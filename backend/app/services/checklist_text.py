"""Texte d'une checklist : extraction depuis un PDF, découpage, et lecture sans IA.

La lecture sans IA (`parse_plain`) sert quand l'IA est indisponible (IA-04) et comprend un format
simple, une carte par ligne :

    BASE
    1    Patrick Mahomes II    Kansas City Chiefs
    301  Fernando Mendoza      Las Vegas Raiders    RC
    GOLDEN MIRROR VARIATIONS [special]
    301  Fernando Mendoza      Las Vegas Raiders

Les colonnes sont séparées par une tabulation, deux espaces ou « - ». Une ligne qui ne commence pas
par un code est un titre de sous-série ; `[type]` force le type.
"""

import io
import re
from typing import Any

from app.rules.search import fold

CHUNK_LINES = 220

# Grandes rubriques des éditeurs (annexe D) → type par défaut des sous-séries qui suivent.
_RUBRICS = {
    "base": "base",
    "base cards": "base",
    "base set": "base",
    "insert": "insert",
    "inserts": "insert",
    "autograph": "auto",
    "autographs": "auto",
    "relic": "relic",
    "relics": "relic",
    "autograph relic": "auto",
    "autograph relics": "auto",
    "variations": "special",
}
_KIND_HINTS = [
    ("auto", ("autograph", "auto", "signature", "signatures", "ink")),
    ("relic", ("relic", "relics", "patch", "memorabilia", "jersey", "remnants", "swatch")),
    ("special", ("variation", "variations", "variant", "sp", "ssp")),
]
_FORCED_KIND = re.compile(r"\[(base|insert|special|relic|auto)\]\s*$", re.I)
_COLUMNS = re.compile(r"\t+|\s{2,}|\s+[-–—]\s+")
_CODE = re.compile(r"^#?[A-Za-z0-9][A-Za-z0-9/.-]*$")
_ROOKIE = re.compile(r"(?:^|\s)(RC|Rookie|Rookie Card)$", re.I)


def extract_pdf_text(data: bytes) -> str:
    """Texte d'un PDF en conservant la mise en page (annexe D), sans dépendance système."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text(extraction_mode="layout") or "" for page in reader.pages)


def _is_card_line(first: str) -> bool:
    """Un code : contient un chiffre, ou des capitales avec un tiret (« RRR-NT »)."""
    if not _CODE.match(first):
        return False
    return any(c.isdigit() for c in first) or ("-" in first and first.isupper())


def _kind_for(title: str, current: str) -> str:
    words = set(re.findall(r"[a-z]+", fold(title)))
    for kind, hints in _KIND_HINTS:
        if words & set(hints):
            return kind
    return current


def _split_slash(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*/\s*", text) if part.strip()]


def parse_plain(text: str, context: str = "") -> list[dict[str, Any]]:
    """Lit une checklist au format simple. Renvoie des sous-séries au format du brouillon."""
    groups: list[dict[str, Any]] = []
    rubric_kind = _RUBRICS.get(fold(context).strip(), "base")
    current: dict[str, Any] | None = None

    for raw in text.splitlines():
        line = re.sub(r"[™®©]", "", raw).strip()
        if not line:
            continue
        first, rest = (re.split(r"\s+", line, maxsplit=1) + [""])[:2]

        if not _is_card_line(first) or not rest.strip():
            forced = _FORCED_KIND.search(line)
            title = _FORCED_KIND.sub("", line).strip()
            rubric = _RUBRICS.get(fold(title))
            if rubric and not forced:
                rubric_kind = rubric
            kind = forced.group(1).lower() if forced else _kind_for(title, rubric_kind)
            current = {"name": title.title() if title.isupper() else title, "kind": kind, "cards": []}
            groups.append(current)
            continue

        if current is None:
            current = {"name": "Base", "kind": rubric_kind, "cards": []}
            groups.append(current)
        columns = [c.strip() for c in _COLUMNS.split(rest.strip()) if c.strip()]
        rookie = False
        if columns and _ROOKIE.fullmatch(columns[-1]):
            rookie, columns = True, columns[:-1]
        name = columns[0] if columns else ""
        if match := _ROOKIE.search(name):
            rookie, name = True, name[: match.start()].strip()
        teams = _split_slash(columns[1]) if len(columns) > 1 else []
        current["cards"].append(
            {"code": first.lstrip("#"), "names": _split_slash(name), "teams": teams, "rookie": rookie}
        )
    return [g for g in groups if g["cards"] or fold(g["name"]) not in _RUBRICS]


def chunks(text: str) -> list[tuple[str, str]]:
    """Découpe le texte en extraits de taille bornée, coupés de préférence sur un titre.

    Renvoie (rubrique en cours, extrait) : le contexte permet au modèle de typer les premières
    lignes d'un extrait qui commence au milieu d'une rubrique.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    result: list[tuple[str, str]] = []
    start, rubric = 0, ""
    while start < len(lines):
        end = min(start + CHUNK_LINES, len(lines))
        if end < len(lines):
            # Recule jusqu'au dernier titre de la fenêtre, s'il y en a un dans sa seconde moitié.
            for index in range(end, start + CHUNK_LINES // 2, -1):
                if not _is_card_line(lines[index].split()[0]):
                    end = index
                    break
        result.append((rubric, "\n".join(lines[start:end])))
        for line in lines[start:end]:
            if fold(line.strip()) in _RUBRICS:
                rubric = line.strip()
        start = end
    return result
