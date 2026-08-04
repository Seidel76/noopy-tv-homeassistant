"""Boutons OneTV : retour au direct, rafraîchissement.

`seekToLive` est implémentée côté app depuis toujours et n'était exposée nulle part : après
une pause ou un retour arrière en direct, revenir au bord du flux imposait de prendre la
télécommande.
"""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import NoopyTVAPI, NoopyTVAPIError
from .const import DOMAIN
from .device import build_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            NoopyTVGoLiveButton(data["coordinator"], data["api"], entry),
            NoopyTVRefreshButton(data["coordinator"], data["api"], entry),
        ]
    )


class _NoopyTVButtonBase(CoordinatorEntity, ButtonEntity):
    def __init__(self, coordinator, api: NoopyTVAPI, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._api = api
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return build_device_info(self._entry, getattr(self._api, "info", None))


class NoopyTVGoLiveButton(_NoopyTVButtonBase):
    """Ramène la lecture au bord du direct (annule pause et différé)."""

    _attr_has_entity_name = True
    _attr_name = "Retour au direct"
    _attr_icon = "mdi:broadcast"

    def __init__(self, coordinator, api: NoopyTVAPI, entry: ConfigEntry) -> None:
        super().__init__(coordinator, api, entry)
        self._attr_unique_id = f"{entry.entry_id}_go_live"

    @property
    def available(self) -> bool:
        """Seulement pertinent sur un contenu en direct effectivement en cours."""
        if not self.coordinator.last_update_success or not self.coordinator.data:
            return False
        state = self.coordinator.data.get("playback_state") or {}
        return bool(state.get("isPlayerActive")) and bool(state.get("isLive"))

    async def async_press(self) -> None:
        try:
            result = await self._api.send_command("seekToLive")
        except NoopyTVAPIError as err:
            raise HomeAssistantError(f"OneTV : retour au direct impossible — {err}") from err
        if not result.get("success", False):
            raise HomeAssistantError(
                f"OneTV a refusé le retour au direct : {result.get('error') or result.get('message')}"
            )
        await self.coordinator.async_request_refresh()


class NoopyTVRefreshButton(_NoopyTVButtonBase):
    """Force une relecture immédiate de l'état depuis l'app."""

    _attr_has_entity_name = True
    _attr_name = "Rafraîchir"
    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, api: NoopyTVAPI, entry: ConfigEntry) -> None:
        super().__init__(coordinator, api, entry)
        self._attr_unique_id = f"{entry.entry_id}_refresh"

    @property
    def available(self) -> bool:
        """Toujours disponible : c'est le bouton qu'on veut pouvoir presser quand ça coince."""
        return True

    async def async_press(self) -> None:
        await self.coordinator.async_refresh()
