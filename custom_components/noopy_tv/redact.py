"""Protection des identifiants d'abonnement contenus dans les URLs.

⚠️ Les URLs que l'app remonte portent souvent les identifiants de l'abonné :
- flux Xtream / M3U : `http://fournisseur:port/live/<utilisateur>/<mot de passe>/<id>.ts`
  (ou la forme courte `/<utilisateur>/<mot de passe>/<id>`), `get.php?username=…&password=…` ;
- visuels Plex : `…/photo/:/transcode?…&X-Plex-Token=…` ;
- visuels Emby / Jellyfin : `…/Images/Primary?api_key=…`.

Un attribut d'état est lisible par TOUS les utilisateurs de Home Assistant, écrit dans le
recorder à chaque changement et repris dans les exports d'historique et les captures ; un
diagnostic finit joint à des tickets publics. Aucune de ces URLs ne doit donc y apparaître.

Module pur (aucun import Home Assistant) : testable sans Home Assistant.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit

REDACTED = "**REDACTED**"

# Clés des URLs de lecture : jamais utiles hors de l'app, retirées dès la réception.
STREAM_URL_KEYS = frozenset({"stream_url", "streamURL", "streamUrl"})

# Paramètres de requête qui portent un identifiant (comparés en minuscules).
_SECRET_QUERY_PARAMS = frozenset(
    {
        "username",
        "user",
        "password",
        "pass",
        "pwd",
        "token",
        "access_token",
        "api_key",
        "apikey",
        "key",
        "auth",
        "x-plex-token",
        "x-emby-token",
        "x-mediabrowser-token",
        "play_token",
        "mac",
        "sig",
        "signature",
    }
)

# `/live/<u>/<p>/…`, `/movie/<u>/<p>/…`, `/series/<u>/<p>/…`, `/timeshift/<u>/<p>/…`
_XTREAM_TYPED_PATH = re.compile(r"/(?:live|movie|series|timeshift)/[^/]+/[^/]+/", re.IGNORECASE)
# Forme courte Xtream : `/<u>/<p>/<id>` ou `/<u>/<p>/<id>.ts`
_XTREAM_SHORT_PATH = re.compile(r"^/[^/]+/[^/]+/\d+(?:\.[A-Za-z0-9]+)?$")


def url_has_credentials(url: str) -> bool:
    """`True` si l'URL porte (ou peut porter) un identifiant d'abonnement."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return True  # illisible : on ne prend pas le risque
    if parts.username or parts.password:
        return True
    for name, _ in parse_qsl(parts.query, keep_blank_values=True):
        if name.lower() in _SECRET_QUERY_PARAMS:
            return True
    path = parts.path or ""
    return bool(_XTREAM_TYPED_PATH.search(path) or _XTREAM_SHORT_PATH.match(path))


def public_url(url: Any) -> str | None:
    """L'URL si elle peut être exposée telle quelle (attribut d'état), sinon `None`.

    On RETIRE l'URL plutôt que d'en ôter le jeton : sans lui, Plex/Emby/Jellyfin refusent
    l'image, une URL amputée ne servirait à rien. L'image reste visible via l'entité
    `media_player`, que Home Assistant sert par son propre proxy authentifié.
    """
    if not isinstance(url, str) or not url:
        return None
    return None if url_has_credentials(url) else url


def loggable_url(url: Any) -> str:
    """Forme de l'URL sûre pour un journal : schéma + hôte, sans chemin ni requête."""
    if not isinstance(url, str):
        return "?"
    try:
        parts = urlsplit(url)
    except ValueError:
        return "?"
    host = parts.hostname or "?"
    return f"{parts.scheme}://{host}/…" if parts.scheme else "?"


def strip_stream_urls(data: Any) -> Any:
    """Copie de `data` sans aucune clé d'URL de lecture, à toute profondeur."""
    if isinstance(data, dict):
        return {
            key: strip_stream_urls(value)
            for key, value in data.items()
            if key not in STREAM_URL_KEYS
        }
    if isinstance(data, list):
        return [strip_stream_urls(item) for item in data]
    return data


def redact_urls(data: Any) -> Any:
    """Copie de `data` où TOUTE valeur ressemblant à une URL est expurgée.

    Filet du diagnostic : une clé d'URL que l'app ajouterait demain, sous un nom absent de
    la liste d'expurgation, ne doit pas pouvoir fuiter.
    """
    if isinstance(data, dict):
        return {key: redact_urls(value) for key, value in data.items()}
    if isinstance(data, list):
        return [redact_urls(item) for item in data]
    if isinstance(data, str) and "://" in data:
        return REDACTED
    return data
