"""Variante d'un achat : parallèle ou carte de base ? (RG-09)"""

import re

from app.rules.search import fold

# RG-09 : « Ne sont pas des parallèles : base, auto, autograph(e), relic, relique, patch, insert,
# rc, rookie, jersey, maillot, memorabilia. »
NOT_PARALLEL = frozenset(
    [
        "base",
        "auto",
        "autograph",
        "autographe",
        "autographs",
        "autographes",
        "relic",
        "relique",
        "patch",
        "insert",
        "rc",
        "rookie",
        "jersey",
        "maillot",
        "memorabilia",
    ]
)

_NUMBERING = re.compile(r"(\d+)\s*/\s*(\d+)")


def is_parallel_variant(variant: str, group_name: str = "") -> bool:
    """Vrai si la variante désigne un parallèle (couleur, numérotation, finition).

    Le nom de la sous-série fait souvent partie de la variante (« Current Stars Auto · Orange
    02/25 ») : on l'écarte avant de regarder ce qui reste.
    """
    words = re.findall(r"[a-z0-9/]+", fold(variant))
    group_words = set(re.findall(r"[a-z0-9/]+", fold(group_name)))
    remaining = [w for w in words if w not in group_words and w not in NOT_PARALLEL]
    return bool(remaining)


def numbering(variant: str) -> tuple[int, int] | None:
    """(exemplaire, tirage) quand la variante porte une numérotation : « Gold 35/50 » → (35, 50)."""
    match = _NUMBERING.search(variant)
    if not match:
        return None
    serial, run = int(match.group(1)), int(match.group(2))
    return (serial, run) if 0 < serial <= run else None
