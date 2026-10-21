"""Filtrage des entrées « séparateur » des playlists et résolution de nom de chaîne.

`is_channel_name_valid` est le port Python de `ChannelNameCleaner.isJunkSeparatorName`
(règle 12 du projet OneTV, révisée r815) : les playlists M3U contiennent des lignes
décoratives qui ne sont pas des chaînes — `▼●★ --- |FR| M6 PLAY |FR| --- ★●▼`,
`---●★| MANGA |★●---`, `====`… Elles n'ont rien à faire dans une `source_list` ni dans
le navigateur de médias.

Critère (parité exacte avec l'app) : aucune lettre ni chiffre, OU une suite d'au moins
3 caractères de séparation contigus.

⚠️ v4.9.4 — l'ancienne version testait le PREMIER caractère contre la ponctuation et
masquait donc « |FR| TF1 FHD », « [FR] … », « (FR) … » : sur une playlist de test,
9 533 vraies chaînes rejetées pour 293 séparateurs.
"""

from __future__ import annotations

import unicodedata

_SEPARATOR_CHARS = frozenset(
    "-=_~*"
    "•·"  # • ·
    "▬■□◆◇"  # ▬ ■ □ ◆ ◇
    "●○★☆"  # ● ○ ★ ☆
    "▼▲►◄"  # ▼ ▲ ► ◄
    "═║─━"  # ═ ║ ─ ━
    "│┃»«"  # │ ┃ » «
)

_LETTER_OR_DIGIT = frozenset({"Lu", "Ll", "Lt", "Lm", "Lo", "Nd"})


def is_channel_name_valid(name: str | None) -> bool:
    """False pour les entrées séparateur d'une playlist."""
    if not name:
        return False

    has_letter_or_digit = False
    run = 0
    for char in name:
        if char in _SEPARATOR_CHARS:
            run += 1
            if run >= 3:
                return False
            continue
        run = 0
        if not has_letter_or_digit and unicodedata.category(char) in _LETTER_OR_DIGIT:
            has_letter_or_digit = True
    return has_letter_or_digit


def normalize_channel_name(name: str | None) -> str:
    """Clé de comparaison tolérante : minuscules, accents retirés, seulement lettres et chiffres.

    « France 2 », « FRANCE 2 » et « france-2 » donnent la même clé ; « TF1 » et « TF1 HD »
    restent distincts (aucun préfixe pays ni suffixe qualité n'est retiré).
    """
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(
        c for c in decomposed.casefold() if unicodedata.category(c) in _LETTER_OR_DIGIT
    )


def resolve_channel_id(channels: dict[str, dict] | None, wanted: str) -> str | None:
    """Identifiant de chaîne pour `wanted` (UUID ou nom), ou None.

    L'app ne compare que le nom EXACT : « France 2 » ne trouvait pas « FRANCE 2 ». On résout
    donc ici, sur la liste déjà en cache (aucune requête) : identifiant, puis nom exact, puis
    nom normalisé (casse, accents, ponctuation), séparateurs de playlist exclus du repli.
    """
    if not channels or not wanted:
        return None
    if wanted in channels:
        return wanted
    for channel_id, channel in channels.items():
        if channel.get("name") == wanted:
            return channel_id
    key = normalize_channel_name(wanted)
    if not key:
        return None
    for channel_id, channel in channels.items():
        name = channel.get("name")
        if is_channel_name_valid(name) and normalize_channel_name(name) == key:
            return channel_id
    return None
