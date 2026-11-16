"""Recherche de cartes (F-09, F-25).

Mêmes règles que `web/src/lib/search.ts` ; les deux sont vérifiées par `shared/search-vectors.json`.

- les accents et la casse sont ignorés ;
- un mot sans chiffre doit correspondre au début d'un mot (« nets » ne trouve pas « Hornets ») ;
- un terme avec chiffre doit égaler le code, un segment du code, ou — s'il est purement numérique —
  un nombre contenu dans le code (« 3 » trouve WK-3, pas WK-30 ; « wk3 » trouve WK-3) ;
- tous les termes doivent correspondre.
"""

import re
import unicodedata

EXACT = "="  # préfixe des jetons à égalité stricte, absent de tout mot normalisé


def fold(text: str) -> str:
    """Minuscules sans accents."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def _code_tokens(code: str) -> tuple[list[str], list[str]]:
    """(mots, jetons exacts) tirés d'un code : « WK-3 » → (['wk'], ['=wk3', '=wk', '=3'])."""
    segments = _words(code)
    compact = "".join(segments)
    exact = {compact, *segments}
    exact |= {str(int(n)) for s in segments for n in re.findall(r"\d+", s)}  # « 045 » = « 45 »
    words = [s for s in segments if not s.isdigit()]
    return words, [EXACT + e for e in sorted(exact)]


def card_tokens(code: str, name: str, group: str = "", teams: list[str] | None = None) -> list[str]:
    """Jetons indexés pour une carte (colonne `search_tokens`)."""
    code_words, exact = _code_tokens(code)
    words = set(code_words)
    for text in (name, group, *(teams or [])):
        words.update(_words(text))
        # « O'Neal » doit répondre à « oneal » comme à « neal ».
        words.update(re.sub(r"[^a-z0-9]", "", w) for w in fold(text).split() if "'" in w or "’" in w)
    words.discard("")
    return sorted(words) + exact


def parse_query(query: str) -> list[tuple[str, str]]:
    """Découpe une requête en termes ('word', préfixe) ou ('exact', valeur)."""
    terms: list[tuple[str, str]] = []
    for raw in fold(query).split():
        token = re.sub(r"[^a-z0-9]", "", raw)
        if not token:
            continue
        if token.isdigit():
            terms.append(("exact", str(int(token))))
        elif any(c.isdigit() for c in token):
            terms.append(("exact", token))
        else:
            terms.append(("word", token))
    return terms


def matches(terms: list[tuple[str, str]], tokens: list[str]) -> bool:
    """Vrai si tous les termes correspondent aux jetons d'une carte."""
    for kind, value in terms:
        if kind == "exact":
            if EXACT + value not in tokens:
                return False
        elif not any(t.startswith(value) for t in tokens if not t.startswith(EXACT)):
            return False
    return True


def to_tsquery(terms: list[tuple[str, str]]) -> str:
    """Requête pour `search_tsv @@ CAST(:q AS tsquery)`. Les valeurs ne contiennent que [a-z0-9]."""
    parts = [f"'{EXACT}{v}'" if kind == "exact" else f"'{v}':*" for kind, v in terms]
    return " & ".join(parts)
