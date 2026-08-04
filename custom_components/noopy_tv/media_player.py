"""Entité media_player pour OneTV.

⚡️ v4.0.0 — Avant, l'intégration n'exposait que des `sensor` + `select` : l'état de lecture
détaillé était pourtant déjà récupéré à chaque tick (`/api/v1/player/state`) et jeté, et le
jeu de commandes complet (`POST /api/v1/player/command`) n'était jamais appelé. Cette entité
ne coûte donc AUCUNE requête réseau supplémentaire.

⚠️ Volume volontairement NON exposé : `RemoteCommand` (côté Swift) définit bien
setVolume/adjustVolume/toggleMute, mais le switch de `AppModel.handleRemoteCommand` — le seul
handler câblé sur le serveur HTTP via `RootView.executeCommandHandler` — ne les implémente pas.
Les annoncer donnerait un curseur de volume mort dans l'UI.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import quote

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaClass,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceNotSupported
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import NoopyTVAPI, NoopyTVAPIError
from .const import (
    CONF_APPLE_TV_ENTITY,
    CONF_APPLE_TV_SOURCE,
    DEFAULT_APPLE_TV_SOURCE,
    DOMAIN,
)
from .device import build_device_info
from .images import async_square_png, proxy_image_url
from .naming import is_channel_name_valid

_LOGGER = logging.getLogger(__name__)

# Identifiants de navigation du media browser.
_BROWSE_ROOT = "root"
_BROWSE_CHANNELS = "channels"
_BROWSE_MOVIES = "movies"
_BROWSE_SERIES = "series"
_BROWSE_EPISODES = "episodes"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NoopyTVMediaPlayer(data["coordinator"], data["api"], entry)])


class NoopyTVMediaPlayer(CoordinatorEntity, MediaPlayerEntity):
    """Lecteur OneTV : état complet, transport, zapping, catalogue navigable."""

    _attr_has_entity_name = True
    _attr_name = None  # entité principale du device → porte le nom du device
    _attr_device_class = MediaPlayerDeviceClass.TV

    def __init__(self, coordinator, api: NoopyTVAPI, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._api = api
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_media_player"
        self._last_position: float | None = None
        self._last_position_updated = dt_util.utcnow()

    # ------------------------------------------------------------------ device

    @property
    def device_info(self) -> DeviceInfo:
        return build_device_info(self._entry, getattr(self._api, "info", None))

    @property
    def available(self) -> bool:
        """TOUJOURS disponible — c'est ce qui rend `turn_on` utile.

        Quand l'app est fermée son serveur HTTP est mort et le coordinator échoue. Si on
        laissait l'entité passer `unavailable` (comportement par défaut de CoordinatorEntity),
        HA refuserait `media_player.turn_on` et on ne pourrait plus lancer l'app depuis une
        automatisation — exactement l'impasse qui obligeait à passer par l'entité Apple TV.
        L'app injoignable est donc rendue comme l'état `off`, pas comme une indisponibilité.
        """
        return True

    # ------------------------------------------------------- accès aux données

    def _player(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("player", {}) or {}

    def _state_payload(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("playback_state", {}) or {}

    def _channels(self) -> dict[str, dict[str, Any]]:
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("channels", {}) or {}

    def _reachable(self) -> bool:
        return bool(self.coordinator.last_update_success)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Suit les sauts de position pour alimenter `media_position_updated_at`.

        HA extrapole la position entre deux mises à jour à partir de cet horodatage : le
        rafraîchir à chaque tick ferait repartir la barre de progression en arrière à chaque
        fois. On ne le bouge donc que si la position a réellement bougé d'au moins 1 s.
        """
        position = self._state_payload().get("currentTime")
        if isinstance(position, (int, float)):
            if self._last_position is None or abs(position - self._last_position) >= 1:
                self._last_position = float(position)
                self._last_position_updated = dt_util.utcnow()
        super()._handle_coordinator_update()

    # ------------------------------------------------------------------- état

    @property
    def state(self) -> MediaPlayerState:
        if not self._reachable():
            return MediaPlayerState.OFF

        ps = self._state_payload()
        active = ps.get("isPlayerActive")
        if active is None:
            active = self._player().get("is_active", False)
        if not active:
            return MediaPlayerState.IDLE
        if ps.get("isPaused"):
            return MediaPlayerState.PAUSED
        if ps.get("isBuffering"):
            return MediaPlayerState.BUFFERING
        # ⚠️ En live, l'app laisse régulièrement `isPlaying` à false entre deux transitions
        # alors que le flux tourne (mesuré : lecteur actif, ni pause ni buffering, tous les
        # drapeaux à false). Renvoyer ON ferait afficher un « Allumé » vague dans l'UI :
        # lecteur actif et non mis en pause = en lecture.
        return MediaPlayerState.PLAYING

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        features = (
            MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.PAUSE
            | MediaPlayerEntityFeature.STOP
            | MediaPlayerEntityFeature.NEXT_TRACK
            | MediaPlayerEntityFeature.PREVIOUS_TRACK
            | MediaPlayerEntityFeature.SELECT_SOURCE
            | MediaPlayerEntityFeature.PLAY_MEDIA
            | MediaPlayerEntityFeature.BROWSE_MEDIA
            | MediaPlayerEntityFeature.TURN_OFF
        )
        if self._apple_tv_entity():
            features |= MediaPlayerEntityFeature.TURN_ON
        # Le seek n'a de sens que sur un contenu borné : en live `duration` vaut 0 et le
        # timeshift se pilote par `seekToLive` / `seekRelative`, pas par une position absolue.
        duration = self._state_payload().get("duration") or 0
        if duration > 0 and not self._state_payload().get("isLive"):
            features |= MediaPlayerEntityFeature.SEEK
        return features

    # ------------------------------------------------------------- média joué

    @property
    def media_content_type(self) -> str | None:
        content = self._state_payload().get("contentType")
        if content == "channel":
            return MediaType.CHANNEL
        if content == "movie":
            return MediaType.MOVIE
        if content == "episode":
            return MediaType.EPISODE
        if content == "catchup":
            return MediaType.CHANNEL
        return None

    @property
    def media_content_id(self) -> str | None:
        return self._state_payload().get("contentId")

    @property
    def media_title(self) -> str | None:
        """Titre = ce qu'on regarde. En live, c'est le PROGRAMME (pas la chaîne)."""
        ps = self._state_payload()
        content = ps.get("contentType")
        if content in ("channel", "catchup"):
            programme = ps.get("currentProgramme") or {}
            if programme.get("title"):
                return str(programme["title"])
            # ⚠️ `current_program` a DEUX formes : un dict dans le payload brut de
            # /api/v1/player, mais déjà aplati en titre (str) dans le cache du coordinator.
            channel_program = (self._player().get("current_channel") or {}).get("current_program")
            if isinstance(channel_program, dict):
                title = channel_program.get("title")
                if title:
                    return str(title)
            elif channel_program:
                return str(channel_program)
            # Sans EPG, afficher la chaîne vaut mieux qu'une tuile sans titre.
            return self.media_channel
        return ps.get("contentTitle")

    @property
    def media_channel(self) -> str | None:
        current = self._player().get("current_channel") or {}
        if current.get("name"):
            return str(current["name"])
        ps = self._state_payload()
        if ps.get("contentType") == "channel":
            return ps.get("contentTitle")
        return None

    @property
    def media_series_title(self) -> str | None:
        if self._state_payload().get("contentType") == "episode":
            return self._state_payload().get("contentTitle")
        return None

    @property
    def media_episode(self) -> str | None:
        if self._state_payload().get("contentType") == "episode":
            return self._state_payload().get("contentSubtitle")
        return None

    @property
    def media_duration(self) -> int | None:
        ps = self._state_payload()
        # ⚠️ En live, `duration` renvoie la profondeur du tampon timeshift (souvent quelques
        # secondes), PAS la durée d'un contenu : l'exposer afficherait une barre de
        # progression de 12 s sur une chaîne TV. Le live n'a pas de durée.
        if ps.get("isLive"):
            return None
        duration = ps.get("duration")
        if isinstance(duration, (int, float)) and duration > 0:
            return int(duration)
        return None

    @property
    def media_position(self) -> int | None:
        if self.media_duration is None:
            return None
        position = self._state_payload().get("currentTime")
        if isinstance(position, (int, float)):
            return int(position)
        return None

    @property
    def media_position_updated_at(self):
        if self.media_position is None:
            return None
        return self._last_position_updated

    def _proxy_image_url(self, raw_url: str, size: int = 400) -> str:
        """Passe l'image par le proxy AUTHENTIFIÉ de l'app (cf. images.proxy_image_url)."""
        return proxy_image_url(self._entry, raw_url, size)

    @property
    def media_image_url(self) -> str | None:
        ps = self._state_payload()
        if ps.get("contentType") in ("movie", "episode") and ps.get("posterURL"):
            return self._proxy_image_url(str(ps["posterURL"]), size=400)
        if ps.get("logoURL"):
            return self._proxy_image_url(str(ps["logoURL"]), size=200)
        current = self._player().get("current_channel") or {}
        if current.get("logo_url"):
            return self._proxy_image_url(str(current["logo_url"]), size=200)
        return None

    async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
        """Jaquette MISE AU CARRÉ avant d'être servie par Home Assistant.

        HA récupère `media_image_url` côté serveur puis l'affiche dans une vignette carrée
        avec recadrage centré : un logo de chaîne y perdait ses bords.
        """
        url = self.media_image_url
        if not url:
            return None, None
        data = await async_square_png(self.hass, url)
        if data is None:
            return None, None
        return data, "image/png"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ps = self._state_payload()
        attrs: dict[str, Any] = {
            "player_type": ps.get("playerType"),
            "is_live": ps.get("isLive"),
            "is_at_live_edge": ps.get("isAtLiveEdge"),
            "timeshift_delay": ps.get("timeshiftDelay"),
        }
        audio = ps.get("audioTracks") or []
        subtitles = ps.get("subtitleTracks") or []
        if audio:
            attrs["audio_tracks"] = [t.get("name") for t in audio]
            selected = next((t for t in audio if t.get("isSelected")), None)
            if selected:
                attrs["audio_track"] = selected.get("name")
        if subtitles:
            attrs["subtitle_tracks"] = [t.get("name") for t in subtitles]
            selected = next((t for t in subtitles if t.get("isSelected")), None)
            if selected:
                attrs["subtitle_track"] = selected.get("name")
        return {k: v for k, v in attrs.items() if v is not None}

    # ------------------------------------------------------------- sources

    @property
    def source(self) -> str | None:
        return self.media_channel

    @property
    def source_list(self) -> list[str]:
        # Les playlists M3U contiennent des lignes décoratives qui ne sont pas des chaînes
        # (« ---●★| MANGA |★●--- ») : elles pollueraient la liste déroulante (règle 12).
        names = {
            ch["name"]
            for ch in self._channels().values()
            if ch.get("name") and is_channel_name_valid(ch["name"])
        }
        return sorted(names)

    def _resolve_channel_id(self, wanted: str) -> str | None:
        """UUID → tel quel ; sinon match sur le nom (exact d'abord, puis insensible à la casse)."""
        channels = self._channels()
        if wanted in channels:
            return wanted
        for channel_id, channel in channels.items():
            if channel.get("name") == wanted:
                return channel_id
        lowered = wanted.casefold()
        for channel_id, channel in channels.items():
            if str(channel.get("name", "")).casefold() == lowered:
                return channel_id
        return None

    # ------------------------------------------------------------- commandes

    async def _send(self, command: str, params: dict[str, Any] | None = None) -> None:
        try:
            result = await self._api.send_command(command, params)
        except NoopyTVAPIError as err:
            raise HomeAssistantError(f"OneTV: commande '{command}' échouée — {err}") from err
        if not result.get("success", False):
            raise HomeAssistantError(
                f"OneTV a refusé la commande '{command}': {result.get('error') or result.get('message')}"
            )
        await self.coordinator.async_request_refresh()

    async def async_media_play(self) -> None:
        await self._send("play")

    async def async_media_pause(self) -> None:
        await self._send("pause")

    async def async_media_play_pause(self) -> None:
        await self._send("togglePlayPause")

    async def async_media_stop(self) -> None:
        await self._send("stop")

    async def async_media_next_track(self) -> None:
        await self._send("nextChannel")

    async def async_media_previous_track(self) -> None:
        await self._send("previousChannel")

    async def async_media_seek(self, position: float) -> None:
        await self._send("seekAbsolute", {"position": float(position)})

    async def async_turn_off(self) -> None:
        """Arrête la lecture. Ne ferme PAS l'app : tvOS ne permet pas de quitter une app à distance."""
        await self._send("stop")

    def _apple_tv_entity(self) -> str | None:
        return self._entry.options.get(CONF_APPLE_TV_ENTITY) or self._entry.data.get(
            CONF_APPLE_TV_ENTITY
        )

    def _apple_tv_source(self) -> str:
        return (
            self._entry.options.get(CONF_APPLE_TV_SOURCE)
            or self._entry.data.get(CONF_APPLE_TV_SOURCE)
            or DEFAULT_APPLE_TV_SOURCE
        )

    async def async_turn_on(self) -> None:
        """Lance (ou réveille) l'app OneTV via l'entité Apple TV associée.

        Nécessite `select_source` sur l'Apple TV : l'app ne peut pas se lancer elle-même
        puisque son serveur HTTP ne tourne que quand elle est déjà ouverte.
        """
        entity_id = self._apple_tv_entity()
        if not entity_id:
            raise HomeAssistantError(
                "Aucune entité Apple TV associée : configurez-la dans les options de "
                "l'intégration OneTV pour pouvoir lancer l'app depuis Home Assistant."
            )

        await self._wake_apple_tv(entity_id)
        await self._select_source_with_retry(entity_id)
        await self._wait_until_reachable()

    async def _wake_apple_tv(self, entity_id: str, timeout: float = 20.0) -> None:
        """Réveille l'Apple TV avant tout `select_source`.

        ⚠️ Endormie, l'Apple TV retire SELECT_SOURCE de ses `supported_features` et Home
        Assistant refuse l'appel avec `ServiceNotSupported` avant même de l'exécuter. Sans
        ce réveil, lancer OneTV depuis une automatisation échoue dès que le téléviseur est
        éteint — c'est-à-dire précisément au retour à la maison.

        ⚠️ Mesuré sur l'appareil : ni `media_player.turn_on`, ni `remote.turn_on` ne la
        réveillent (l'entité reste `off`). Seul l'envoi d'une touche — `remote.send_command`
        avec `home` — la sort de veille, en ~8 s.
        """
        if self.hass.states.get(entity_id) is None:
            raise HomeAssistantError(f"L'entité {entity_id} n'existe pas.")

        if not self._apple_tv_is_asleep(entity_id):
            return

        remote_entity = self._companion_remote(entity_id)
        if remote_entity is None:
            _LOGGER.debug(
                "OneTV: pas d'entité remote associée à %s, réveil impossible", entity_id
            )
            return

        try:
            await self.hass.services.async_call(
                "remote",
                "send_command",
                {"entity_id": remote_entity, "command": "home"},
                blocking=True,
            )
        except HomeAssistantError as err:
            _LOGGER.debug("OneTV: réveil via %s impossible (%s)", remote_entity, err)
            return

        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(1)
            if not self._apple_tv_is_asleep(entity_id):
                return

    def _apple_tv_is_asleep(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return state is None or state.state in ("off", "unavailable", "standby", "unknown")

    def _companion_remote(self, entity_id: str) -> str | None:
        """Entité `remote.*` du même appareil que le media_player Apple TV."""
        registry = er.async_get(self.hass)
        entry = registry.async_get(entity_id)
        if entry is None or entry.device_id is None:
            return None
        for candidate in er.async_entries_for_device(
            registry, entry.device_id, include_disabled_entities=False
        ):
            if candidate.domain == "remote":
                return candidate.entity_id
        return None

    async def _select_source_with_retry(
        self, entity_id: str, attempts: int = 5, delay: float = 3.0
    ) -> None:
        """Lance l'app, en réessayant tant que l'Apple TV refuse le changement de source.

        ⚠️ Ne PAS se fier à l'attribut `supported_features` pour savoir si l'appel va
        passer : il est mis à jour de façon différée. Observé sur l'appareil — l'attribut
        annonçait SELECT_SOURCE disponible alors que l'appel levait encore
        `ServiceNotSupported`. Seul le réessai est fiable.
        """
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                await self.hass.services.async_call(
                    "media_player",
                    "select_source",
                    {"entity_id": entity_id, "source": self._apple_tv_source()},
                    blocking=True,
                )
                return
            except ServiceNotSupported as err:
                last_error = err
                if attempt < attempts - 1:
                    await asyncio.sleep(delay)

        raise HomeAssistantError(
            f"{entity_id} refuse toujours le changement de source après "
            f"{attempts} tentatives — l'Apple TV ne se réveille pas. Allumez le téléviseur "
            "puis réessayez."
        ) from last_error

    async def _wait_until_reachable(self, timeout: float = 40.0) -> bool:
        """Attend que le serveur HTTP de l'app réponde de nouveau.

        Lancement à froid mesuré ~10 s, réveil d'une app suspendue <4 s.
        """
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            await self.coordinator.async_refresh()
            if self.coordinator.last_update_success:
                return True
            await asyncio.sleep(2)
        _LOGGER.warning("OneTV: l'app n'a pas répondu dans les %.0fs après le lancement", timeout)
        return False

    async def async_select_source(self, source: str) -> None:
        await self._play_channel(source)

    async def _play_channel(self, wanted: str) -> None:
        if not self._reachable():
            await self.async_turn_on()

        channel_id = self._resolve_channel_id(wanted) or wanted
        # `play_channel` traverse /api/v1/player/play, qui résout aussi bien un UUID qu'un nom.
        if not await self._api.play_channel(channel_id):
            raise HomeAssistantError(f"OneTV n'a pas trouvé la chaîne « {wanted} »")
        await self.coordinator.async_request_refresh()

    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        """Lit une chaîne, un film ou un épisode.

        - `channel` / `tvchannel` : `media_id` = UUID ou nom de chaîne
        - `movie` : `media_id` = identifiant du film
        - `episode` : `media_id` = `<seriesId>/<saison>/<episode>`
        """
        normalized = (media_type or "").lower()

        if normalized in (MediaType.CHANNEL, "tvchannel", "channel"):
            await self._play_channel(media_id)
            return

        if not self._reachable():
            await self.async_turn_on()

        if normalized == MediaType.MOVIE:
            await self._send("playMovie", {"movieId": media_id})
            return

        if normalized in (MediaType.EPISODE, MediaType.TVSHOW, "episode", "tvshow"):
            parts = media_id.split("/")
            series_id = parts[0]
            season = int(parts[1]) if len(parts) > 1 else 1
            episode = int(parts[2]) if len(parts) > 2 else 1
            await self._send(
                "playEpisode",
                {"seriesId": series_id, "seasonNumber": season, "episodeNumber": episode},
            )
            return

        raise HomeAssistantError(f"Type de média non supporté par OneTV: {media_type}")

    # --------------------------------------------------------- media browser

    async def async_browse_media(
        self,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        if media_content_id in (None, _BROWSE_ROOT):
            return self._browse_root()
        if media_content_id == _BROWSE_CHANNELS:
            return self._browse_channel_categories()
        if media_content_id.startswith(f"{_BROWSE_CHANNELS}/"):
            return self._browse_channels_in_category(media_content_id.split("/", 1)[1])
        if media_content_id == _BROWSE_MOVIES:
            return await self._browse_vod(_BROWSE_MOVIES)
        if media_content_id == _BROWSE_SERIES:
            return await self._browse_vod(_BROWSE_SERIES)
        if media_content_id.startswith(f"{_BROWSE_MOVIES}/"):
            return await self._browse_vod_category(_BROWSE_MOVIES, media_content_id.split("/", 1)[1])
        if media_content_id.startswith(f"{_BROWSE_EPISODES}/"):
            return await self._browse_episodes(media_content_id.split("/", 1)[1])
        if media_content_id.startswith(f"{_BROWSE_SERIES}/"):
            return await self._browse_vod_category(_BROWSE_SERIES, media_content_id.split("/", 1)[1])
        raise HomeAssistantError(f"Chemin de navigation inconnu: {media_content_id}")

    def _browse_root(self) -> BrowseMedia:
        return BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id=_BROWSE_ROOT,
            media_content_type="",
            title="OneTV",
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.DIRECTORY,
            children=[
                BrowseMedia(
                    media_class=MediaClass.DIRECTORY,
                    media_content_id=_BROWSE_CHANNELS,
                    media_content_type="",
                    title="Chaînes",
                    can_play=False,
                    can_expand=True,
                ),
                BrowseMedia(
                    media_class=MediaClass.DIRECTORY,
                    media_content_id=_BROWSE_MOVIES,
                    media_content_type="",
                    title="Films",
                    can_play=False,
                    can_expand=True,
                ),
                BrowseMedia(
                    media_class=MediaClass.DIRECTORY,
                    media_content_id=_BROWSE_SERIES,
                    media_content_type="",
                    title="Séries",
                    can_play=False,
                    can_expand=True,
                ),
            ],
        )

    def _browse_channel_categories(self) -> BrowseMedia:
        categories = sorted(
            {ch.get("category") for ch in self._channels().values() if ch.get("category")}
        )
        return BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id=_BROWSE_CHANNELS,
            media_content_type="",
            title="Chaînes",
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.DIRECTORY,
            children=[
                BrowseMedia(
                    media_class=MediaClass.DIRECTORY,
                    media_content_id=f"{_BROWSE_CHANNELS}/{category}",
                    media_content_type="",
                    title=category,
                    can_play=False,
                    can_expand=True,
                )
                for category in categories
            ],
        )

    def _browse_channels_in_category(self, category: str) -> BrowseMedia:
        children = [
            BrowseMedia(
                media_class=MediaClass.CHANNEL,
                media_content_id=channel_id,
                media_content_type=MediaType.CHANNEL,
                title=str(channel.get("name", "")),
                can_play=True,
                can_expand=False,
                thumbnail=(
                    self._proxy_image_url(str(channel["logo_url"]), size=200)
                    if channel.get("logo_url")
                    else None
                ),
            )
            for channel_id, channel in self._channels().items()
            if channel.get("category") == category and is_channel_name_valid(channel.get("name"))
        ]
        children.sort(key=lambda item: item.title)
        return BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id=f"{_BROWSE_CHANNELS}/{category}",
            media_content_type="",
            title=category,
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.CHANNEL,
            children=children,
        )

    async def _fetch_vod(self, kind: str) -> list[dict[str, Any]]:
        if kind == _BROWSE_MOVIES:
            return await self._api.get_movies()
        return await self._api.get_series()

    async def _browse_vod(self, kind: str) -> BrowseMedia:
        categories = await self._fetch_vod(kind)
        title = "Films" if kind == _BROWSE_MOVIES else "Séries"
        return BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id=kind,
            media_content_type="",
            title=title,
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.DIRECTORY,
            children=[
                BrowseMedia(
                    media_class=MediaClass.DIRECTORY,
                    media_content_id=f"{kind}/{category.get('categoryId')}",
                    media_content_type="",
                    title=str(category.get("categoryName", "")),
                    can_play=False,
                    can_expand=True,
                )
                for category in categories
                if category.get("categoryId")
            ],
        )

    async def _browse_vod_category(self, kind: str, category_id: str) -> BrowseMedia:
        categories = await self._fetch_vod(kind)
        category = next(
            (c for c in categories if str(c.get("categoryId")) == category_id), None
        )
        if category is None:
            raise HomeAssistantError(f"Catégorie introuvable: {category_id}")

        is_movies = kind == _BROWSE_MOVIES
        items = category.get("movies" if is_movies else "series", []) or []
        children = []
        for item in items:
            item_id = str(item.get("id", ""))
            if not item_id:
                continue
            children.append(
                BrowseMedia(
                    media_class=MediaClass.MOVIE if is_movies else MediaClass.TV_SHOW,
                    media_content_id=item_id if is_movies else f"{_BROWSE_EPISODES}/{item_id}",
                    media_content_type=MediaType.MOVIE if is_movies else "",
                    title=str(item.get("name", "")),
                    # Une série se déplie sur ses épisodes (app >= 2026-08). Avant, elle se
                    # lançait « au S01E01 » faute d'endpoint pour les lister.
                    can_play=is_movies,
                    can_expand=not is_movies,
                    thumbnail=(
                        self._proxy_image_url(str(item["posterURL"]), size=300)
                        if item.get("posterURL")
                        else None
                    ),
                )
            )
        return BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id=f"{kind}/{category_id}",
            media_content_type="",
            title=str(category.get("categoryName", "")),
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.MOVIE if is_movies else MediaClass.TV_SHOW,
            children=children,
        )

    async def _browse_episodes(self, series_id: str) -> BrowseMedia:
        """Épisodes d'une série.

        ⚠️ L'app charge les épisodes à la demande : le premier appel peut répondre
        « en cours de chargement » avec une liste vide. On repasse alors une fois, une
        seconde plus tard, plutôt que de renvoyer un dossier vide à l'utilisateur.
        """
        loading, episodes = await self._api.get_series_episodes(series_id)
        if loading and not episodes:
            await asyncio.sleep(1.5)
            _, episodes = await self._api.get_series_episodes(series_id)

        children = [
            BrowseMedia(
                media_class=MediaClass.EPISODE,
                media_content_id=f"{series_id}/{episode.get('season', 1)}/{episode.get('episode', 1)}",
                media_content_type=MediaType.EPISODE,
                title=(
                    f"S{int(episode.get('season', 0)):02d}E{int(episode.get('episode', 0)):02d}"
                    f" · {episode.get('title', '')}".strip()
                ),
                can_play=True,
                can_expand=False,
            )
            for episode in episodes
        ]

        return BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id=f"{_BROWSE_EPISODES}/{series_id}",
            media_content_type="",
            title="Épisodes" if children else "Épisodes (indisponibles)",
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.EPISODE,
            children=children,
        )
