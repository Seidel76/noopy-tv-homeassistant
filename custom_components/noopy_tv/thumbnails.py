"""Vue HTTP qui sert les logos de chaînes MIS AU CARRÉ.

⚠️ Pourquoi une vue plutôt qu'un lien direct vers le logo : dans le navigateur de médias,
Home Assistant affiche les vignettes avec un recadrage centré. Un logo de chaîne, large et
court, y perd ses bords — mesuré sur le logo M6 (379×213), 44 % de la largeur disparaissait.
Passer en cartes carrées (v4.5.2) a réduit le mal sans le supprimer : le recadrage subsiste.

Contrairement à la jaquette du lecteur, on ne peut pas servir les octets depuis l'entité :
une vignette de navigateur n'est qu'une URL dans une balise `img`. On expose donc notre
propre URL, qui télécharge le visuel, l'inscrit dans un carré transparent et le renvoie.

L'URL est SIGNÉE par Home Assistant (`async_sign_path`) : la balise `img` du navigateur
n'envoie aucun en-tête d'authentification, et on ne veut pas d'un point d'entrée ouvert
capable d'aller chercher n'importe quelle adresse.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from urllib.parse import quote, urlparse

from aiohttp import web

from homeassistant.components.http.const import KEY_AUTHENTICATED

from homeassistant.components.http import HomeAssistantView

# `async_sign_path` vit dans le sous-module `auth` et n'est PAS ré-exporté par le package
# `homeassistant.components.http` : l'importer depuis la racine lève un ImportError qui
# empêche le chargement de TOUTE l'intégration. Le repli couvre les versions qui l'y
# exposeraient un jour.
try:
    from homeassistant.components.http.auth import async_sign_path
except ImportError:  # pragma: no cover
    from homeassistant.components.http import async_sign_path  # type: ignore[attr-defined]
from homeassistant.core import HomeAssistant, callback

from .images import async_square_png

_LOGGER = logging.getLogger(__name__)

THUMBNAIL_URL = "/api/noopy_tv/thumbnail"
# Les vignettes sont chargées pendant la navigation : une signature courte suffit largement,
# et une URL qui fuiterait n'aurait qu'une valeur éphémère.
_SIGNATURE_LIFETIME_SECONDS = 3600


class NoopyTVThumbnailView(HomeAssistantView):
    """Renvoie un visuel distant, complété en carré."""

    url = THUMBNAIL_URL
    name = "api:noopy_tv:thumbnail"
    # La balise `img` du navigateur n'envoie pas de jeton : l'accès repose sur la signature
    # de l'URL, vérifiée par Home Assistant avant d'arriver ici.
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        # `requires_auth = False` désactive le contrôle du middleware : sans cette vérification
        # explicite, l'URL serait un téléchargeur ouvert utilisable contre n'importe quelle
        # adresse joignable depuis Home Assistant. Le middleware pose ce drapeau quand la
        # signature de l'URL est valide.
        if not request.get(KEY_AUTHENTICATED, False):
            return web.Response(status=401, text="signature absente ou expirée")

        url = request.query.get("url")
        if not url:
            return web.Response(status=400, text="url manquante")
        if urlparse(url).scheme not in ("http", "https"):
            return web.Response(status=400, text="schéma non autorisé")

        hass: HomeAssistant = request.app["hass"]
        data = await async_square_png(hass, url)
        if data is None:
            return web.Response(status=404, text="visuel indisponible")

        return web.Response(
            body=data,
            content_type="image/png",
            headers={"Cache-Control": "max-age=3600"},
        )


@callback
def squared_thumbnail_url(hass: HomeAssistant, raw_url: str) -> str | None:
    """URL signée servant `raw_url` mis au carré. `None` si la signature échoue."""
    if not raw_url:
        return None
    try:
        return async_sign_path(
            hass,
            f"{THUMBNAIL_URL}?url={quote(raw_url, safe='')}",
            # `expiration` attend un timedelta, pas un nombre de secondes.
            expiration=timedelta(seconds=_SIGNATURE_LIFETIME_SECONDS),
        )
    except Exception:  # noqa: BLE001 - une vignette ne doit jamais casser la navigation
        _LOGGER.debug("Signature de vignette impossible", exc_info=True)
        return None
