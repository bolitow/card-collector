"""Codes de cartes (RG-13) et listes de codes (F-37). Fonctions pures, sans base de données."""

import re
from itertools import groupby

MAX_CODE_LENGTH = 24
MAX_RANGE = 10_000

_RANGE = re.compile(r"^(\d+)-(\d+)$")
_SEPARATORS = re.compile(r"[,;\n]")


class InvalidCode(ValueError):
    pass


def normalize_code(raw: str) -> str:
    """RG-13 : sans « # », sans espaces, en majuscules, 24 caractères au plus."""
    code = re.sub(r"\s+", "", raw).lstrip("#").upper()
    if not code:
        raise InvalidCode("code vide")
    if len(code) > MAX_CODE_LENGTH:
        raise InvalidCode(f"code de plus de {MAX_CODE_LENGTH} caractères : {code[:30]}")
    return code


def code_key(code: str) -> str:
    """Clé d'égalité : deux codes numériques de même valeur sont égaux (« 007 » = « 7 »)."""
    code = normalize_code(code)
    return str(int(code)) if code.isdigit() else code


def natural_sort_key(code: str) -> tuple:
    """Tri naturel : 2 avant 10, WK-3 avant WK-30."""
    parts = re.findall(r"\d+|\D+", code.upper())
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in parts)


def _looks_like_code(token: str) -> bool:
    """Un jeton avec un chiffre (« 58 », « wk-4 ») ou en capitales avec un tiret (« RRR-NT »)."""
    if any(c.isdigit() for c in token):
        return True
    return "-" in token and not any(c.islower() for c in token)


def _expand_range(start: str, end: str) -> list[str]:
    lo, hi = int(start), int(end)
    if hi < lo or hi - lo >= MAX_RANGE:
        raise InvalidCode(f"plage invalide : {start}-{end}")
    width = len(start) if start.startswith("0") else 0  # « 001-050 » : zéros conservés
    return [str(n).zfill(width) for n in range(lo, hi + 1)]


def parse_code_list(text: str) -> list[tuple[str, str]]:
    """F-37 : transforme une saisie libre en liste (code, nom).

    - une carte par ligne : « 57 Kylian Mbappé »
    - plages : « 1-200 », « 001-050 »
    - listes séparées par des virgules ou des points-virgules
    - plusieurs codes séparés par des espaces
    - doublons ignorés (au sens de RG-13)
    """
    found: dict[str, tuple[str, str]] = {}

    def add(raw: str, name: str = "") -> None:
        code = normalize_code(raw)
        found.setdefault(code_key(code), (code, name.strip()))

    for segment in _SEPARATORS.split(text):
        tokens = segment.split()
        if not tokens:
            continue
        first = tokens[0].lstrip("#")
        if match := _RANGE.match(first):
            for code in _expand_range(*match.groups()):
                add(code)
            tokens = tokens[1:]
            if not tokens:
                continue
            first = tokens[0].lstrip("#")
        rest = tokens[1:]
        if rest and not all(_looks_like_code(t.lstrip("#")) for t in rest):
            add(first, " ".join(rest))  # « 57 Kylian Mbappé » : le reste de la ligne est le nom
            continue
        for token in tokens:
            token = token.lstrip("#")
            if match := _RANGE.match(token):
                for code in _expand_range(*match.groups()):
                    add(code)
            elif token:
                add(token)
    return list(found.values())


def format_code_list(codes: list[str], compact: bool = False) -> str:
    """Liste à copier (F-12). `compact` regroupe les numéros qui se suivent : « 1-12, 15, 18-20 ».

    Le format compact est celui que les collectionneurs s'échangent ; `parse_code_list` le relit.
    """
    if not compact:
        return ", ".join(sorted(codes, key=natural_sort_key))

    # Les numéros consécutifs de même écriture (avec ou sans zéros de tête) forment une plage.
    by_width: dict[int, list[int]] = {}
    for code in codes:
        if code.isdigit():
            by_width.setdefault(len(code) if code.startswith("0") else 0, []).append(int(code))
    runs: list[tuple[int, int, int]] = []
    for width, values in by_width.items():
        ordered = sorted(set(values))
        for _, run in groupby(enumerate(ordered), key=lambda pair: pair[1] - pair[0]):
            items = [value for _, value in run]
            runs.append((items[0], items[-1], width))

    def write(value: int, width: int) -> str:
        return str(value).zfill(width)

    out = [
        write(lo, width) if lo == hi else f"{write(lo, width)}-{write(hi, width)}"
        for lo, hi, width in sorted(runs, key=lambda r: (r[0], r[2]))
    ]
    out.extend(sorted((c for c in codes if not c.isdigit()), key=natural_sort_key))
    return ", ".join(out)
