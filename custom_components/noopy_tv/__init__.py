from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NoopyTVAPI, NoopyTVAPIError, NoopyTVConnectionError
from .const import (
    CONF_API_KEY,
    CONF_APPLE_TV_ENTITY,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    CONF_SUPPORTS_SSE,
    DOMAIN,
    PLATFORMS as PLATFORM_NAMES,
    SERVICE_PLAY_CHANNEL,
    SERVICE_PLAY_EPISODE,
    SERVICE_PLAY_MOVIE,
    SERVICE_REFRESH,
    SERVICE_SEND_COMMAND,
    SSE_FALLBACK_SCAN_INTERVAL_SECONDS,
    SSE_RECONNECT_MAX_DELAY,
    SSE_RECONNECT_MIN_DELAY,
    SUPPORTED_COMMANDS,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform(name) for name in PLATFORM_NAMES]

PLAY_MOVIE_SCHEMA = vol.Schema(
    {
        vol.Required("movie_id"): cv.string,
        vol.Optional("resume_position"): vol.Coerce(float),
    }
)

PLAY_EPISODE_SCHEMA = vol.Schema(
    {
        vol.Required("series_id"): cv.string,
        vol.Required("season"): vol.Coerce(int),
        vol.Required("episode"): vol.Coerce(int),
        vol.Optional("resume_position"): vol.Coerce(float),
    }
)

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("command"): vol.In(SUPPORTED_COMMANDS),
        vol.Optional("params"): dict,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    # ⚡️ v3.0.0 cleanup : supprimer les anciennes entities `sensor.<entry>_channel_<id>`
    # (1 par chaîne, créait 1000+ entités pour grosses playlists). Désormais un seul
    # sensor `current_channel` agrégé. Les vieilles entities restent dans le registry
    # entre les upgrades — on les nettoie ici à chaque setup.
    _cleanup_legacy_per_channel_sensors(hass, entry)

    session = async_get_clientsession(hass)
    api = NoopyTVAPI(
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        session=session,
        api_key=entry.data.get(CONF_API_KEY),
    )

    try:
        if not await api.test_connection():
            _LOGGER.error("Impossible de se connecter à OneTV")
            return False
    except NoopyTVConnectionError as err:
        _LOGGER.error("Erreur de connexion: %s", err)
        return False
    except NoopyTVAPIError as err:
        _LOGGER.error("Erreur API: %s", err)
        return False

    # Persist the api_key the server may have advertised via /api/v1/info
    # so subsequent restarts don't need to re-fetch it.
    if api.api_key and entry.data.get(CONF_API_KEY) != api.api_key:
        new_data = {**entry.data, CONF_API_KEY: api.api_key}
        hass.config_entries.async_update_entry(entry, data=new_data)

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    if isinstance(scan_interval, int):
        scan_interval = timedelta(seconds=scan_interval)

    coordinator = NoopyTVDataUpdateCoordinator(hass, api=api, update_interval=scan_interval)

    await coordinator.async_config_entry_first_refresh()

    # ⚡️ v4.0.0 — écoute SSE : le serveur tvOS pousse un event à chaque zap (<50 ms).
    # Tant que le flux tient, le polling retombe à un simple filet de sécurité.
    sse = NoopyTVEventListener(hass, api, coordinator, poll_interval=scan_interval)
    # Le TXT Bonjour annonce `sse=1/0`. Absent (anciennes apps) → on tente, le listener
    # abandonne proprement sur un 501. Explicitement à 0 → serveur sans flux push (iOS),
    # inutile d'ouvrir une connexion vouée à l'échec.
    if entry.data.get(CONF_SUPPORTS_SSE, True):
        sse.start()
    else:
        _LOGGER.debug("OneTV: le serveur annonce ne pas supporter SSE — polling seul")

    hass.data[DOMAIN][entry.entry_id] = {"api": api, "coordinator": coordinator, "sse": sse}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def handle_refresh(call: ServiceCall) -> None:
        _LOGGER.info("Service refresh appelé")
        await coordinator.async_request_refresh()

    async def handle_play_channel(call: ServiceCall) -> None:
        channel_id = call.data.get("channel_id")
        if not channel_id:
            _LOGGER.error("channel_id requis pour play_channel")
            return

        _LOGGER.info("Service play_channel appelé pour: %s", channel_id)
        success = await api.play_channel(channel_id)

        if success:
            _LOGGER.info("Chaîne changée avec succès")
            await coordinator.async_request_refresh()
        else:
            _LOGGER.error("Échec du changement de chaîne")

    async def _send_command(command: str, params: dict[str, Any] | None = None) -> None:
        try:
            result = await api.send_command(command, params)
        except NoopyTVAPIError as err:
            raise HomeAssistantError(f"OneTV: commande '{command}' échouée — {err}") from err
        if not result.get("success", False):
            raise HomeAssistantError(
                f"OneTV a refusé la commande '{command}': "
                f"{result.get('error') or result.get('message')}"
            )
        await coordinator.async_request_refresh()

    async def handle_play_movie(call: ServiceCall) -> None:
        params: dict[str, Any] = {"movieId": call.data["movie_id"]}
        if "resume_position" in call.data:
            params["resumePosition"] = float(call.data["resume_position"])
        await _send_command("playMovie", params)

    async def handle_play_episode(call: ServiceCall) -> None:
        params: dict[str, Any] = {
            "seriesId": call.data["series_id"],
            "seasonNumber": int(call.data["season"]),
            "episodeNumber": int(call.data["episode"]),
        }
        if "resume_position" in call.data:
            params["resumePosition"] = float(call.data["resume_position"])
        await _send_command("playEpisode", params)

    async def handle_send_command(call: ServiceCall) -> None:
        await _send_command(call.data["command"], call.data.get("params"))

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, handle_refresh)
    hass.services.async_register(DOMAIN, SERVICE_PLAY_CHANNEL, handle_play_channel)
    hass.services.async_register(
        DOMAIN, SERVICE_PLAY_MOVIE, handle_play_movie, schema=PLAY_MOVIE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_PLAY_EPISODE, handle_play_episode, schema=PLAY_EPISODE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SEND_COMMAND, handle_send_command, schema=SEND_COMMAND_SCHEMA
    )

    _async_remove_legacy_artwork_entity(hass, entry)
    _async_check_apple_tv_pairing(hass, entry)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.info(
        "OneTV v4.4.0 configuré: %s:%d (scan=%ss)",
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
        int(scan_interval.total_seconds()),
    )

    return True


def _async_remove_legacy_artwork_entity(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Supprime l'entité `image` des v4.1.x.

    ⚠️ La masquer ne suffisait pas : Home Assistant continue de la lister, suffixée
    « (Cachée) », dans la carte Capteurs — pour un doublon du visuel que le lecteur affiche
    déjà. Le `media_player` sert désormais lui-même l'image mise au carré, cette entité
    dédiée n'a plus de raison d'être.

    Sans ce nettoyage, elle resterait au registre en `unavailable` après la mise à jour.
    """
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("image", DOMAIN, f"{entry.entry_id}_artwork")
    if entity_id is not None:
        registry.async_remove(entity_id)
        _LOGGER.info("OneTV : entité %s supprimée (le lecteur porte désormais le visuel)", entity_id)


def _async_check_apple_tv_pairing(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Signale dans « Réparations » qu'aucune Apple TV n'est associée.

    Sans elle, `media_player.turn_on` échoue et l'app ne peut pas être lancée depuis Home
    Assistant — mais rien ne le signalait : l'utilisateur découvrait le problème le jour où
    son automatisation de retour à la maison ne faisait rien.
    """
    issue_id = f"no_apple_tv_{entry.entry_id}"
    if entry.options.get(CONF_APPLE_TV_ENTITY):
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="no_apple_tv_paired",
    )


def _cleanup_legacy_per_channel_sensors(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """v3.0.0 migration : supprimer les sensors par-channel des versions antérieures.

    En v2.x, chaque channel créait son propre sensor `<entry_id>_channel_<channel_id>`.
    Avec les playlists qui changent (UUIDs régénérés), les entities orphelines
    s'accumulaient (8500+ sensors observés sur 462 channels). v3.0.0 utilise un seul
    sensor agrégé `current_channel` pour la chaîne en cours.
    """
    registry = er.async_get(hass)
    legacy_unique_id_prefix = f"{entry.entry_id}_channel_"
    removed = 0
    for entity_id, entity_entry in list(registry.entities.items()):
        if entity_entry.config_entry_id != entry.entry_id:
            continue
        if entity_entry.platform != DOMAIN:
            continue
        unique_id = entity_entry.unique_id or ""
        # Match _channel_<id> mais pas _channel_selector (= la dropdown gardée)
        if unique_id.startswith(legacy_unique_id_prefix) and unique_id != f"{entry.entry_id}_channel_selector":
            registry.async_remove(entity_id)
            removed += 1
    if removed > 0:
        _LOGGER.warning(
            "OneTV v3.0.0 migration : %d ancien(s) sensor(s) par-channel supprimé(s) du registry. "
            "Les nouveaux dashboards utilisent `sensor.onetv_current_channel` agrégé.",
            removed,
        )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # ⚠️ Supprimer une entrée n'efface PAS les alertes de réparation qu'elle a créées :
        # elles restent affichées en désignant une entrée qui n'existe plus.
        ir.async_delete_issue(hass, DOMAIN, f"no_apple_tv_{entry.entry_id}")

        data = hass.data[DOMAIN].pop(entry.entry_id)
        sse: NoopyTVEventListener | None = data.get("sse")
        if sse is not None:
            await sse.stop()
        api: NoopyTVAPI = data["api"]
        await api.close()

        if not hass.data[DOMAIN]:
            for service in (
                SERVICE_REFRESH,
                SERVICE_PLAY_CHANNEL,
                SERVICE_PLAY_MOVIE,
                SERVICE_PLAY_EPISODE,
                SERVICE_SEND_COMMAND,
            ):
                hass.services.async_remove(DOMAIN, service)

    return unload_ok


class NoopyTVEventListener:
    """Maintient le flux SSE `/api/v1/events/stream` et déclenche un refresh à chaque event.

    Choix de conception : on ne PARSE PAS le payload des events pour construire l'état. Un
    event sert uniquement de signal « quelque chose a changé, va lire l'état ». Ça évite de
    dupliquer (et de désynchroniser) le décodage déjà fait par `/api/v1/player/state`, et le
    coût est nul — `async_request_refresh` est débouncé avec `immediate=True`, donc le premier
    zap déclenche un refresh instantané et une rafale est coalescée.

    Le flux n'existe que sur le serveur tvOS (iOS répond 501) : dans ce cas on abandonne
    définitivement et le polling normal reprend la main.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: NoopyTVAPI,
        coordinator: DataUpdateCoordinator,
        poll_interval: timedelta,
    ) -> None:
        self._hass = hass
        self._api = api
        self._coordinator = coordinator
        self._poll_interval = poll_interval
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._connected = False

    def start(self) -> None:
        if self._task is None:
            self._task = self._hass.async_create_background_task(
                self._run(), name=f"{DOMAIN}_sse"
            )

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def _set_poll_interval(self, interval: timedelta) -> None:
        if self._coordinator.update_interval == interval:
            return
        try:
            self._coordinator.update_interval = interval
        except Exception:  # pragma: no cover - dépend de la version de HA
            _LOGGER.debug("OneTV: impossible d'ajuster l'intervalle de polling", exc_info=True)

    @property
    def connected(self) -> bool:
        return self._connected

    @callback
    def _on_connected(self) -> None:
        """Le flux est établi → le polling n'est plus qu'un filet de sécurité.

        ⚠️ Ne PAS déduire la connexion de l'arrivée d'un event `snapshot` : le serveur
        étiquette son état initial selon la situation (il envoie `channel.change` quand une
        chaîne est déjà en cours), donc `snapshot` peut ne jamais arriver.
        """
        self._connected = True
        self._set_poll_interval(timedelta(seconds=SSE_FALLBACK_SCAN_INTERVAL_SECONDS))

    @callback
    def _on_event(self, event_name: str, _payload: dict[str, Any]) -> None:
        if event_name in ("heartbeat", "message"):
            return
        _LOGGER.debug("OneTV SSE: event %s → refresh", event_name)
        self._hass.async_create_task(self._coordinator.async_request_refresh())

    async def _run(self) -> None:
        delay = SSE_RECONNECT_MIN_DELAY
        while not self._stopping:
            try:
                await self._api.listen_events(self._on_event, self._on_connected)
                # Retour normal = flux fermé proprement par le serveur (app quittée).
                delay = SSE_RECONNECT_MIN_DELAY
            except NoopyTVAPIError as err:
                # 501/404 = serveur sans SSE (iOS, ou app trop ancienne) → inutile d'insister.
                if "501" in str(err) or "non disponible" in str(err) or "non supporté" in str(err):
                    _LOGGER.info("OneTV: pas de flux SSE (%s) — polling conservé", err)
                    self._set_poll_interval(self._poll_interval)
                    return
                _LOGGER.debug("OneTV SSE: %s", err)
            except NoopyTVConnectionError as err:
                _LOGGER.debug("OneTV SSE déconnecté: %s", err)
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - filet de sécurité
                _LOGGER.exception("OneTV SSE: erreur inattendue")

            # Flux perdu → l'app est peut-être fermée : on repasse en polling nominal.
            self._connected = False
            self._set_poll_interval(self._poll_interval)
            if self._stopping:
                return
            await asyncio.sleep(delay)
            delay = min(delay * 2, SSE_RECONNECT_MAX_DELAY)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


class NoopyTVDataUpdateCoordinator(DataUpdateCoordinator):

    def __init__(self, hass: HomeAssistant, api: NoopyTVAPI, update_interval: timedelta) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)
        self.api = api

    async def _async_update_data(self) -> dict:
        try:
            return await self.api.refresh_data()
        except NoopyTVConnectionError as err:
            raise UpdateFailed(f"OneTV non accessible: {err}") from err
        except NoopyTVAPIError as err:
            raise UpdateFailed(f"Erreur API: {err}") from err
        except Exception as err:
            _LOGGER.exception("Erreur inattendue lors de la mise à jour")
            raise UpdateFailed(f"Erreur inattendue: {err}") from err
