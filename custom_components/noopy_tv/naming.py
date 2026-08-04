"""Filtrage des entrées « séparateur » des playlists IPTV.

Port Python de `tvOSBuzzTVChannelList.isChannelNameValid` (règle 12 du projet OneTV) :
les playlists M3U contiennent des lignes décoratives qui ne sont pas des chaînes —
`▼●★ --- |FR| M6 PLAY |FR| --- ★●▼`, `---●★| MANGA |★●---`, `====`… Elles n'ont
rien à faire dans une `source_list` ni dans le navigateur de médias.

Le critère est celui de l'app : premier caractère non-blanc appartenant à un jeu de
symboles décoratifs (ponctuation incluse, apostrophe exclue), ou nom de 3 caractères
ou moins sans la moindre lettre.
"""

from __future__ import annotations

import unicodedata

_JUNK_PREFIX_CHARS = set(
    "▼▲●★☆■□▸▹►◄◆◇○◎※†‡§¶•–—―~=+#@!|/_\\<>{}[]()«»‹›❤❥✦✧✩✪✫✬✭✮✯✰✱✲✳✴✵✶✷✸✹✺-"
)

# Catégories Unicode de ponctuation — équivalent de `CharacterSet.punctuationCharacters`.
_PUNCTUATION_CATEGORIES = {"Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po"}


def is_channel_name_valid(name: str | None) -> bool:
    """False pour les entrées séparateur d'une playlist."""
    if not name:
        return False

    first = next((c for c in name if not c.isspace()), None)
    if first is None:
        return False

    if first in _JUNK_PREFIX_CHARS:
        return False
    # L'apostrophe est explicitement tolérée (ex. « L'Équipe »), le reste de la
    # ponctuation non.
    if first != "'" and unicodedata.category(first) in _PUNCTUATION_CATEGORIES:
        return False

    if len(name) <= 3:
        return any(c.isalpha() for c in name)

    return True
