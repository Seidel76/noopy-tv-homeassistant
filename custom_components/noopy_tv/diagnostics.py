"""Diagnostics téléchargeables depuis la fiche de l'intégration.

Évite les allers-retours « envoie-moi tes logs » : tout ce qui sert à comprendre un
problème (identité de l'appareil, état du flux push, cadence de sondage, forme du dernier
payload) est réuni en un fichier.

⚠️ Un diagnostic finit joint à des tickets GitHub PUBLICS. On expurge donc :
- `api_key` (accès complet à l'API de l'app sur le réseau local) ;
- toute URL : celles des flux portent l'identifiant et le mot de passe de l'abonné
  (`/live/<utilisateur>/<mot de passe>/<id>.ts`), celles des visuels Plex/Emby/Jellyfin leur
  jeton. Expurgation par CLÉ sur tout le fichier, puis filet par VALEUR (`redact_urls`) pour
  une clé d'URL que l'app ajouterait sous un nom inconnu.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, DOMAIN
from .redact import STREAM_URL_KEYS, redact_urls

TO_REDACT = {
    CONF_API_KEY,
    "api_key",
    "apiKey",
    "token",
    "access_token",
    "accessToken",
    "username",
    "password",
    *STREAM_URL_KEYS,
    "url",
    "logo_url",
    "logoURL",
    "poster_url",
    "posterURL",
    "backdrop_url",
    "backdropURL",
    "icon_url",
    "iconURL",
    "current_program_icon",
    "catchup_url",
    "catchupURL",
}


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

    diagnostics = {
        "entry": {
            "data": dict(entry.data),
            "options": dict(entry.options),
            "unique_id": entry.unique_id,
        },
        "server_info": dict(getattr(api, "info", {}) or {}),
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
    return redact_urls(async_redact_data(diagnostics, TO_REDACT))
