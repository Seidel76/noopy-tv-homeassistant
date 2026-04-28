from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NoopyTVAPI, NoopyTVAPIError, NoopyTVConnectionError
from .const import (
    CONF_API_KEY,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SERVICE_REFRESH,
    SERVICE_PLAY_CHANNEL,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SELECT]


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

    hass.data[DOMAIN][entry.entry_id] = {"api": api, "coordinator": coordinator}

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

    hass.services.async_register(DOMAIN, SERVICE_REFRESH, handle_refresh)
    hass.services.async_register(DOMAIN, SERVICE_PLAY_CHANNEL, handle_play_channel)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.info(
        "OneTV v3.0.0 configuré: %s:%d (scan=%ss)",
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
        int(scan_interval.total_seconds()),
    )

    return True


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
        data = hass.data[DOMAIN].pop(entry.entry_id)
        api: NoopyTVAPI = data["api"]
        await api.close()

        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_REFRESH)
            hass.services.async_remove(DOMAIN, SERVICE_PLAY_CHANNEL)

    return unload_ok


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
