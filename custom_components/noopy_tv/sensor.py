"""OneTV sensors v3.0.0 — design agrégé.

Avant (v2.x): un sensor par chaîne → 1000+ entities pour grosses playlists, recorder
HA explose, UI inutilisable. Désormais : 2 sensors globaux (stats + current_channel)
qui exposent toutes les infos via attributes.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    ATTR_PLAYER_ACTIVE,
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
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]

    entities: list[SensorEntity] = [
        NoopyTVStatsSensor(coordinator, entry),
        NoopyTVCurrentChannelSensor(coordinator, entry),
    ]
    async_add_entities(entities)
    _LOGGER.info("OneTV v3.0.0 : %d sensor(s) global(aux) créé(s) (vs N+1 par chaîne en v2.x)", len(entities))


class NoopyTVStatsSensor(CoordinatorEntity, SensorEntity):
    """Stats globales : nombre total de chaînes, catégories, etc."""

    _attr_has_entity_name = True
    _attr_name = "Statistiques"
    _attr_icon = "mdi:television-box"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_stats"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="OneTV",
            manufacturer="OneTV",
            model="IPTV App",
            sw_version="3.0.0",
        )

    @property
    def native_value(self) -> int | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(ATTR_TOTAL_CHANNELS, 0)

    @property
    def native_unit_of_measurement(self) -> str:
        return "chaînes"

    @property
    def state_class(self) -> SensorStateClass:
        return SensorStateClass.MEASUREMENT

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}

        data = self.coordinator.data
        attrs: dict[str, Any] = {
            ATTR_TOTAL_CHANNELS: data.get(ATTR_TOTAL_CHANNELS, 0),
            ATTR_TOTAL_CATEGORIES: data.get(ATTR_TOTAL_CATEGORIES, 0),
        }

        if "categories" in data:
            attrs["categories"] = list(data["categories"].keys())

        return attrs


class NoopyTVCurrentChannelSensor(CoordinatorEntity, SensorEntity):
    """Sensor agrégé : la chaîne en cours de lecture + son programme.

    Remplace les 1000+ sensors par-chaîne de v2.x. Tout est dans `extra_state_attributes`
    pour permettre aux templates HA / cards Lovelace d'extraire ce qu'ils veulent.
    """

    _attr_has_entity_name = True
    _attr_name = "Chaîne en cours"
    _attr_icon = "mdi:television-classic"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_current_channel"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="OneTV",
            manufacturer="OneTV",
            model="IPTV App",
            sw_version="3.0.0",
        )

    def _current_channel(self) -> dict[str, Any] | None:
        if not self.coordinator.data:
            return None
        player = self.coordinator.data.get("player", {}) or {}
        return player.get("current_channel")

    @property
    def native_value(self) -> str | None:
        ch = self._current_channel()
        if not ch:
            return "Aucune lecture"
        return ch.get("name") or "Aucune lecture"

    @property
    def entity_picture(self) -> str | None:
        ch = self._current_channel()
        if not ch:
            return None
        logo_url = ch.get("logo_url")
        if not logo_url:
            return None
        host = self._entry.data.get("host", "")
        port = self._entry.data.get("port", 8765)
        encoded = quote(logo_url, safe="")
        return f"http://{host}:{port}/api/v1/proxy/image?url={encoded}&size=80"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}

        player = self.coordinator.data.get("player", {}) or {}
        attrs: dict[str, Any] = {
            ATTR_PLAYER_ACTIVE: player.get("is_active", False),
        }

        ch = self._current_channel()
        if not ch:
            return attrs

        # Channel-level attributes
        attrs["channel_id"] = ch.get("id")
        attrs["channel_name"] = ch.get("name")
        attrs[ATTR_LOGO_URL] = ch.get("logo_url")
        attrs[ATTR_STREAM_URL] = ch.get("stream_url")
        attrs[ATTR_CATEGORY] = ch.get("category")
        attrs[ATTR_TVG_ID] = ch.get("tvg_id")
        attrs[ATTR_STREAM_ID] = ch.get("stream_id")

        # Logo proxy URL (avoids CORS / auth headers in HA frontend)
        logo_url = ch.get("logo_url")
        if logo_url:
            host = self._entry.data.get("host", "")
            port = self._entry.data.get("port", 8765)
            encoded = quote(logo_url, safe="")
            attrs["logo_proxy_url"] = f"http://{host}:{port}/api/v1/proxy/image?url={encoded}&size=80"

        # Current programme attributes (guide EPG)
        prog = ch.get("current_program")
        if prog:
            attrs[ATTR_CURRENT_PROGRAM] = prog.get("title")
            attrs[ATTR_CURRENT_PROGRAM_START] = prog.get("start")
            attrs[ATTR_CURRENT_PROGRAM_END] = prog.get("end")
            attrs[ATTR_CURRENT_PROGRAM_DESCRIPTION] = prog.get("description")
            attrs[ATTR_CURRENT_PROGRAM_ICON] = prog.get("icon_url")
            attrs[ATTR_PROGRESS_PERCENT] = prog.get("progress_percent", 0)

        return attrs
