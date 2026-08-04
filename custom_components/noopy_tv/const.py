from datetime import timedelta

DOMAIN = "noopy_tv"

CONF_HOST = "host"
CONF_PORT = "port"
CONF_API_KEY = "api_key"
CONF_SCAN_INTERVAL = "scan_interval"

# ⚡️ v4.0.0 — l'app OneTV n'a AUCUN moyen de se lancer elle-même : quand elle est fermée,
# son serveur HTTP est mort et toutes les entités passent `unavailable` (règle 232). Le seul
# levier est l'Apple TV : `media_player.select_source` avec le nom de l'app dans `source_list`.
# L'utilisateur associe donc son entité Apple TV ici pour que `media_player.turn_on` marche.
CONF_APPLE_TV_ENTITY = "apple_tv_entity"
# Identité annoncée par le TXT Bonjour (v4.1.0). `device_id` est STABLE et indépendant de
# l'IP : sans lui, l'unique_id se basait sur host+port et un bail DHCP renouvelé créait une
# entrée EN DOUBLE au lieu de mettre à jour l'existante.
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_MODEL = "device_model"
CONF_DEVICE_MANUFACTURER = "device_manufacturer"
# Le TXT porte `sse=1/0` : inutile de tenter un flux push sur un serveur qui n'en a pas.
CONF_SUPPORTS_SSE = "supports_sse"
# Les 6 sélecteurs par catégorie restent à `unknown` en permanence et encombrent l'UI.
CONF_ENABLE_CATEGORY_SELECTS = "enable_category_selects"
CONF_APPLE_TV_SOURCE = "apple_tv_source"
DEFAULT_APPLE_TV_SOURCE = "OneTV Connect"

# ⚡️ v4.0.0 — le serveur tvOS pousse un event SSE (<50 ms) à chaque zap sur
# /api/v1/events/stream. Quand le flux est établi, le polling devient un simple filet de
# sécurité à cet intervalle (au lieu de CONF_SCAN_INTERVAL).
SSE_FALLBACK_SCAN_INTERVAL_SECONDS = 60
SSE_RECONNECT_MIN_DELAY = 5
SSE_RECONNECT_MAX_DELAY = 300

DEFAULT_PORT = 8765
# ⚡️ v3.2.0 (2026-06-20) : 10s par défaut. Depuis le re-fetch CONDITIONNEL de la liste lourde
# (api.py refresh_data : la liste 60k chaînes n'est re-téléchargée que si `channels_generation`
# change), un tick ne coûte plus que /info + /player + /player_state (petits, en parallèle).
# 10s rend la chaîne en cours quasi temps réel SANS marteler le catalogue.
DEFAULT_SCAN_INTERVAL = timedelta(seconds=10)
DEFAULT_SCAN_INTERVAL_SECONDS = 10
MIN_SCAN_INTERVAL_SECONDS = 5
MAX_SCAN_INTERVAL_SECONDS = 300

ZEROCONF_SERVICE_TYPE = "_noopytv._tcp.local."

ATTR_CHANNEL_ID = "channel_id"
ATTR_CHANNEL_NAME = "channel_name"
ATTR_LOGO_URL = "logo_url"
ATTR_STREAM_URL = "stream_url"
ATTR_STREAM_ID = "stream_id"
ATTR_TVG_ID = "tvg_id"
ATTR_CATEGORY = "category"

ATTR_CURRENT_PROGRAM = "current_program"
ATTR_CURRENT_PROGRAM_START = "current_program_start"
ATTR_CURRENT_PROGRAM_END = "current_program_end"
ATTR_CURRENT_PROGRAM_DESCRIPTION = "current_program_description"
ATTR_CURRENT_PROGRAM_ICON = "current_program_icon"
ATTR_NEXT_PROGRAM = "next_program"
ATTR_NEXT_PROGRAM_START = "next_program_start"
ATTR_NEXT_PROGRAM_END = "next_program_end"
ATTR_PROGRESS_PERCENT = "progress_percent"

ATTR_CATEGORIES = "categories"
ATTR_TOTAL_CHANNELS = "total_channels"
ATTR_TOTAL_CATEGORIES = "total_categories"

SERVICE_REFRESH = "refresh"
SERVICE_PLAY_CHANNEL = "play_channel"
SERVICE_PLAY_MOVIE = "play_movie"
SERVICE_PLAY_EPISODE = "play_episode"
SERVICE_SEND_COMMAND = "send_command"

# Commandes acceptées par `noopy_tv.send_command`. Liste calquée sur le switch de
# `AppModel.handleRemoteCommand` — ⚠️ setVolume/adjustVolume/toggleMute existent dans
# RemoteCommand côté app mais ne sont PAS implémentées par ce handler : ne pas les exposer.
SUPPORTED_COMMANDS = [
    "play",
    "pause",
    "togglePlayPause",
    "stop",
    "seekRelative",
    "seekAbsolute",
    "seekToLive",
    "setAudioTrack",
    "setSubtitleTrack",
    "nextChannel",
    "previousChannel",
]

ATTR_IS_PLAYING = "is_playing"
ATTR_PLAYER_ACTIVE = "player_active"
ATTR_CURRENT_CHANNEL = "current_channel"
ATTR_CURRENT_CHANNEL_ID = "current_channel_id"
ATTR_CURRENT_CHANNEL_LOGO = "current_channel_logo"
ATTR_AVAILABLE_CHANNELS = "available_channels"

PLATFORMS = ["sensor", "select", "media_player", "binary_sensor", "button", "image"]
