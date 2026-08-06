"""Lecture de l'état de lecture publié par l'app — et rattrapage de ses trous.

Module neutre : `sensor` et `media_player` en dépendent tous les deux, aucun n'a à importer
l'autre.
"""

from __future__ import annotations


def infer_content_type(payload: dict, player: dict | None) -> str:
    """Type de contenu, avec rattrapage quand l'app renvoie « none » en pleine lecture.

    ⚠️ Mesuré 2026-08-05 : pendant la lecture d'un épisode, l'app renvoie
    `contentType: "none"` alors que `contentTitle`, `currentTime` et `duration` sont bien
    renseignés. À la fermeture d'un lecteur VOD elle remet le type à `.none` sans effacer le
    reste ; un re-montage de la vue (bascule de lecteur, route Dolby Vision, reprise après
    échec) fait arriver cette fermeture APRÈS l'ouverture de la nouvelle instance, qui a
    déjà publié son contenu. Le type est perdu alors que la lecture continue.

    Discriminant fiable : en VOD `player.current_channel` est nul, en direct il porte la
    chaîne. La durée ne suffit pas — en direct elle vaut la position du bord du direct,
    donc non nulle elle aussi.
    """
    raw = (payload or {}).get("contentType")
    if isinstance(raw, str) and raw and raw != "none":
        return raw

    if not (payload or {}).get("isPlayerActive"):
        return "none"
    if (player or {}).get("current_channel"):
        return "channel"

    duration = (payload or {}).get("duration")
    if isinstance(duration, (int, float)) and duration > 0 and (payload or {}).get("contentTitle"):
        return "movie"
    return "none"
