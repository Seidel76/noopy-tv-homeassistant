from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NoopyTVAPI, NoopyTVAPIError, NoopyTVConnectionError
from .const import (
    CONF_API_KEY,
    CONF_APPLE_TV_ENTITY,
    CONF_APPLE_TV_SOURCE,
    CONF_DEVICE_ID,
    CONF_DEVICE_MANUFACTURER,
    CONF_DEVICE_MODEL,
    CONF_ENABLE_CATEGORY_SELECTS,
    CONF_SUPPORTS_SSE,
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_APPLE_TV_SOURCE,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _txt(properties: dict, *keys: str) -> str | None:
    """Lit une clé du TXT Bonjour. Les valeurs arrivent en `bytes` ou en `str` selon HA."""
    for key in keys:
        value = properties.get(key)
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="ignore")
        if isinstance(value, str) and value:
            return value
    return None

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
})


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    session = async_get_clientsession(hass)

    api = NoopyTVAPI(
        host=data[CONF_HOST],
        port=data.get(CONF_PORT, DEFAULT_PORT),
        session=session,
        api_key=data.get(CONF_API_KEY),
    )

    try:
        info = await api.get_info()

        if info.get("name") != "OneTV":
            raise NoopyTVAPIError("Ce n'est pas un serveur OneTV")

        # Pick up the api_key advertised by /api/v1/info so all subsequent
        # authenticated endpoints can be reached without manual entry.
        if api.api_key:
            data[CONF_API_KEY] = api.api_key

        return {
            "title": f"OneTV ({data[CONF_HOST]})",
            "total_channels": info.get("total_channels", 0),
            "total_categories": info.get("total_categories", 0),
        }
    finally:
        await api.close()


class NoopyTVConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    
    VERSION = 1
    
    def __init__(self) -> None:
        self._discovered_host: str | None = None
        self._discovered_port: int = DEFAULT_PORT
        self._discovered_name: str = "OneTV"
        self._discovered_api_key: str | None = None
        self._discovered_device_id: str | None = None
        self._discovered_model: str | None = None
        self._discovered_manufacturer: str | None = None
        self._discovered_supports_sse: bool = True
    
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except NoopyTVConnectionError:
                errors["base"] = "cannot_connect"
            except NoopyTVAPIError:
                errors["base"] = "invalid_response"
            except Exception:
                _LOGGER.exception("Erreur inattendue")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(f"noopytv_{user_input[CONF_HOST]}_{user_input.get(CONF_PORT, DEFAULT_PORT)}")
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(title=info["title"], data=user_input)
        
        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)
    
    async def async_step_zeroconf(self, discovery_info: zeroconf.ZeroconfServiceInfo) -> FlowResult:
        _LOGGER.info("OneTV découvert: %s", discovery_info)

        self._discovered_host = str(discovery_info.host)
        self._discovered_port = discovery_info.port or DEFAULT_PORT
        self._discovered_name = discovery_info.name.replace("._noopytv._tcp.local.", "")

        # Extract the api_key from the Bonjour TXT record (key "apiKey").
        # Allows zero-config auto-pairing without copy-paste from tvOS.
        properties = discovery_info.properties or {}
        if properties:
            _LOGGER.debug("Propriétés TXT: %s", properties)
        advertised_key = _txt(properties, "apiKey", "api_key")
        if advertised_key:
            self._discovered_api_key = advertised_key

        # Identité + capacités annoncées (app ≥ 2026-08). Absents sur les versions
        # antérieures : tous les usages en aval sont donc optionnels.
        self._discovered_device_id = _txt(properties, "deviceId", "device_id")
        self._discovered_model = _txt(properties, "model")
        self._discovered_manufacturer = _txt(properties, "manufacturer")
        sse_flag = _txt(properties, "sse")
        # Absent = on tente quand même (l'ancien comportement, qui abandonne proprement
        # sur un 501). Présent et à "0" = serveur sans flux push, inutile d'essayer.
        self._discovered_supports_sse = sse_flag != "0"

        # ⚠️ L'unique_id doit être STABLE. Basé sur host+port (comportement ≤ v4.0.x), un
        # simple renouvellement de bail DHCP produisait un nouvel identifiant → Home Assistant
        # créait une entrée EN DOUBLE et l'ancienne restait morte. On préfère donc le
        # `deviceId` annoncé dans le TXT Bonjour (app ≥ 2026-08), avec repli sur host+port
        # pour les versions antérieures.
        await self.async_set_unique_id(self._unique_id_for_discovery())
        # `updates=` : si l'appareil est déjà connu, on met à jour son adresse au lieu
        # d'abandonner — c'est ce qui répare une IP qui a changé.
        self._abort_if_unique_id_configured(
            updates={
                CONF_HOST: self._discovered_host,
                CONF_PORT: self._discovered_port,
                **({CONF_API_KEY: self._discovered_api_key} if self._discovered_api_key else {}),
            }
        )

        try:
            session = async_get_clientsession(self.hass)
            api = NoopyTVAPI(
                host=self._discovered_host,
                port=self._discovered_port,
                session=session,
                api_key=self._discovered_api_key,
            )

            if not await api.test_connection():
                return self.async_abort(reason="cannot_connect")

            # Fallback: pick up the key from /api/v1/info if the TXT record didn't carry one.
            if not self._discovered_api_key and api.api_key:
                self._discovered_api_key = api.api_key

            await api.close()
        except Exception as err:
            _LOGGER.warning("Erreur lors du test de connexion: %s", err)
            return self.async_abort(reason="cannot_connect")

        self.context["title_placeholders"] = {"name": self._discovered_name, "host": self._discovered_host}

        return await self.async_step_zeroconf_confirm()
    
    def _unique_id_for_discovery(self) -> str:
        """`deviceId` si l'app l'annonce, sinon repli host+port (comportement ≤ v4.0.x)."""
        if self._discovered_device_id:
            return f"noopytv_{self._discovered_device_id}"
        return f"noopytv_{self._discovered_host}_{self._discovered_port}"

    async def async_step_zeroconf_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            data: dict[str, Any] = {
                CONF_HOST: self._discovered_host,
                CONF_PORT: self._discovered_port,
                CONF_SUPPORTS_SSE: self._discovered_supports_sse,
            }
            if self._discovered_api_key:
                data[CONF_API_KEY] = self._discovered_api_key
            if self._discovered_device_id:
                data[CONF_DEVICE_ID] = self._discovered_device_id
            if self._discovered_model:
                data[CONF_DEVICE_MODEL] = self._discovered_model
            if self._discovered_manufacturer:
                data[CONF_DEVICE_MANUFACTURER] = self._discovered_manufacturer
            return self.async_create_entry(
                title=f"OneTV ({self._discovered_host})",
                data=data,
            )
        
        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={"name": self._discovered_name, "host": self._discovered_host, "port": str(self._discovered_port)},
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return NoopyTVOptionsFlowHandler()


class NoopyTVOptionsFlowHandler(config_entries.OptionsFlow):
    """Options de l'intégration.

    ⚠️ Ne PAS définir `self.config_entry` dans un `__init__` : depuis HA 2024.11 c'est une
    property en lecture seule renseignée par le framework, et l'affecter lève
    `AttributeError: property 'config_entry' ... has no setter` — le bouton « Configurer »
    renvoyait alors une erreur 500 (bug présent depuis la v3.x).
    """

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        
        current_interval = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS)
        current_atv = self.config_entry.options.get(CONF_APPLE_TV_ENTITY, "")
        current_source = self.config_entry.options.get(CONF_APPLE_TV_SOURCE, DEFAULT_APPLE_TV_SOURCE)

        # ⚡️ v4.0.0 — l'entité Apple TV est le SEUL moyen de (re)lancer l'app : son serveur
        # HTTP ne tourne que quand elle est déjà ouverte. Sans ça, `media_player.turn_on`
        # échoue avec un message explicite.
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_SCAN_INTERVAL, default=current_interval): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                vol.Optional(CONF_APPLE_TV_ENTITY, default=current_atv): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="media_player")
                ),
                vol.Optional(CONF_APPLE_TV_SOURCE, default=current_source): str,
                vol.Optional(
                    CONF_ENABLE_CATEGORY_SELECTS,
                    default=self.config_entry.options.get(CONF_ENABLE_CATEGORY_SELECTS, True),
                ): bool,
            }),
        )
