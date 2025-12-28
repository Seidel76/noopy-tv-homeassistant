"""Sensors pour l'intégration Noopy TV."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_CATEGORY,
    ATTR_CURRENT_PROGRAM,
    ATTR_CURRENT_PROGRAM_DESCRIPTION,
    ATTR_CURRENT_PROGRAM_END,
    ATTR_CURRENT_PROGRAM_ICON,
    ATTR_CURRENT_PROGRAM_START,
    ATTR_LOGO_URL,
    ATTR_PROGRESS_PERCENT,
    ATTR_STREAM_ID,
    ATTR_STREAM_URL,
    ATTR_TOTAL_CATEGORIES,
    ATTR_TOTAL_CHANNELS,
    ATTR_TVG_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configure les sensors depuis la config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    
    entities: list[SensorEntity] = []
    
    # Sensor de statistiques globales
    entities.append(NoopyTVStatsSensor(coordinator, entry))
    
    # Un sensor par chaîne
    if coordinator.data and "channels" in coordinator.data:
        for channel_id, channel_data in coordinator.data["channels"].items():
            entities.append(
                NoopyTVChannelSensor(
                    coordinator,
                    entry,
                    channel_id,
                    channel_data["name"],
                )
            )
    
    async_add_entities(entities)
    
    # Écouter les nouvelles chaînes
    @callback
    def async_add_new_channels() -> None:
        """Ajoute les nouvelles chaînes détectées."""
        if not coordinator.data or "channels" not in coordinator.data:
            return
        
        existing_ids = {
            entity.channel_id
            for entity in entities
            if isinstance(entity, NoopyTVChannelSensor)
        }
        
        new_entities = []
        for channel_id, channel_data in coordinator.data["channels"].items():
            if channel_id not in existing_ids:
                new_entity = NoopyTVChannelSensor(
                    coordinator,
                    entry,
                    channel_id,
                    channel_data["name"],
                )
                new_entities.append(new_entity)
                entities.append(new_entity)
        
        if new_entities:
            async_add_entities(new_entities)
    
    # S'abonner aux mises à jour pour détecter les nouvelles chaînes
    entry.async_on_unload(
        coordinator.async_add_listener(async_add_new_channels)
    )


class NoopyTVStatsSensor(CoordinatorEntity, SensorEntity):
    """Sensor de statistiques globales Noopy TV."""
    
    _attr_has_entity_name = True
    _attr_name = "Statistiques"
    _attr_icon = "mdi:television-box"
    
    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialise le sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_stats"
    
    @property
    def device_info(self) -> DeviceInfo:
        """Retourne les infos du device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Noopy TV",
            manufacturer="Noopy TV",
            model="IPTV App",
            sw_version="1.0.0",
        )
    
    @property
    def native_value(self) -> int | None:
        """Retourne le nombre total de chaînes."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(ATTR_TOTAL_CHANNELS, 0)
    
    @property
    def native_unit_of_measurement(self) -> str:
        """Retourne l'unité."""
        return "chaînes"
    
    @property
    def state_class(self) -> SensorStateClass:
        """Retourne la classe d'état."""
        return SensorStateClass.MEASUREMENT
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Retourne les attributs supplémentaires."""
        if not self.coordinator.data:
            return {}
        
        data = self.coordinator.data
        attrs = {
            ATTR_TOTAL_CHANNELS: data.get(ATTR_TOTAL_CHANNELS, 0),
            ATTR_TOTAL_CATEGORIES: data.get(ATTR_TOTAL_CATEGORIES, 0),
        }
        
        # Ajouter la liste des catégories
        if "categories" in data:
            attrs["categories"] = list(data["categories"].keys())
        
        return attrs


class NoopyTVChannelSensor(CoordinatorEntity, SensorEntity):
    """Sensor pour une chaîne TV Noopy TV."""
    
    _attr_has_entity_name = True
    _attr_icon = "mdi:television-classic"
    
    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        channel_id: str,
        name: str,
    ) -> None:
        """Initialise le sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._channel_id = channel_id
        self._name = name
        self._attr_unique_id = f"{entry.entry_id}_channel_{channel_id}"
        self._attr_name = name
    
    @property
    def channel_id(self) -> str:
        """Retourne l'ID de la chaîne."""
        return self._channel_id
    
    @property
    def device_info(self) -> DeviceInfo:
        """Retourne les infos du device."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="Noopy TV",
            manufacturer="Noopy TV",
            model="IPTV App",
            sw_version="1.0.0",
        )
    
    @property
    def _channel_data(self) -> dict[str, Any] | None:
        """Retourne les données de la chaîne."""
        if not self.coordinator.data or "channels" not in self.coordinator.data:
            return None
        return self.coordinator.data["channels"].get(self._channel_id)
    
    @property
    def available(self) -> bool:
        """Retourne si le sensor est disponible."""
        return self.coordinator.last_update_success and self._channel_data is not None
    
    @property
    def native_value(self) -> str | None:
        """Retourne le programme en cours."""
        data = self._channel_data
        if not data:
            return None
        return data.get(ATTR_CURRENT_PROGRAM, "Aucun programme")
    
    @property
    def entity_picture(self) -> str | None:
        """Retourne le logo de la chaîne."""
        data = self._channel_data
        if not data:
            return None
        # Priorité à l'icône du programme, sinon le logo de la chaîne
        return data.get(ATTR_CURRENT_PROGRAM_ICON) or data.get(ATTR_LOGO_URL)
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Retourne les attributs supplémentaires."""
        data = self._channel_data
        if not data:
            return {}
        
        attrs = {
            "channel_id": data.get("id"),
            "channel_name": data.get("name"),
            ATTR_LOGO_URL: data.get(ATTR_LOGO_URL),
            ATTR_STREAM_URL: data.get(ATTR_STREAM_URL),
            ATTR_CATEGORY: data.get("category"),
            ATTR_TVG_ID: data.get("tvg_id"),
            ATTR_STREAM_ID: data.get("stream_id"),
            "has_catchup": data.get("has_catchup", False),
            "catchup_days": data.get("catchup_days", 0),
        }
        
        # Infos EPG programme en cours
        if ATTR_CURRENT_PROGRAM in data:
            attrs.update({
                ATTR_CURRENT_PROGRAM: data.get(ATTR_CURRENT_PROGRAM),
                ATTR_CURRENT_PROGRAM_START: data.get(ATTR_CURRENT_PROGRAM_START),
                ATTR_CURRENT_PROGRAM_END: data.get(ATTR_CURRENT_PROGRAM_END),
                ATTR_CURRENT_PROGRAM_DESCRIPTION: data.get(ATTR_CURRENT_PROGRAM_DESCRIPTION),
                ATTR_CURRENT_PROGRAM_ICON: data.get(ATTR_CURRENT_PROGRAM_ICON),
                ATTR_PROGRESS_PERCENT: data.get(ATTR_PROGRESS_PERCENT),
            })
        
        return attrs
