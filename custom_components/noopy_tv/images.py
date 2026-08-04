"""URL des visuels (logos de chaînes, affiches VOD).

⚠️ Historique, corrigé en v4.1.2 — les images n'ont JAMAIS fonctionné dans cette
intégration, pour deux raisons empilées :

1. `/api/v1/proxy/image` exige une authentification (seul `/api/v1/info` est public) et la
   clé n'était pas jointe → **401**.
2. Une fois la clé jointe, le proxy applique une liste blanche anti-SSRF qui ne contient
   que `image.tmdb.org`, `thesportsdb.com` et `crests.football-data.org` → un logo de
   chaîne IPTV est refusé par construction : **403 « URL not allowed »**.

Rien de tout ça ne se voyait : une `entity_picture` cassée n'affiche simplement rien, sans
erreur. Le problème n'a fait surface qu'avec l'entité `image`, que Home Assistant récupère
côté serveur et dont l'échec remonte en clair.

**On n'utilise donc plus le proxy.** Home Assistant va chercher l'URL d'origine lui-même :
il a accès à Internet, les logos et affiches sont sur des hôtes publics, et ça supprime au
passage l'exposition de la clé d'API dans les attributs d'entité — elle aurait dû être
placée dans l'URL, visible de tout utilisateur de Home Assistant.

Ce qu'on perd : le redimensionnement `size=` du proxy. Négligeable — un logo pèse quelques
kilo-octets et Home Assistant met le résultat en cache.
"""

from __future__ import annotations

import asyncio
import io
import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def proxy_image_url(entry: ConfigEntry, raw_url: str, size: int = 300) -> str:
    """URL exploitable par Home Assistant pour un visuel.

    `size` est conservé dans la signature (les appelants le passent) mais n'a plus d'effet
    depuis l'abandon du proxy ; le garder évite de toucher les quatre plateformes le jour où
    un redimensionnement redeviendrait possible.
    """
    return raw_url


async def async_square_png(hass: HomeAssistant, url: str) -> bytes | None:
    """Télécharge un visuel et le rend CARRÉ par ajout de marges transparentes.

    ⚠️ Home Assistant affiche ces vignettes en carré avec recadrage centré
    (`object-fit: cover`). Un logo paysage y perd ses bords : mesuré sur le logo M6
    (379×213), 44 % de la largeur disparaissait et les branches du M étaient coupées.

    On ne redimensionne PAS le contenu : on l'inscrit dans un carré transparent, ce qui rend
    le recadrage de Home Assistant sans effet et garde le logo entier et centré.
    """
    session = async_get_clientsession(hass)
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(connect=5, total=15)) as response:
            if response.status != 200:
                _LOGGER.debug("Visuel %s : HTTP %s", url, response.status)
                return None
            raw = await response.read()
    except (aiohttp.ClientError, asyncio.TimeoutError) as err:
        _LOGGER.debug("Visuel %s injoignable : %s", url, err)
        return None

    # Pillow est fourni par Home Assistant. Traitement en exécuteur : c'est du CPU, et la
    # boucle d'événements ne doit pas être bloquée.
    return await hass.async_add_executor_job(_pad_to_square, raw)


def _pad_to_square(raw: bytes) -> bytes | None:
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow est une dépendance de HA
        return raw

    try:
        image = Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception:  # noqa: BLE001 - une image illisible ne doit pas casser l'entité
        _LOGGER.debug("Visuel illisible, servi tel quel")
        return raw

    width, height = image.size
    side = max(width, height)
    if width == height:
        canvas = image
    else:
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(image, ((side - width) // 2, (side - height) // 2))

    # Toujours ré-encoder en PNG : les appelants annoncent `image/png`, et une source JPEG
    # déjà carrée renverrait sinon un type incohérent.
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


@callback
def shared_artwork_picture(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    """URL du visuel servi par le `media_player`, déjà mis au carré.

    Les capteurs et sélecteurs ne peuvent pas transformer une image : leur `entity_picture`
    n'est qu'une URL. On les fait donc pointer vers le lecteur, qui sert le même contenu
    (le visuel en cours) via `async_get_media_image()`, carré.

    ⚠️ v4.2.0 — c'était une entité `image` dédiée. Elle apparaissait dans la liste des
    entités, y compris masquée (« Logo de la chaîne (Cachée) »), pour un doublon de ce que
    le lecteur affiche déjà. Le lecteur, lui, est l'entité principale : aucune entité en
    plus à masquer.

    Repli sur l'URL brute si le lecteur n'expose pas encore d'image — au pire le logo est
    recadré, comme avant la v4.1.3.
    """
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("media_player", DOMAIN, f"{entry.entry_id}_media_player")
    if entity_id is None:
        return None
    state = hass.states.get(entity_id)
    if state is None:
        return None
    picture = state.attributes.get("entity_picture")
    return picture if isinstance(picture, str) else None
