"""Constantes pour l'intégration Noopy TV."""
from datetime import timedelta

DOMAIN = "noopy_tv"

# Configuration
CONF_HOST = "host"
CONF_PORT = "port"
CONF_SCAN_INTERVAL = "scan_interval"

# Defaults
DEFAULT_PORT = 8765
DEFAULT_SCAN_INTERVAL = timedelta(seconds=10)  # 10 secondes pour un statut player réactif
DEFAULT_SCAN_INTERVAL_SECONDS = 10

# Zeroconf
ZEROCONF_SERVICE_TYPE = "_noopytv._tcp.local."

# Attributs des sensors
ATTR_CHANNEL_ID = "channel_id"
ATTR_CHANNEL_NAME = "channel_name"
ATTR_LOGO_URL = "logo_url"
ATTR_STREAM_URL = "stream_url"
ATTR_STREAM_ID = "stream_id"
ATTR_TVG_ID = "tvg_id"
ATTR_CATEGORY = "category"

# EPG Attributs
ATTR_CURRENT_PROGRAM = "current_program"
ATTR_CURRENT_PROGRAM_START = "current_program_start"
ATTR_CURRENT_PROGRAM_END = "current_program_end"
ATTR_CURRENT_PROGRAM_DESCRIPTION = "current_program_description"
ATTR_CURRENT_PROGRAM_ICON = "current_program_icon"
ATTR_NEXT_PROGRAM = "next_program"
ATTR_NEXT_PROGRAM_START = "next_program_start"
ATTR_NEXT_PROGRAM_END = "next_program_end"
ATTR_PROGRESS_PERCENT = "progress_percent"

# Catégories
ATTR_CATEGORIES = "categories"
ATTR_TOTAL_CHANNELS = "total_channels"
ATTR_TOTAL_CATEGORIES = "total_categories"

# Services
SERVICE_REFRESH = "refresh"
SERVICE_PLAY_CHANNEL = "play_channel"

# Player attributs
ATTR_IS_PLAYING = "is_playing"
ATTR_PLAYER_ACTIVE = "player_active"
ATTR_CURRENT_CHANNEL = "current_channel"
ATTR_CURRENT_CHANNEL_ID = "current_channel_id"
ATTR_CURRENT_CHANNEL_LOGO = "current_channel_logo"
ATTR_AVAILABLE_CHANNELS = "available_channels"

# Platforms
PLATFORMS = ["sensor", "select"]
