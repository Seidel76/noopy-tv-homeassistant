"""Entité Select pour le changement de chaîne Noopy TV."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_CURRENT_CHANNEL,
    ATTR_CURRENT_CHANNEL_ID,
    ATTR_CURRENT_CHANNEL_LOGO,
    ATTR_PLAYER_ACTIVE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configure les entités select depuis une config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    
    async_add_entities([NoopyTVChannelSelect(coordinator, api, entry)])


class NoopyTVChannelSelect(CoordinatorEntity, SelectEntity):
    """Entité Select pour changer de chaîne sur Noopy TV."""
    
    _attr_has_entity_name = True
    _attr_translation_key = "channel_selector"
    _attr_icon = "mdi:television"
    
    def __init__(self, coordinator, api, entry: ConfigEntry) -> None:
        """Initialise le sélecteur de chaînes."""
        super().__init__(coordinator)
        self._api = api
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_channel_selector"
        self._current_option: str | None = None
        self._channel_map: dict[str, str] = {}  # name -> id
    
    @property
    def device_info(self) -> dict[str, Any]:
        """Retourne les informations sur l'appareil."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Noopy TV",
            "manufacturer": "Noopy TV",
            "model": "Apple TV",
            "sw_version": "1.0",
        }
    
    @property
    def options(self) -> list[str]:
        """Retourne la liste des chaînes disponibles."""
        if not self.coordinator.data:
            return []
        
        channels = self.coordinator.data.get("channels", {})
        
        # Créer la map name -> id et retourner les noms
        self._channel_map = {}
        names = []
        for channel_id, channel_data in channels.items():
            name = channel_data.get("name", "")
            if name:
                self._channel_map[name] = channel_id
                names.append(name)
        
        return sorted(names)
    
    @property
    def current_option(self) -> str | None:
        """Retourne la chaîne actuellement sélectionnée."""
        if not self.coordinator.data:
            return None
        
        player = self.coordinator.data.get("player", {})
        current_channel = player.get("current_channel")
        
        if current_channel:
            return current_channel.get("name")
        
        return None
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Retourne les attributs supplémentaires."""
        attrs: dict[str, Any] = {}
        
        if not self.coordinator.data:
            return attrs
        
        player = self.coordinator.data.get("player", {})
        
        attrs[ATTR_PLAYER_ACTIVE] = player.get("is_active", False)
        
        current_channel = player.get("current_channel")
        if current_channel:
            attrs[ATTR_CURRENT_CHANNEL] = current_channel.get("name")
            attrs[ATTR_CURRENT_CHANNEL_ID] = current_channel.get("id")
            attrs[ATTR_CURRENT_CHANNEL_LOGO] = current_channel.get("logo_url")
            
            # Programme en cours
            current_prog = current_channel.get("current_program")
            if current_prog:
                attrs["current_program"] = current_prog.get("title")
                attrs["current_program_progress"] = current_prog.get("progress_percent", 0)
        
        return attrs
    
    async def async_select_option(self, option: str) -> None:
        """Change la chaîne sélectionnée."""
        channel_id = self._channel_map.get(option)
        
        if not channel_id:
            _LOGGER.error("Chaîne non trouvée: %s", option)
            return
        
        _LOGGER.info("Changement de chaîne vers: %s (ID: %s)", option, channel_id)
        
        success = await self._api.play_channel(channel_id)
        
        if success:
            _LOGGER.info("Chaîne changée avec succès: %s", option)
            # Rafraîchir les données
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Échec du changement de chaîne: %s", option)
    
    @callback
    def _handle_coordinator_update(self) -> None:
        """Gère la mise à jour du coordinateur."""
        self.async_write_ha_state()

