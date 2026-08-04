from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


@dataclass
class NoopyChannel:
    id: str
    name: str
    stream_url: str | None = None
    logo_url: str | None = None
    category: str | None = None
    tvg_id: str | None = None
    stream_id: int | None = None
    has_catchup: bool = False
    catchup_days: int = 0
    order: int = 0
    current_program: dict | None = None


@dataclass
class NoopyCategory:
    name: str
    channels_count: int = 0


@dataclass
class NoopyProgram:
    id: str
    title: str
    start: datetime
    end: datetime
    description: str | None = None
    icon_url: str | None = None
    progress_percent: float = 0.0

    @property
    def is_current(self) -> bool:
        now = datetime.now(timezone.utc)
        return self.start <= now < self.end


class NoopyTVAPIError(Exception):
    pass


class NoopyTVConnectionError(NoopyTVAPIError):
    pass


class NoopyTVAPI:

    def __init__(
        self,
        host: str,
        port: int = 8765,
        session: aiohttp.ClientSession | None = None,
        api_key: str | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._session = session
        self._own_session = session is None
        self._base_url = f"http://{host}:{port}"
        self._api_key = api_key
        self._channels: dict[str, NoopyChannel] = {}
        self._categories: list[NoopyCategory] = []
        self._info: dict[str, Any] = {}
        # ⚡️ FIX HA (2026-06-20) — cache de la liste lourde + détecteur de changement.
        # La liste channels (jusqu'à 60k) ne change que rarement ; on évite de la
        # re-télécharger/re-parser à chaque tick du coordinator (cf. refresh_data).
        self._cached_channels_data: dict[str, dict[str, Any]] = {}
        self._cached_categories_data: dict[str, dict[str, Any]] = {}
        self._last_generation: int | None = None
        self._last_total_channels: int | None = None
        self._last_total_categories: int | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._own_session = True
        return self._session

    async def close(self) -> None:
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()

    def _auth_headers(self) -> dict[str, str]:
        if self._api_key:
            return {"X-API-Key": self._api_key}
        return {}

    @property
    def api_key(self) -> str | None:
        return self._api_key

    def set_api_key(self, api_key: str) -> None:
        self._api_key = api_key

    async def _request(self, endpoint: str, timeout: float | None = None) -> Any:
        session = await self._ensure_session()
        url = f"{self._base_url}{endpoint}"

        # ⚡️ FIX HA (2026-06-20) — timeout serré par requête (réseau LAN). Sans ça, un Apple TV
        # bloqué fige le coordinator 30s. connect court (3s) + total adapté à la taille du payload.
        req_timeout = aiohttp.ClientTimeout(connect=3, total=timeout or 12)
        try:
            async with session.get(url, headers=self._auth_headers(), timeout=req_timeout) as response:
                if response.status != 200:
                    raise NoopyTVAPIError(f"Erreur HTTP {response.status}")
                return await response.json()
        except aiohttp.ClientConnectorError as err:
            raise NoopyTVConnectionError(f"Impossible de se connecter à OneTV: {err}") from err
        except aiohttp.ClientError as err:
            raise NoopyTVAPIError(f"Erreur de connexion: {err}") from err

    async def get_info(self) -> dict[str, Any]:
        # /api/v1/info is public — no auth required (used to discover the api_key)
        data = await self._request("/api/v1/info")
        self._info = data
        # Auto-pick up the api_key advertised by the server
        if not self._api_key and isinstance(data, dict):
            advertised = data.get("api_key")
            if isinstance(advertised, str) and advertised:
                self._api_key = advertised
        return data

    async def test_connection(self) -> bool:
        try:
            info = await self.get_info()
            return info.get("name") == "OneTV"
        except NoopyTVAPIError:
            return False

    async def get_channels(self) -> list[NoopyChannel]:
        # Gros payload (jusqu'à 60k chaînes) → timeout plus large.
        data = await self._request("/api/v1/channels", timeout=20)
        channels_data = data.get("channels", [])
        channels = []
        self._channels = {}  # reset (évite les chaînes périmées d'une playlist précédente)

        for item in channels_data:
            current_prog = None
            if "current_program" in item:
                prog = item["current_program"]
                current_prog = {
                    "title": prog.get("title"),
                    "start": prog.get("start"),
                    "end": prog.get("end"),
                    "description": prog.get("description"),
                    "icon_url": prog.get("icon_url"),
                    "progress_percent": prog.get("progress_percent", 0),
                }

            channel = NoopyChannel(
                id=item.get("id", ""),
                name=item.get("name", ""),
                stream_url=item.get("stream_url"),
                logo_url=item.get("logo_url"),
                category=item.get("category"),
                tvg_id=item.get("tvg_id"),
                stream_id=item.get("stream_id"),
                has_catchup=item.get("has_catchup", False),
                catchup_days=item.get("catchup_days", 0),
                order=item.get("order", 0),
                current_program=current_prog,
            )
            channels.append(channel)
            self._channels[channel.id] = channel

        _LOGGER.debug("Récupéré %d chaînes depuis OneTV", len(channels))
        return channels

    async def get_categories(self, player_data: dict[str, Any] | None = None) -> list[NoopyCategory]:
        """Récupère les catégories — avec fallback robuste.

        Le serveur OneTV expose `/api/v1/categories` mais peut renvoyer une liste vide
        si le cache n'a pas encore été poussé (apps non rebuilées). Dans ce cas,
        reconstruit les catégories depuis `available_channels` du /player.

        `player_data` : si fourni (déjà fetché dans le même tick), évite un 2e GET /player
        coûteux pour le fallback.
        """
        data = await self._request("/api/v1/categories", timeout=10)
        categories_data = data.get("categories", [])

        if categories_data:
            self._categories = [
                NoopyCategory(name=item.get("name", ""), channels_count=item.get("channels_count", 0))
                for item in categories_data
            ]
            return self._categories

        # Fallback : reconstruire depuis available_channels du /player (réutilise le player déjà
        # fetché si possible, sinon un GET ciblé).
        if player_data is None:
            try:
                player_data = await self._request("/api/v1/player", timeout=6)
            except NoopyTVAPIError:
                player_data = {}
        available = (player_data or {}).get("available_channels", []) or []

        counts: dict[str, int] = {}
        for ch in available:
            cat = ch.get("category")
            if not cat:
                continue
            counts[cat] = counts.get(cat, 0) + 1
        # Tri par nom de catégorie (alpha) — l'ordre métier réel n'est pas exposé ici
        ordered = OrderedDict(sorted(counts.items(), key=lambda kv: kv[0]))
        self._categories = [NoopyCategory(name=name, channels_count=count) for name, count in ordered.items()]
        if self._categories:
            _LOGGER.info(
                "OneTV: /api/v1/categories vide, reconstruit %d catégorie(s) depuis available_channels",
                len(self._categories),
            )
        return self._categories

    async def get_now_playing(self) -> list[dict[str, Any]]:
        data = await self._request("/api/v1/now")
        return data.get("now_playing", [])

    async def get_player_status(self) -> dict[str, Any]:
        """Récupère l'état du player legacy (`/api/v1/player`) avec available_channels."""
        data = await self._request("/api/v1/player", timeout=6)
        return data

    async def get_playback_state(self) -> dict[str, Any]:
        """Récupère l'état détaillé de la lecture (`/api/v1/player/state`).

        Retourne contentType (channel/movie/episode/catchup/none), contentTitle,
        contentSubtitle, posterURL, logoURL, tmdbID, currentTime, duration,
        isPlaying, isPaused, isBuffering, audioTracks, subtitleTracks, etc.

        Permet de distinguer une chaîne TV d'une VOD/épisode et de remonter
        l'image (poster pour film/épisode, logo pour chaîne).
        """
        try:
            return await self._request("/api/v1/player/state", timeout=6)
        except NoopyTVAPIError as err:
            _LOGGER.debug("get_playback_state failed: %s", err)
            return {}

    async def play_channel(self, channel_id: str) -> bool:
        session = await self._ensure_session()
        url = f"{self._base_url}/api/v1/player/play"

        headers = {"Content-Type": "application/json", **self._auth_headers()}

        try:
            async with session.post(url, json={"channel_id": channel_id}, headers=headers) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("success", False)
                return False
        except aiohttp.ClientError as err:
            _LOGGER.error("Erreur lors du changement de chaîne: %s", err)
            return False

    async def send_command(self, command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Envoie une commande au lecteur via `POST /api/v1/player/command`.

        Le serveur décode un `RemoteCommand` Swift : `command` (String), `params`
        ([String: RemoteValue] — scalaires JSON nus) et `requestId` (String **requis**,
        non optionnel côté Swift → toujours l'envoyer, sinon 400 Invalid command JSON).

        Retourne le dict de réponse (`success`, `message`, `error`, `data`). Lève
        `NoopyTVAPIError` si la requête elle-même échoue.
        """
        session = await self._ensure_session()
        url = f"{self._base_url}/api/v1/player/command"
        headers = {"Content-Type": "application/json", **self._auth_headers()}
        payload: dict[str, Any] = {
            "command": command,
            "requestId": uuid.uuid4().hex,
        }
        if params:
            payload["params"] = params

        req_timeout = aiohttp.ClientTimeout(connect=3, total=10)
        try:
            async with session.post(url, json=payload, headers=headers, timeout=req_timeout) as response:
                if response.status == 404:
                    # Ancienne version de l'app : l'endpoint commandes n'existe pas encore.
                    raise NoopyTVAPIError(
                        "Commandes non supportées par cette version de OneTV (mettez l'app à jour)"
                    )
                if response.status != 200:
                    raise NoopyTVAPIError(f"Erreur HTTP {response.status} sur send_command({command})")
                return await response.json()
        except aiohttp.ClientConnectorError as err:
            raise NoopyTVConnectionError(f"Impossible de se connecter à OneTV: {err}") from err
        except aiohttp.ClientError as err:
            raise NoopyTVAPIError(f"Erreur de connexion: {err}") from err

    async def get_movies(self) -> list[dict[str, Any]]:
        """Catalogue films groupé par catégorie (`/api/v1/movies`).

        Shape serveur : `{totalCategories, categories: [{categoryId, categoryName,
        moviesCount, movies: [{id, name, posterURL, tmdbId, year, rating}]}]}`.
        ⚠️ Le serveur plafonne à 100 films par catégorie.
        """
        try:
            data = await self._request("/api/v1/movies", timeout=20)
        except NoopyTVAPIError as err:
            _LOGGER.debug("get_movies failed: %s", err)
            return []
        return data.get("categories", []) or []

    async def get_series(self) -> list[dict[str, Any]]:
        """Catalogue séries groupé par catégorie (`/api/v1/series`) — même shape, clé `series`."""
        try:
            data = await self._request("/api/v1/series", timeout=20)
        except NoopyTVAPIError as err:
            _LOGGER.debug("get_series failed: %s", err)
            return []
        return data.get("categories", []) or []

    async def get_series_episodes(self, series_id: str) -> tuple[bool, list[dict[str, Any]]]:
        """Épisodes d'une série (`/api/v1/series/{id}/episodes`, app >= 2026-08).

        Retourne `(loading, episodes)`. Les épisodes ne sont pas portés par la fiche série :
        l'app les charge à la demande par fournisseur. Quand son cache est vide, le serveur
        déclenche le chargement et répond `loading: true` avec une liste vide — l'appelant
        rappelle un instant plus tard. Un serveur plus ancien renvoie 404 : `(False, [])`.
        """
        try:
            data = await self._request(f"/api/v1/series/{series_id}/episodes", timeout=10)
        except NoopyTVAPIError as err:
            _LOGGER.debug("get_series_episodes(%s) failed: %s", series_id, err)
            return False, []
        return bool(data.get("loading")), data.get("episodes", []) or []

    async def listen_events(
        self,
        on_event: Callable[[str, dict[str, Any]], None],
        on_connected: Callable[[], None] | None = None,
    ) -> None:
        """Consomme le flux SSE `/api/v1/events/stream` jusqu'à déconnexion.

        Le serveur (tvOS uniquement) émet `event: <kind>\\ndata: <json>\\n\\n` avec
        kind ∈ snapshot | channel.start | channel.change | channel.stop | sport.context,
        plus un commentaire `: ping` toutes les 10 s. Sur iOS le serveur répond 501.

        Lève `NoopyTVConnectionError` / `NoopyTVAPIError` — l'appelant gère la reconnexion.
        """
        session = await self._ensure_session()
        url = f"{self._base_url}/api/v1/events/stream"
        headers = {"Accept": "text/event-stream", **self._auth_headers()}
        # Flux long : pas de timeout total, seulement la connexion. `sock_read` sert de
        # détecteur de mort du lien — le heartbeat serveur tombe toutes les 10 s, donc
        # 45 s sans le moindre octet = lien perdu.
        stream_timeout = aiohttp.ClientTimeout(total=None, connect=5, sock_read=45)

        try:
            async with session.get(url, headers=headers, timeout=stream_timeout) as response:
                if response.status == 501:
                    raise NoopyTVAPIError("SSE non disponible (serveur iOS, tvOS uniquement)")
                if response.status == 404:
                    raise NoopyTVAPIError("SSE non supporté par cette version de OneTV")
                if response.status != 200:
                    raise NoopyTVAPIError(f"SSE erreur HTTP {response.status}")

                _LOGGER.debug("OneTV: flux SSE connecté (%s)", url)
                if on_connected is not None:
                    on_connected()
                event_name = "message"
                data_lines: list[str] = []

                async for raw_line in response.content:
                    line = raw_line.decode("utf-8", errors="ignore").rstrip("\r\n")

                    if line.startswith(":"):
                        continue  # heartbeat / commentaire
                    if line.startswith("event:"):
                        event_name = line[len("event:"):].strip()
                        continue
                    if line.startswith("data:"):
                        data_lines.append(line[len("data:"):].strip())
                        continue
                    if line == "":
                        if data_lines:
                            payload: dict[str, Any] = {}
                            raw = "\n".join(data_lines)
                            try:
                                decoded = json.loads(raw)
                                if isinstance(decoded, dict):
                                    payload = decoded
                            except ValueError:
                                _LOGGER.debug("SSE: payload non-JSON ignoré (%s)", raw[:120])
                            on_event(event_name, payload)
                        event_name = "message"
                        data_lines = []
        except asyncio.TimeoutError as err:
            raise NoopyTVConnectionError(f"SSE timeout: {err}") from err
        except aiohttp.ClientConnectorError as err:
            raise NoopyTVConnectionError(f"SSE injoignable: {err}") from err
        except aiohttp.ClientError as err:
            raise NoopyTVAPIError(f"SSE erreur: {err}") from err

    async def get_channel_detail(self, channel_id: str) -> dict[str, Any] | None:
        try:
            data = await self._request(f"/api/v1/channel/{channel_id}")
            return data
        except NoopyTVAPIError:
            return None

    async def refresh_data(self) -> dict[str, Any]:
        """Rafraîchit les données nécessaires aux entities HA.

        ⚡️ FIX HA (2026-06-20) — La liste lourde (channels + categories, jusqu'à 60k) n'est
        re-téléchargée QUE lorsqu'elle a changé. Avant, chaque tick du coordinator re-pullait
        et re-parsait tout le catalogue → réseau saturé + lag. Désormais :
          1. `/api/v1/info` (O(1) serveur) donne `channels_generation` (repli sur les compteurs).
          2. `player` + `playback_state` (petits, temps réel) sont fetchés en parallèle à CHAQUE tick.
          3. La liste lourde n'est fetchée que si la génération/les compteurs ont changé ; sinon on
             réutilise le cache → la chaîne en cours reste fluide sans marteler le catalogue.
        """
        # 1) Détecteur de changement bon marché.
        info: dict[str, Any] = {}
        try:
            info = await self.get_info()
        except NoopyTVAPIError:
            info = {}
        generation = info.get("channels_generation")
        total_ch = info.get("total_channels")
        total_cat = info.get("total_categories")

        # 2) Player + playback_state : toujours, en parallèle (temps réel, petits payloads).
        player_status, playback_state = await asyncio.gather(
            self.get_player_status(),
            self.get_playback_state(),
        )

        # 3) Décide si la liste lourde doit être re-fetchée.
        if generation is not None:
            channels_changed = generation != self._last_generation
        else:
            # Serveur ancien sans génération → repli sur les compteurs.
            channels_changed = (
                total_ch != self._last_total_channels
                or total_cat != self._last_total_categories
            )
        if not self._cached_channels_data:
            channels_changed = True  # 1er tick / cache vide

        if channels_changed:
            channels = await self.get_channels()
            categories = await self.get_categories(player_data=player_status)

            channels_data: dict[str, dict[str, Any]] = {}
            for channel in channels:
                cd: dict[str, Any] = {
                    "id": channel.id,
                    "name": channel.name,
                    "logo_url": channel.logo_url,
                    "stream_url": channel.stream_url,
                    "category": channel.category,
                    "tvg_id": channel.tvg_id,
                    "stream_id": channel.stream_id,
                    "has_catchup": channel.has_catchup,
                    "catchup_days": channel.catchup_days,
                    "order": channel.order,
                }
                if channel.current_program:
                    cd.update({
                        "current_program": channel.current_program.get("title"),
                        "current_program_start": channel.current_program.get("start"),
                        "current_program_end": channel.current_program.get("end"),
                        "current_program_description": channel.current_program.get("description"),
                        "current_program_icon": channel.current_program.get("icon_url"),
                        "progress_percent": channel.current_program.get("progress_percent", 0),
                    })
                channels_data[channel.id] = cd

            self._cached_channels_data = channels_data
            self._cached_categories_data = {
                cat.name: {"name": cat.name, "channels_count": cat.channels_count}
                for cat in categories
            }
            self._last_generation = generation
            self._last_total_channels = total_ch if total_ch is not None else len(channels)
            self._last_total_categories = total_cat if total_cat is not None else len(categories)
            _LOGGER.debug("OneTV: liste chaînes re-fetchée (%d chaînes)", len(channels_data))

        return {
            "channels": self._cached_channels_data,
            "categories": self._cached_categories_data,
            "total_channels": len(self._cached_channels_data),
            "total_categories": len(self._cached_categories_data),
            "player": player_status,
            "playback_state": playback_state,
        }

    @property
    def channels(self) -> dict[str, NoopyChannel]:
        return self._channels

    @property
    def categories(self) -> list[NoopyCategory]:
        return self._categories

    @property
    def info(self) -> dict[str, Any]:
        return self._info
