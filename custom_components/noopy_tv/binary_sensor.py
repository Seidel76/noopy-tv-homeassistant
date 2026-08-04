"""Binary sensor OneTV : l'application répond-elle ?

⚡️ v4.0.0 — Sans cette entité, savoir si l'app tourne obligeait à tester si les AUTRES
entités étaient `unavailable`, ce qui n'est pas exprimable proprement dans une condition
d'automatisation (et `media_player.apple_tv` d'Apple TV, lui, continue d'annoncer
`app_name = "OneTV Connect"` alors que l'app est suspendue et injoignable — cf. règle 232).
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([NoopyTVAvailabilityBinarySensor(coordinator, entry)])


class NoopyTVAvailabilityBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """`on` quand le serveur HTTP de l'app OneTV répond."""

    _attr_has_entity_name = True
    _attr_name = "Application accessible"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_app_available"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="OneTV",
            manufacturer="OneTV",
            model="IPTV App",
        )

    @property
    def available(self) -> bool:
        """Jamais `unavailable` : une sonde de disponibilité qui disparaît ne sert à rien."""
        return True

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.last_update_success)
