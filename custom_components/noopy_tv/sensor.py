"""OneTV sensors v3.1.0 — sensor agrégé enrichi.

Le sensor `chaine_en_cours` fusionne `/api/v1/player` (channel info) ET
`/api/v1/player/state` (contentType précis + posterURL pour VOD/episode +
tmdbID + position de lecture) → expose chaîne TV OU film/épisode dans une
seule entity, avec l'image appropriée (logo pour channel, poster pour VOD).

Aucun impact sur les players KSPlayer/MPV/VLC : tout est servi par le cache
HTTP push-based côté serveur OneTV (pas de hop main thread, pas de freeze).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from urllib.parse import quote

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE
from homeassistant.util import dt as dt_util
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
from .device import build_device_info

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
        NoopyTVProgrammeProgressSensor(coordinator, entry),
    ]
    async_add_entities(entities)
    _LOGGER.info("OneTV : %d sensor(s) créé(s)", len(entities))


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
        return build_device_info(self._entry)

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
    """Sensor agrégé : contenu en cours de lecture (chaîne TV, film, épisode, catchup).

    Fusionne `/api/v1/player` (chaîne courante avec metadata) et
    `/api/v1/player/state` (contentType précis + posterURL pour VOD).

    `state` : nom de la chaîne OU titre du film/épisode selon contentType
    `entity_picture` : logo channel OU poster VOD (proxy via /api/v1/proxy/image)
    `attributes` : contentType, contentId, contentTitle, contentSubtitle, tmdbID,
                   logoURL, posterURL, isPlaying, currentTime, duration, programme EPG…
    """

    _attr_has_entity_name = True
    _attr_name = "Lecture en cours"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_current_channel"

    @property
    def device_info(self) -> DeviceInfo:
        return build_device_info(self._entry)

    def _player(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("player", {}) or {}

    def _playback_state(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.get("playback_state", {}) or {}

    def _current_channel(self) -> dict[str, Any] | None:
        return self._player().get("current_channel")

    def _content_type(self) -> str:
        """Retourne channel / movie / episode / catchup / none."""
        ps = self._playback_state()
        ct = ps.get("contentType")
        if isinstance(ct, str) and ct:
            return ct
        # Fallback : si is_active mais pas de contentType, on considère channel
        if self._player().get("is_active"):
            return "channel"
        return "none"

    @property
    def icon(self) -> str:
        ct = self._content_type()
        if ct == "movie":
            return "mdi:movie"
        if ct == "episode":
            return "mdi:television-play"
        if ct == "catchup":
            return "mdi:rewind"
        if ct == "channel":
            return "mdi:television-classic"
        return "mdi:television-off"

    @property
    def native_value(self) -> str | None:
        ct = self._content_type()
        ps = self._playback_state()

        if ct == "none":
            return "Aucune lecture"

        # VOD / film / épisode : titre depuis playback_state
        if ct in ("movie", "episode", "catchup"):
            title = ps.get("contentTitle")
            if title:
                return str(title)
            # Fallback channel name (catchup peut avoir un channel associé)
            ch = self._current_channel()
            if ch and ch.get("name"):
                return str(ch["name"])
            return ct.capitalize()

        # Chaîne TV : nom de la chaîne (priorité player.current_channel, fallback playback_state)
        ch = self._current_channel()
        if ch and ch.get("name"):
            return str(ch["name"])
        title = ps.get("contentTitle")
        if title:
            return str(title)
        return "Lecture en cours"

    def _proxy_image_url(self, raw_url: str, size: int = 200) -> str:
        host = self._entry.data.get("host", "")
        port = self._entry.data.get("port", 8765)
        encoded = quote(raw_url, safe="")
        return f"http://{host}:{port}/api/v1/proxy/image?url={encoded}&size={size}"

    @property
    def entity_picture(self) -> str | None:
        """Image affichée dans HA : poster VOD (movie/episode) ou logo chaîne (channel/catchup)."""
        ct = self._content_type()
        ps = self._playback_state()

        # VOD : poster
        if ct in ("movie", "episode"):
            poster = ps.get("posterURL")
            if poster:
                return self._proxy_image_url(poster, size=400)

        # Channel/catchup : logo (priorité playback_state.logoURL, fallback player.current_channel.logo_url)
        logo = ps.get("logoURL")
        if not logo:
            ch = self._current_channel()
            if ch:
                logo = ch.get("logo_url")
        if logo:
            return self._proxy_image_url(logo, size=200)

        # Fallback : icône programme courant si chaîne
        ch = self._current_channel()
        if ch:
            cp = ch.get("current_program")
            if cp and cp.get("icon_url"):
                return self._proxy_image_url(cp["icon_url"], size=200)

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}

        player = self._player()
        ps = self._playback_state()
        ct = self._content_type()

        attrs: dict[str, Any] = {
            ATTR_PLAYER_ACTIVE: player.get("is_active") or ps.get("isPlayerActive", False),
            "content_type": ct,  # channel / movie / episode / catchup / none
            "is_playing": ps.get("isPlaying", False),
            "is_paused": ps.get("isPaused", False),
            "is_buffering": ps.get("isBuffering", False),
        }

        # Position de lecture (utile pour timeline UI)
        if ps.get("duration", 0) > 0:
            attrs["current_time"] = ps.get("currentTime", 0)
            attrs["duration"] = ps.get("duration", 0)
            ct_sec = ps.get("currentTime") or 0
            dur = ps.get("duration") or 0
            if dur > 0:
                attrs["progress_percent"] = round((ct_sec / dur) * 100, 1)

        # Live / timeshift
        if ps.get("isLive"):
            attrs["is_live"] = True
            attrs["is_at_live_edge"] = ps.get("isAtLiveEdge", False)
            attrs["timeshift_delay"] = ps.get("timeshiftDelay", 0)

        # Player utilisé (KSPlayer / MPV / VLC / AVPlayer)
        if ps.get("playerType"):
            attrs["player_type"] = ps["playerType"]

        # Branchement : VOD ou chaîne
        if ct in ("movie", "episode"):
            attrs["content_id"] = ps.get("contentId")
            attrs["content_title"] = ps.get("contentTitle")
            if ps.get("contentSubtitle"):
                attrs["content_subtitle"] = ps["contentSubtitle"]
            if ps.get("tmdbID"):
                attrs["tmdb_id"] = ps["tmdbID"]
            if ps.get("posterURL"):
                attrs["poster_url"] = ps["posterURL"]
                attrs["poster_proxy_url"] = self._proxy_image_url(ps["posterURL"], size=400)
            return attrs

        # Chaîne TV ou catchup : remonter les attributs channel
        ch = self._current_channel() or {}
        if not ch and ct == "none":
            return attrs

        attrs["channel_id"] = ch.get("id") or ps.get("contentId")
        attrs["channel_name"] = ch.get("name") or ps.get("contentTitle")
        attrs[ATTR_LOGO_URL] = ch.get("logo_url") or ps.get("logoURL")
        attrs[ATTR_STREAM_URL] = ch.get("stream_url")
        attrs[ATTR_CATEGORY] = ch.get("category")
        attrs[ATTR_TVG_ID] = ch.get("tvg_id")
        attrs[ATTR_STREAM_ID] = ch.get("stream_id")

        logo_url = ch.get("logo_url") or ps.get("logoURL")
        if logo_url:
            attrs["logo_proxy_url"] = self._proxy_image_url(logo_url, size=200)

        # Programme EPG en cours
        cp = ch.get("current_program")
        if cp:
            attrs[ATTR_CURRENT_PROGRAM] = cp.get("title")
            attrs[ATTR_CURRENT_PROGRAM_START] = cp.get("start")
            attrs[ATTR_CURRENT_PROGRAM_END] = cp.get("end")
            attrs[ATTR_CURRENT_PROGRAM_DESCRIPTION] = cp.get("description")
            attrs[ATTR_CURRENT_PROGRAM_ICON] = cp.get("icon_url")
            attrs[ATTR_PROGRESS_PERCENT] = cp.get("progress_percent", 0)
        else:
            # Fallback EPG depuis playback_state
            psp = ps.get("currentProgramme")
            if psp:
                attrs[ATTR_CURRENT_PROGRAM] = psp.get("title")
                attrs[ATTR_CURRENT_PROGRAM_START] = psp.get("start")
                attrs[ATTR_CURRENT_PROGRAM_END] = psp.get("end")
                attrs[ATTR_CURRENT_PROGRAM_DESCRIPTION] = psp.get("desc")
                attrs[ATTR_CURRENT_PROGRAM_ICON] = psp.get("iconURL")
                attrs[ATTR_PROGRESS_PERCENT] = round((psp.get("progress") or 0) * 100, 1)

        return attrs


class NoopyTVProgrammeProgressSensor(CoordinatorEntity, SensorEntity):
    """Avancement du programme EPG en cours, en pourcentage.

    ⚠️ La valeur est RECALCULÉE depuis `start` / `end` plutôt que lue dans le payload : le
    champ `progress` de l'app vaut 0→1 côté lecteur mais 0→100 dans la liste des chaînes
    (`progress_percent`). Recalculer supprime l'ambiguïté et reste juste quel que soit le
    chemin qui a rempli l'EPG.

    Les attributs `start` / `end` permettent à une carte de dashboard d'animer la barre
    entre deux mises à jour, qui n'arrivent qu'au rythme du coordinator.
    """

    _attr_has_entity_name = True
    _attr_name = "Progression du programme"
    _attr_icon = "mdi:progress-clock"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_programme_progress"

    @property
    def device_info(self) -> DeviceInfo:
        return build_device_info(self._entry)

    def _programme(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        state = self.coordinator.data.get("playback_state") or {}
        programme = state.get("currentProgramme")
        if isinstance(programme, dict):
            return programme
        # Repli : la chaîne courante porte aussi son programme, mais aplati.
        player = self.coordinator.data.get("player") or {}
        channel = player.get("current_channel") or {}
        raw = channel.get("current_program")
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _parse(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        return dt_util.parse_datetime(value)

    @property
    def available(self) -> bool:
        programme = self._programme()
        return bool(
            self.coordinator.last_update_success
            and self._parse(programme.get("start"))
            and self._parse(programme.get("end"))
        )

    @property
    def native_value(self) -> float | None:
        programme = self._programme()
        start = self._parse(programme.get("start"))
        end = self._parse(programme.get("end"))
        if start is None or end is None:
            return None
        total = (end - start).total_seconds()
        if total <= 0:
            return None
        elapsed = (dt_util.utcnow() - start).total_seconds()
        return round(max(0.0, min(100.0, elapsed / total * 100)), 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        programme = self._programme()
        start = self._parse(programme.get("start"))
        end = self._parse(programme.get("end"))
        attrs: dict[str, Any] = {
            "title": programme.get("title"),
            "start": programme.get("start"),
            "end": programme.get("end"),
            "description": programme.get("desc") or programme.get("description"),
        }
        if start and end:
            attrs["duration_minutes"] = int((end - start).total_seconds() // 60)
            remaining = (end - dt_util.utcnow()).total_seconds()
            attrs["remaining_minutes"] = max(0, int(remaining // 60))
        icon_url = programme.get("iconURL") or programme.get("icon_url")
        if icon_url:
            attrs["icon_url"] = icon_url
        return {k: v for k, v in attrs.items() if v is not None}
