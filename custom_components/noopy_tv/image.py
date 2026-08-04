"""Logo de la chaîne en cours, en entité `image` réutilisable.

Le logo n'était disponible que comme `entity_picture` du sensor et du media_player —
c'est-à-dire pratiquement inexploitable ailleurs (une carte Lovelace personnalisée, une
notification, un panneau mural…). Une entité `image` donne une URL stable côté Home Assistant
(`/api/image_proxy/...`), servie par HA lui-même : le destinataire n'a pas besoin d'atteindre
l'Apple TV.

L'URL source passe par le proxy d'images de l'app (`/api/v1/proxy/image`), qui a seul accès
aux CDN de logos et applique le redimensionnement.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .device import build_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([NoopyTVArtworkImage(hass, data["coordinator"], data["api"], entry)])


class NoopyTVArtworkImage(CoordinatorEntity, ImageEntity):
    """Logo de la chaîne en cours — ou affiche du film / de l'épisode en VOD."""

    _attr_has_entity_name = True
    _attr_name = "Logo de la chaîne"

    def __init__(self, hass: HomeAssistant, coordinator, api, entry: ConfigEntry) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        self._api = api
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_artwork"
        self._current_source: str | None = None
        self._refresh_source()

    @property
    def device_info(self):
        return build_device_info(self._entry, getattr(self._api, "info", None))

    def _player(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("player", {}) or {}

    def _state_payload(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("playback_state", {}) or {}

    def _proxy(self, raw_url: str, size: int) -> str:
        host = self._entry.data.get("host", "")
        port = self._entry.data.get("port", 8765)
        return f"http://{host}:{port}/api/v1/proxy/image?url={quote(raw_url, safe='')}&size={size}"

    def _source_url(self) -> str | None:
        state = self._state_payload()
        if state.get("contentType") in ("movie", "episode") and state.get("posterURL"):
            return self._proxy(str(state["posterURL"]), size=400)
        if state.get("logoURL"):
            return self._proxy(str(state["logoURL"]), size=300)
        channel = self._player().get("current_channel") or {}
        if channel.get("logo_url"):
            return self._proxy(str(channel["logo_url"]), size=300)
        return None

    def _refresh_source(self) -> bool:
        """Met à jour l'URL. Retourne True si elle a changé."""
        url = self._source_url()
        if url == self._current_source:
            return False
        self._current_source = url
        self._attr_image_url = url
        # ⚠️ `image_last_updated` est ce qui invalide le cache de Home Assistant : sans
        # horodatage neuf, l'ancien logo resterait affiché après un zap.
        self._attr_image_last_updated = dt_util.utcnow()
        return True

    @callback
    def _handle_coordinator_update(self) -> None:
        self._refresh_source()
        super()._handle_coordinator_update()
