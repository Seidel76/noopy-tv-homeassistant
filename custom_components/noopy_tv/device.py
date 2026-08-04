"""Fiche appareil partagée par toutes les plateformes.

⚠️ Avant la v4.1.0, `device_info` était redéclaré dans 4 fichiers avec des champs
divergents (`sw_version="3.1.0"` codé en dur — la version de l'INTÉGRATION, pas celle de
l'app — et `model="IPTV App"` alors que l'annonce Bonjour porte le vrai modèle d'Apple TV).
Home Assistant fusionne ces déclarations : le résultat dépendait de la plateforme chargée en
dernier. Une seule source ici.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_DEVICE_MANUFACTURER, CONF_DEVICE_MODEL, DOMAIN


def build_device_info(entry: ConfigEntry, info: dict[str, Any] | None = None) -> DeviceInfo:
    """Fiche appareil, enrichie de ce que le serveur OneTV annonce quand il le fait.

    `info` = payload de `/api/v1/info`. Les anciennes versions de l'app y renvoient
    `version: "1.0"` en dur ; on ne l'affiche donc que si elle ressemble à une vraie version
    d'app (celles-ci portent un numéro de build entre parenthèses).
    """
    info = info or {}

    device: DeviceInfo = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="OneTV",
        manufacturer=entry.data.get(CONF_DEVICE_MANUFACTURER) or "OneTV",
        model=entry.data.get(CONF_DEVICE_MODEL) or "IPTV App",
        configuration_url=f"http://{entry.data.get('host')}:{entry.data.get('port', 8765)}/",
    )

    version = info.get("version")
    if isinstance(version, str) and version and version != "1.0":
        device["sw_version"] = version

    return device
