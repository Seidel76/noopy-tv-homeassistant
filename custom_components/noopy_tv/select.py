"""OneTV selects v3.1.0 — selects par catégorie créés dynamiquement.

Liste les catégories depuis le coordinator (qui les reconstitue depuis
`available_channels` du /player si /categories est vide). Chaque catégorie
devient un `select.onetv_<categorie>` avec uniquement les chaînes de
cette catégorie. Le select global "Toutes les chaînes" est conservé.
"""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from homeassistant.exceptions import HomeAssistantError

from .api import NoopyTVAPIError
from .const import (
    ATTR_CURRENT_CHANNEL,
    ATTR_CURRENT_CHANNEL_ID,
    ATTR_CURRENT_CHANNEL_LOGO,
    ATTR_PLAYER_ACTIVE,
    CONF_ENABLE_CATEGORY_SELECTS,
    DOMAIN,
)
from .device import build_device_info
from .images import proxy_image_url

_LOGGER = logging.getLogger(__name__)


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[àáâãäå]', 'a', text)
    text = re.sub(r'[èéêë]', 'e', text)
    text = re.sub(r'[ìíîï]', 'i', text)
    text = re.sub(r'[òóôõö]', 'o', text)
    text = re.sub(r'[ùúûü]', 'u', text)
    text = re.sub(r'[ç]', 'c', text)
    text = re.sub(r'[^a-z0-9]+', '_', text)
    text = text.strip('_')
    return text


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]

    # Tracker des entities déjà créées (pour add dynamiques quand HA détecte
    # une nouvelle catégorie au runtime)
    created_categories: set[str] = set()

    entities: list[SelectEntity] = [
        NoopyTVChannelSelect(coordinator, api, entry),
        # ⚡️ v4.1.0 — les pistes étaient déjà dans le payload récupéré à chaque cycle
        # (`audioTracks` / `subtitleTracks` : index, nom, langue, piste active) et les
        # commandes `setAudioTrack` / `setSubtitleTrack` implémentées côté app. Rien de tout
        # ça n'était exposé.
        NoopyTVTrackSelect(coordinator, api, entry, kind="audio"),
        NoopyTVTrackSelect(coordinator, api, entry, kind="subtitle"),
    ]

    # Les 6 selects par catégorie restent à `unknown` en permanence : désactivables.
    category_selects_enabled = entry.options.get(CONF_ENABLE_CATEGORY_SELECTS, True)
    initial_categories = _categories_from_coordinator(coordinator) if category_selects_enabled else []
    for category_name in initial_categories:
        entities.append(NoopyTVCategorySelect(coordinator, api, entry, category_name))
        created_categories.add(category_name)
        _LOGGER.debug("Création select pour catégorie : %s", category_name)

    async_add_entities(entities)
    _LOGGER.info(
        "OneTV v3.1.0 : %d select(s) créé(s) (1 global + %d catégorie(s))",
        len(entities),
        len(created_categories),
    )

    # Listener pour ajouter de nouveaux selects quand de nouvelles catégories
    # apparaissent au runtime (changement playlist, refresh).
    @callback
    def _async_add_new_category_selects() -> None:
        if not category_selects_enabled:
            return
        new_cats = _categories_from_coordinator(coordinator)
        added: list[NoopyTVCategorySelect] = []
        for cat in new_cats:
            if cat not in created_categories:
                ent = NoopyTVCategorySelect(coordinator, api, entry, cat)
                added.append(ent)
                created_categories.add(cat)
                _LOGGER.info("OneTV: nouvelle catégorie détectée → %s", cat)
        if added:
            async_add_entities(added)

    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_category_selects))


def _categories_from_coordinator(coordinator) -> list[str]:
    """Liste triée des noms de catégories disponibles dans le coordinator data.

    Source primaire : `coordinator.data["categories"]` (dict name→info).
    Fallback : reconstruit depuis le set des `category` de chaque channel.
    """
    if not coordinator.data:
        return []

    cats_dict = coordinator.data.get("categories") or {}
    names = [name for name in cats_dict.keys() if name]

    if not names:
        # Reconstruire depuis les channels
        channels = coordinator.data.get("channels") or {}
        seen: set[str] = set()
        for ch_data in channels.values():
            cat = ch_data.get("category")
            if cat and cat not in seen:
                seen.add(cat)
        names = list(seen)

    return sorted(names)


class _ChannelSelectBase(CoordinatorEntity, SelectEntity):
    """Base commune pour les selects de chaîne."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, api, entry: ConfigEntry, unique_suffix: str) -> None:
        super().__init__(coordinator)
        self._api = api
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._channel_map: dict[str, str] = {}
        # ⚡️ FIX HA (2026-06-20) — cache de `.options` : HA lit la propriété à chaque écriture
        # d'état (chaque tick) pour CHAQUE select → sans cache c'est un tri O(chaînes) répété
        # par select et par tick. La liste channels ne change que rarement (re-fetch conditionnel
        # côté coordinator → même objet dict entre ticks) → on garde une réf et compare par `is`.
        self._options_cache: list[str] | None = None
        self._options_cache_src: object | None = None

    @property
    def device_info(self):
        return build_device_info(self._entry, getattr(self._api, "info", None))

    def _proxy_image_url(self, raw_url: str, size: int = 48) -> str:
        return proxy_image_url(self._entry, raw_url, size)

    def _current_channel(self) -> dict[str, Any] | None:
        if not self.coordinator.data:
            return None
        player = self.coordinator.data.get("player", {}) or {}
        return player.get("current_channel")

    def _filter_channels(self) -> list[tuple[str, dict[str, Any]]]:
        """À surcharger pour filtrer les channels (ex: par catégorie)."""
        if not self.coordinator.data:
            return []
        channels = self.coordinator.data.get("channels", {}) or {}
        return list(channels.items())

    def _build_options(self) -> list[str]:
        # Cache: réutilise le résultat tant que l'objet dict `channels` est le même (identité).
        data = self.coordinator.data
        channels = (data.get("channels") if data else None) or {}
        if self._options_cache is not None and channels is self._options_cache_src:
            return self._options_cache

        items = self._filter_channels()
        sorted_items = sorted(items, key=lambda x: x[1].get("order", 999999))
        channel_map: dict[str, str] = {}
        names: list[str] = []
        for channel_id, ch_data in sorted_items:
            name = ch_data.get("name", "")
            if name:
                # Évite les doublons (au pire suffixe l'ID court)
                if name in channel_map:
                    name = f"{name} ({channel_id[:6]})"
                channel_map[name] = channel_id
                names.append(name)
        self._channel_map = channel_map
        self._options_cache = names
        self._options_cache_src = channels
        return names

    @property
    def options(self) -> list[str]:
        return self._build_options()

    async def async_select_option(self, option: str) -> None:
        # Re-build le map au cas où il aurait été flushé
        if option not in self._channel_map:
            self._build_options()
        channel_id = self._channel_map.get(option)
        if not channel_id:
            _LOGGER.error("Chaîne non trouvée: %s", option)
            return
        _LOGGER.info("Changement de chaîne : %s (id=%s)", option, channel_id)
        success = await self._api.play_channel(channel_id)
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Échec play_channel pour %s", option)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class NoopyTVChannelSelect(_ChannelSelectBase):
    """Select global avec toutes les chaînes."""

    _attr_translation_key = "channel_selector"
    _attr_icon = "mdi:television"

    def __init__(self, coordinator, api, entry: ConfigEntry) -> None:
        super().__init__(coordinator, api, entry, "channel_selector")
        self._attr_name = "Toutes les chaînes"

    @property
    def entity_picture(self) -> str | None:
        ch = self._current_channel()
        if ch and ch.get("logo_url"):
            return self._proxy_image_url(ch["logo_url"], size=48)
        return None

    @property
    def current_option(self) -> str | None:
        ch = self._current_channel()
        return ch.get("name") if ch else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        if not self.coordinator.data:
            return attrs

        player = self.coordinator.data.get("player", {}) or {}
        attrs[ATTR_PLAYER_ACTIVE] = player.get("is_active", False)
        attrs["total_channels"] = len(self.options)

        ch = self._current_channel()
        if ch:
            attrs[ATTR_CURRENT_CHANNEL] = ch.get("name")
            attrs[ATTR_CURRENT_CHANNEL_ID] = ch.get("id")
            attrs[ATTR_CURRENT_CHANNEL_LOGO] = ch.get("logo_url")
            attrs["current_category"] = ch.get("category", "")
            if ch.get("logo_url"):
                attrs["logo_proxy_url"] = self._proxy_image_url(ch["logo_url"], size=80)
            cp = ch.get("current_program")
            if cp:
                attrs["current_program"] = cp.get("title")
                attrs["progress_percent"] = cp.get("progress_percent", 0)
        return attrs


class NoopyTVCategorySelect(_ChannelSelectBase):
    """Select pour une catégorie donnée — n'affiche que les chaînes de cette catégorie."""

    _attr_icon = "mdi:television-guide"

    def __init__(self, coordinator, api, entry: ConfigEntry, category: str) -> None:
        super().__init__(coordinator, api, entry, f"category_{slugify(category)}")
        self._category = category
        self._attr_name = category

    def _filter_channels(self) -> list[tuple[str, dict[str, Any]]]:
        if not self.coordinator.data:
            return []
        channels = self.coordinator.data.get("channels", {}) or {}
        return [
            (cid, cdata)
            for cid, cdata in channels.items()
            if cdata.get("category") == self._category
        ]

    @property
    def entity_picture(self) -> str | None:
        ch = self._current_channel()
        if ch and ch.get("category") == self._category and ch.get("logo_url"):
            return self._proxy_image_url(ch["logo_url"], size=48)
        return None

    @property
    def current_option(self) -> str | None:
        ch = self._current_channel()
        if ch and ch.get("category") == self._category:
            return ch.get("name")
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "category": self._category,
            "channels_count": len(self.options),
        }
        if not self.coordinator.data:
            return attrs

        player = self.coordinator.data.get("player", {}) or {}
        ch = self._current_channel()
        if ch:
            in_cat = ch.get("category") == self._category
            attrs["is_playing_in_category"] = in_cat
            if in_cat:
                attrs[ATTR_CURRENT_CHANNEL] = ch.get("name")
                attrs[ATTR_PLAYER_ACTIVE] = player.get("is_active", False)
                if ch.get("logo_url"):
                    attrs["logo_proxy_url"] = self._proxy_image_url(ch["logo_url"], size=80)
                cp = ch.get("current_program")
                if cp:
                    attrs["current_program"] = cp.get("title")
                    attrs["progress_percent"] = cp.get("progress_percent", 0)
        return attrs


class NoopyTVTrackSelect(CoordinatorEntity, SelectEntity):
    """Sélecteur de piste audio ou de sous-titres du contenu en cours.

    Les pistes sont déjà publiées par `/api/v1/player/state` sous la forme
    `[{index, name, language, isSelected}]`, et l'app implémente `setAudioTrack` /
    `setSubtitleTrack`. Cette entité ne coûte donc aucune requête supplémentaire.

    ⚠️ Les options changent à CHAQUE contenu (un film n'a pas les mêmes pistes qu'une
    chaîne). C'est attendu pour ce type d'entité — l'entité devient indisponible quand le
    contenu courant n'expose aucune piste, plutôt que d'afficher une liste périmée.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, api, entry: ConfigEntry, kind: str) -> None:
        super().__init__(coordinator)
        self._api = api
        self._entry = entry
        self._kind = kind  # "audio" | "subtitle"
        if kind == "audio":
            self._attr_name = "Piste audio"
            self._attr_icon = "mdi:volume-high"
            self._payload_key = "audioTracks"
            self._command = "setAudioTrack"
        else:
            self._attr_name = "Sous-titres"
            self._attr_icon = "mdi:subtitles-outline"
            self._payload_key = "subtitleTracks"
            self._command = "setSubtitleTrack"
        self._attr_unique_id = f"{entry.entry_id}_{kind}_track"

    @property
    def device_info(self):
        return build_device_info(self._entry, getattr(self._api, "info", None))

    def _tracks(self) -> list[dict[str, Any]]:
        if not self.coordinator.data:
            return []
        state = self.coordinator.data.get("playback_state") or {}
        return state.get(self._payload_key) or []

    def _label(self, track: dict[str, Any]) -> str:
        """Libellé lisible et surtout UNIQUE — deux pistes peuvent porter le même nom."""
        name = str(track.get("name") or "").strip()
        language = str(track.get("language") or "").strip()
        index = track.get("index")
        if name and language and language.lower() not in name.lower():
            label = f"{name} ({language})"
        else:
            label = name or language or f"Piste {index}"
        return f"{label} · {index}"

    @property
    def available(self) -> bool:
        return bool(self.coordinator.last_update_success) and bool(self._tracks())

    @property
    def options(self) -> list[str]:
        return [self._label(track) for track in self._tracks()]

    @property
    def current_option(self) -> str | None:
        for track in self._tracks():
            if track.get("isSelected"):
                return self._label(track)
        return None

    async def async_select_option(self, option: str) -> None:
        # L'index est suffixé au libellé (cf. `_label`) : on le relit plutôt que de faire
        # confiance à l'unicité des noms de pistes.
        track = next((t for t in self._tracks() if self._label(t) == option), None)
        if track is None or track.get("index") is None:
            raise HomeAssistantError(f"Piste introuvable : {option}")

        try:
            result = await self._api.send_command(
                self._command, {"trackIndex": int(track["index"])}
            )
        except NoopyTVAPIError as err:
            raise HomeAssistantError(f"OneTV : changement de piste impossible — {err}") from err
        if not result.get("success", False):
            raise HomeAssistantError(
                f"OneTV a refusé le changement de piste : "
                f"{result.get('error') or result.get('message')}"
            )
        await self.coordinator.async_request_refresh()
