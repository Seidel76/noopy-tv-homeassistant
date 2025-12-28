"""Entités Select pour le changement de chaîne Noopy TV."""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

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


def slugify(text: str) -> str:
    """Convertit un texte en slug pour l'ID d'entité."""
    text = text.lower()
    text = re.sub(r'[àáâãäå]', 'a', text)
    text = re.sub(r'[èéêë]', 'e', text)
    text = re.sub(r'[ìíîï]', 'i', text)
    text = re.sub(r'[òóôõö]', 'o', text)
    text = re.sub(r'[ùúûü]', 'u', text)
    text = re.sub(r'[ç]', 'c', text)
    text = re.sub(r'[^a-z0-9]+', '_', text)
    text = text.strip('_')
    return text


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configure les entités select depuis une config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    
    entities: list[SelectEntity] = []
    
    # Sélecteur global (toutes les chaînes)
    entities.append(NoopyTVChannelSelect(coordinator, api, entry))
    
    # Récupérer les catégories depuis les données
    if coordinator.data:
        channels = coordinator.data.get("channels", {})
        categories: set[str] = set()
        
        for channel_data in channels.values():
            category = channel_data.get("category", "")
            if category:
                categories.add(category)
        
        # Créer un sélecteur par catégorie
        for category in sorted(categories):
            entities.append(NoopyTVCategorySelect(coordinator, api, entry, category))
            _LOGGER.debug("Création du sélecteur pour la catégorie: %s", category)
    
    async_add_entities(entities)
    _LOGGER.info("Créé %d sélecteurs de chaînes", len(entities))


class NoopyTVChannelSelect(CoordinatorEntity, SelectEntity):
    """Entité Select pour changer de chaîne sur Noopy TV (toutes les chaînes)."""
    
    _attr_has_entity_name = True
    _attr_translation_key = "channel_selector"
    _attr_icon = "mdi:television"
    
    def __init__(self, coordinator, api, entry: ConfigEntry) -> None:
        """Initialise le sélecteur de chaînes."""
        super().__init__(coordinator)
        self._api = api
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_channel_selector"
        self._attr_name = "Toutes les chaînes"
        self._channel_map: dict[str, str] = {}  # name -> id
    
    @property
    def entity_picture(self) -> str | None:
        """Retourne l'URL du logo de la chaîne en cours via le proxy (redimensionné)."""
        if not self.coordinator.data:
            return None
        
        player = self.coordinator.data.get("player", {})
        current_channel = player.get("current_channel")
        
        if current_channel:
            logo_url = current_channel.get("logo_url")
            if logo_url:
                host = self._entry.data.get("host", "")
                port = self._entry.data.get("port", 8765)
                encoded_url = quote(logo_url, safe="")
                return f"http://{host}:{port}/api/v1/proxy/image?url={encoded_url}&size=48"
        
        return None
    
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
        attrs["total_channels"] = len(self.options)
        
        current_channel = player.get("current_channel")
        if current_channel:
            attrs[ATTR_CURRENT_CHANNEL] = current_channel.get("name")
            attrs[ATTR_CURRENT_CHANNEL_ID] = current_channel.get("id")
            attrs[ATTR_CURRENT_CHANNEL_LOGO] = current_channel.get("logo_url")
            attrs["current_category"] = current_channel.get("category", "")
            
            logo_url = current_channel.get("logo_url")
            if logo_url:
                host = self._entry.data.get("host", "")
                port = self._entry.data.get("port", 8765)
                encoded_url = quote(logo_url, safe="")
                attrs["logo_proxy_url"] = f"http://{host}:{port}/api/v1/proxy/image?url={encoded_url}&size=80"
            
            current_prog = current_channel.get("current_program")
            if current_prog:
                attrs["current_program"] = current_prog.get("title")
                attrs["progress_percent"] = current_prog.get("progress_percent", 0)
        
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
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Échec du changement de chaîne: %s", option)
    
    @callback
    def _handle_coordinator_update(self) -> None:
        """Gère la mise à jour du coordinateur."""
        self.async_write_ha_state()


class NoopyTVCategorySelect(CoordinatorEntity, SelectEntity):
    """Entité Select pour changer de chaîne dans une catégorie spécifique."""
    
    _attr_has_entity_name = True
    _attr_icon = "mdi:television-guide"
    
    def __init__(self, coordinator, api, entry: ConfigEntry, category: str) -> None:
        """Initialise le sélecteur de chaînes par catégorie."""
        super().__init__(coordinator)
        self._api = api
        self._entry = entry
        self._category = category
        self._attr_unique_id = f"{entry.entry_id}_category_{slugify(category)}"
        self._attr_name = category
        self._channel_map: dict[str, str] = {}  # name -> id
    
    @property
    def entity_picture(self) -> str | None:
        """Retourne l'URL du logo de la chaîne en cours si elle est dans cette catégorie."""
        if not self.coordinator.data:
            return None
        
        player = self.coordinator.data.get("player", {})
        current_channel = player.get("current_channel")
        
        if current_channel and current_channel.get("category") == self._category:
            logo_url = current_channel.get("logo_url")
            if logo_url:
                host = self._entry.data.get("host", "")
                port = self._entry.data.get("port", 8765)
                encoded_url = quote(logo_url, safe="")
                return f"http://{host}:{port}/api/v1/proxy/image?url={encoded_url}&size=48"
        
        return None
    
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
        """Retourne la liste des chaînes de cette catégorie."""
        if not self.coordinator.data:
            return []
        
        channels = self.coordinator.data.get("channels", {})
        
        self._channel_map = {}
        names = []
        for channel_id, channel_data in channels.items():
            if channel_data.get("category") == self._category:
                name = channel_data.get("name", "")
                if name:
                    self._channel_map[name] = channel_id
                    names.append(name)
        
        return sorted(names)
    
    @property
    def current_option(self) -> str | None:
        """Retourne la chaîne actuellement sélectionnée si elle est dans cette catégorie."""
        if not self.coordinator.data:
            return None
        
        player = self.coordinator.data.get("player", {})
        current_channel = player.get("current_channel")
        
        if current_channel and current_channel.get("category") == self._category:
            return current_channel.get("name")
        
        return None
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Retourne les attributs supplémentaires."""
        attrs: dict[str, Any] = {
            "category": self._category,
            "channels_count": len(self.options),
        }
        
        if not self.coordinator.data:
            return attrs
        
        player = self.coordinator.data.get("player", {})
        current_channel = player.get("current_channel")
        
        # Indiquer si la chaîne en cours est dans cette catégorie
        if current_channel:
            is_current_category = current_channel.get("category") == self._category
            attrs["is_playing_in_category"] = is_current_category
            
            if is_current_category:
                attrs[ATTR_CURRENT_CHANNEL] = current_channel.get("name")
                attrs[ATTR_PLAYER_ACTIVE] = player.get("is_active", False)
                
                logo_url = current_channel.get("logo_url")
                if logo_url:
                    host = self._entry.data.get("host", "")
                    port = self._entry.data.get("port", 8765)
                    encoded_url = quote(logo_url, safe="")
                    attrs["logo_proxy_url"] = f"http://{host}:{port}/api/v1/proxy/image?url={encoded_url}&size=80"
                
                current_prog = current_channel.get("current_program")
                if current_prog:
                    attrs["current_program"] = current_prog.get("title")
                    attrs["progress_percent"] = current_prog.get("progress_percent", 0)
        
        return attrs
    
    async def async_select_option(self, option: str) -> None:
        """Change la chaîne sélectionnée."""
        channel_id = self._channel_map.get(option)
        
        if not channel_id:
            _LOGGER.error("Chaîne non trouvée dans %s: %s", self._category, option)
            return
        
        _LOGGER.info("Changement de chaîne vers: %s (catégorie: %s)", option, self._category)
        
        success = await self._api.play_channel(channel_id)
        
        if success:
            _LOGGER.info("Chaîne changée avec succès: %s", option)
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Échec du changement de chaîne: %s", option)
    
    @callback
    def _handle_coordinator_update(self) -> None:
        """Gère la mise à jour du coordinateur."""
        self.async_write_ha_state()
