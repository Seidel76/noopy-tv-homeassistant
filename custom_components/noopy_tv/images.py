"""Construction des URL du proxy d'images de l'app.

⚠️ Bug corrigé en v4.1.1, présent depuis l'origine : `/api/v1/proxy/image` exige une
authentification (seul `/api/v1/info` est public côté app) et la clé n'était jamais jointe.
Toutes les images renvoyaient donc **401** — logos de chaînes du capteur, vignettes des
sélecteurs, jaquette du media_player. Personne ne l'avait vu parce qu'un `entity_picture`
cassé n'affiche rien sans lever d'erreur ; ça n'est devenu visible qu'avec l'entité `image`,
que Home Assistant récupère côté serveur et dont l'échec remonte en clair.

L'authentification passe par le paramètre `?token=` accepté par le serveur (le header
`X-API-Key` n'est pas une option : c'est Home Assistant, ou le navigateur, qui va chercher
l'URL, sans qu'on puisse lui faire ajouter un en-tête).
"""

from __future__ import annotations

from urllib.parse import quote

from homeassistant.config_entries import ConfigEntry

from .const import CONF_API_KEY, CONF_HOST, CONF_PORT, DEFAULT_PORT


def proxy_image_url(entry: ConfigEntry, raw_url: str, size: int = 300) -> str:
    """URL proxifiée et AUTHENTIFIÉE d'une image distante.

    Le proxy sert aussi à contourner le fait que Home Assistant n'a pas forcément accès aux
    CDN de logos, et applique le redimensionnement.
    """
    host = entry.data.get(CONF_HOST, "")
    port = entry.data.get(CONF_PORT, DEFAULT_PORT)
    url = (
        f"http://{host}:{port}/api/v1/proxy/image"
        f"?url={quote(raw_url, safe='')}&size={size}"
    )
    api_key = entry.data.get(CONF_API_KEY)
    if api_key:
        url += f"&token={quote(api_key, safe='')}"
    return url
