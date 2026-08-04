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
from .device import build_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [NoopyTVAvailabilityBinarySensor(data["coordinator"], entry, data.get("sse"))]
    )


class NoopyTVAvailabilityBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """`on` quand le serveur HTTP de l'app OneTV répond."""

    _attr_has_entity_name = True
    _attr_name = "Application accessible"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry: ConfigEntry, sse=None) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._sse = sse
        self._attr_unique_id = f"{entry.entry_id}_app_available"

    @property
    def device_info(self) -> DeviceInfo:
        return build_device_info(self._entry)

    @property
    def available(self) -> bool:
        """Jamais `unavailable` : une sonde de disponibilité qui disparaît ne sert à rien."""
        return True

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.last_update_success)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose l'état du flux push : sans ça, savoir s'il tient exige de lire les logs."""
        return {
            "push_connected": bool(self._sse is not None and self._sse.connected),
            "update_interval_seconds": int(
                self.coordinator.update_interval.total_seconds()
            )
            if self.coordinator.update_interval
            else None,
        }
