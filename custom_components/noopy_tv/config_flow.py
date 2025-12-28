"""Configuration flow pour l'intégration Noopy TV."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import zeroconf
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NoopyTVAPI, NoopyTVAPIError, NoopyTVConnectionError
from .const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, DEFAULT_PORT, DEFAULT_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_SECONDS, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Valide les données utilisateur et teste la connexion."""
    session = async_get_clientsession(hass)
    
    api = NoopyTVAPI(
        host=data[CONF_HOST],
        port=data.get(CONF_PORT, DEFAULT_PORT),
        session=session,
    )
    
    try:
        info = await api.get_info()
        
        if info.get("name") != "Noopy TV":
            raise NoopyTVAPIError("Ce n'est pas un serveur Noopy TV")
        
        return {
            "title": f"Noopy TV ({data[CONF_HOST]})",
            "total_channels": info.get("total_channels", 0),
            "total_categories": info.get("total_categories", 0),
        }
    finally:
        await api.close()


class NoopyTVConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Gère le flow de configuration pour Noopy TV."""
    
    VERSION = 1
    
    def __init__(self) -> None:
        """Initialise le flow."""
        self._discovered_host: str | None = None
        self._discovered_port: int = DEFAULT_PORT
        self._discovered_name: str = "Noopy TV"
    
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Gère l'étape de configuration manuelle."""
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
                # Vérifier si déjà configuré
                await self.async_set_unique_id(
                    f"noopytv_{user_input[CONF_HOST]}_{user_input.get(CONF_PORT, DEFAULT_PORT)}"
                )
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )
        
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
    
    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> FlowResult:
        """Gère la découverte automatique via Zeroconf/Bonjour."""
        _LOGGER.info("Noopy TV découvert: %s", discovery_info)
        
        self._discovered_host = str(discovery_info.host)
        self._discovered_port = discovery_info.port or DEFAULT_PORT
        self._discovered_name = discovery_info.name.replace("._noopytv._tcp.local.", "")
        
        # Récupérer les propriétés TXT
        properties = discovery_info.properties
        if properties:
            _LOGGER.debug("Propriétés TXT: %s", properties)
        
        # Vérifier si déjà configuré
        await self.async_set_unique_id(
            f"noopytv_{self._discovered_host}_{self._discovered_port}"
        )
        self._abort_if_unique_id_configured()
        
        # Tester la connexion
        try:
            session = async_get_clientsession(self.hass)
            api = NoopyTVAPI(
                host=self._discovered_host,
                port=self._discovered_port,
                session=session,
            )
            
            if not await api.test_connection():
                return self.async_abort(reason="cannot_connect")
            
            await api.close()
        except Exception as err:
            _LOGGER.warning("Erreur lors du test de connexion: %s", err)
            return self.async_abort(reason="cannot_connect")
        
        # Préremplir le contexte pour l'affichage
        self.context["title_placeholders"] = {
            "name": self._discovered_name,
            "host": self._discovered_host,
        }
        
        return await self.async_step_zeroconf_confirm()
    
    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirme l'ajout d'un appareil découvert."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"Noopy TV ({self._discovered_host})",
                data={
                    CONF_HOST: self._discovered_host,
                    CONF_PORT: self._discovered_port,
                },
            )
        
        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={
                "name": self._discovered_name,
                "host": self._discovered_host,
                "port": str(self._discovered_port),
            },
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Retourne le flow d'options."""
        return NoopyTVOptionsFlowHandler(config_entry)


class NoopyTVOptionsFlowHandler(config_entries.OptionsFlow):
    """Gère les options de l'intégration Noopy TV."""
    
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialise le flow d'options."""
        self.config_entry = config_entry
    
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Gère les options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        
        # Valeur actuelle ou défaut (en secondes)
        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            DEFAULT_SCAN_INTERVAL_SECONDS,
        )
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=current_interval,
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),  # 5s à 5min
                }
            ),
        )
