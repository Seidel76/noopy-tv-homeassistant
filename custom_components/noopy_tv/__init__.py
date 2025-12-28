"""Intégration Noopy TV pour Home Assistant.

Cette intégration permet de découvrir automatiquement l'app Noopy TV
sur votre réseau local et de récupérer les chaînes TV et programmes EPG.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NoopyTVAPI, NoopyTVAPIError, NoopyTVConnectionError
from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
    SERVICE_REFRESH,
    SERVICE_PLAY_CHANNEL,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configure l'intégration depuis une config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Créer le client API
    session = async_get_clientsession(hass)
    api = NoopyTVAPI(
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, DEFAULT_PORT),
        session=session,
    )
    
    # Tester la connexion
    try:
        if not await api.test_connection():
            _LOGGER.error("Impossible de se connecter à Noopy TV")
            return False
    except NoopyTVConnectionError as err:
        _LOGGER.error("Erreur de connexion: %s", err)
        return False
    except NoopyTVAPIError as err:
        _LOGGER.error("Erreur API: %s", err)
        return False
    
    # Créer le coordinateur de données (intervalle en secondes)
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    if isinstance(scan_interval, int):
        scan_interval = timedelta(seconds=scan_interval)
    
    coordinator = NoopyTVDataUpdateCoordinator(
        hass,
        api=api,
        update_interval=scan_interval,
    )
    
    # Premier chargement des données
    await coordinator.async_config_entry_first_refresh()
    
    # Stocker le coordinateur
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
    }
    
    # Configurer les plateformes
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Enregistrer les services
    async def handle_refresh(call: ServiceCall) -> None:
        """Gère le service de rafraîchissement."""
        _LOGGER.info("Service refresh appelé")
        await coordinator.async_request_refresh()
    
    async def handle_play_channel(call: ServiceCall) -> None:
        """Gère le service de changement de chaîne."""
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
    
    # Écouter les changements d'options
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    
    _LOGGER.info("Noopy TV configuré avec succès: %s:%d", entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT))
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge une config entry."""
    # Décharger les plateformes
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Fermer l'API et nettoyer
        data = hass.data[DOMAIN].pop(entry.entry_id)
        api: NoopyTVAPI = data["api"]
        await api.close()
        
        # Supprimer les services si c'est la dernière entry
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_REFRESH)
            hass.services.async_remove(DOMAIN, SERVICE_PLAY_CHANNEL)
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Recharge une config entry après changement d'options."""
    await hass.config_entries.async_reload(entry.entry_id)


class NoopyTVDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinateur de mise à jour des données Noopy TV."""
    
    def __init__(
        self,
        hass: HomeAssistant,
        api: NoopyTVAPI,
        update_interval: timedelta,
    ) -> None:
        """Initialise le coordinateur."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.api = api
    
    async def _async_update_data(self) -> dict:
        """Récupère les données depuis l'API."""
        try:
            return await self.api.refresh_data()
        
        except NoopyTVConnectionError as err:
            raise UpdateFailed(f"Noopy TV non accessible: {err}") from err
        except NoopyTVAPIError as err:
            raise UpdateFailed(f"Erreur API: {err}") from err
        except Exception as err:
            _LOGGER.exception("Erreur inattendue lors de la mise à jour")
            raise UpdateFailed(f"Erreur inattendue: {err}") from err
