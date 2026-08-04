"""Diagnostics téléchargeables depuis la fiche de l'intégration.

Évite les allers-retours « envoie-moi tes logs » : tout ce qui sert à comprendre un
problème (identité de l'appareil, état du flux push, cadence de sondage, forme du dernier
payload) est réuni en un fichier.

⚠️ `api_key` est expurgée : elle donne un accès complet à l'API de l'app sur le réseau local.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, DOMAIN

TO_REDACT = {CONF_API_KEY, "api_key", "apiKey"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    sse = data.get("sse")

    payload = coordinator.data or {}
    channels = payload.get("channels") or {}
    # On n'exporte PAS les 942 chaînes : un échantillon suffit à diagnostiquer un problème
    # de forme, et le fichier reste lisible.
    sample = [dict(list(channels.values())[i]) for i in range(min(3, len(channels)))]

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
            "unique_id": entry.unique_id,
        },
        "server_info": async_redact_data(dict(getattr(api, "info", {}) or {}), TO_REDACT),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
        },
        "push": {
            "connected": bool(sse is not None and sse.connected),
        },
        "counts": {
            "channels": len(channels),
            "categories": len(payload.get("categories") or {}),
        },
        "player": payload.get("player"),
        "playback_state": payload.get("playback_state"),
        "channels_sample": sample,
    }
