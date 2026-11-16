"""Avancement d'une collection (RG-15) et libellés de possession (RG-05, RG-06)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Progress:
    owned: int
    total: int
    scope: str  # 'base' ou 'all'

    @property
    def percent(self) -> int:
        """Arrondi vers le bas : 100 % n'apparaît que lorsque tout est possédé."""
        return self.owned * 100 // self.total if self.total else 0

    @property
    def label(self) -> str:
        if self.owned and self.percent < 1:
            return "<1 %"  # collection entamée mais sous 1 %
        return f"{self.percent} %"


def progress(total_by_kind: dict[str, int], owned_by_kind: dict[str, int]) -> Progress:
    """RG-15 : le pourcentage porte sur la base quand la collection mélange plusieurs types
    et qu'une carte de base est possédée ; sinon sur toute la série.

    Les compteurs sont ceux du périmètre affiché (toute la série, ou l'équipe prioritaire).
    """
    kinds = [k for k, n in total_by_kind.items() if n]
    if len(kinds) > 1 and owned_by_kind.get("base", 0) > 0:
        return Progress(owned_by_kind["base"], total_by_kind["base"], "base")
    return Progress(sum(owned_by_kind.values()), sum(total_by_kind.values()), "all")


def doubles(quantity: int) -> int:
    """RG-06 : une quantité q ≥ 2 donne q − 1 doubles. Un parallèle n'est jamais un double (RG-05)."""
    return max(quantity - 1, 0)
