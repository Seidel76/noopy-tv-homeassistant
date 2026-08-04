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

from homeassistant.config_entries import ConfigEntry


def proxy_image_url(entry: ConfigEntry, raw_url: str, size: int = 300) -> str:
    """URL exploitable par Home Assistant pour un visuel.

    `size` est conservé dans la signature (les appelants le passent) mais n'a plus d'effet
    depuis l'abandon du proxy ; le garder évite de toucher les quatre plateformes le jour où
    un redimensionnement redeviendrait possible.
    """
    return raw_url
