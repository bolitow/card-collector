"""Règles de gestion pures : RG-05, RG-06, RG-09, RG-13, RG-15, F-09, F-37."""

import json
from pathlib import Path

import pytest

from app.rules import codes, search
from app.rules.progress import doubles, progress
from app.rules.variants import is_parallel_variant, numbering

VECTORS = json.loads((Path(__file__).parents[2] / "shared" / "search-vectors.json").read_text())


# ---- RG-13 : codes


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("#57", "57"), (" op17-045 ", "OP17-045"), ("rrr - nt", "RRR-NT"), ("007", "007")],
)
def test_normalize_code(raw, expected):
    assert codes.normalize_code(raw) == expected


def test_numeric_codes_of_same_value_are_equal():
    assert codes.code_key("007") == codes.code_key("7") == "7"
    assert codes.code_key("WK-07") != codes.code_key("WK-7")  # seuls les codes purement numériques


def test_code_longer_than_24_characters_is_rejected():
    with pytest.raises(codes.InvalidCode):
        codes.normalize_code("X" * 25)


def test_natural_sort_puts_2_before_10():
    ordered = sorted(["10", "2", "WK-30", "WK-3", "1"], key=codes.natural_sort_key)
    assert ordered == ["1", "2", "10", "WK-3", "WK-30"]


# ---- F-37 : listes de codes


def test_one_card_per_line_with_name():
    assert codes.parse_code_list("57 Kylian Mbappé\nBTP-1 Josh Allen") == [
        ("57", "Kylian Mbappé"),
        ("BTP-1", "Josh Allen"),
    ]


def test_ranges_keep_leading_zeros():
    assert [c for c, _ in codes.parse_code_list("1-3")] == ["1", "2", "3"]
    assert [c for c, _ in codes.parse_code_list("001-003")] == ["001", "002", "003"]


def test_separators_and_duplicates():
    parsed = codes.parse_code_list("12, 14; 12\n007 7 WK-3 wk-3 #90")
    assert [c for c, _ in parsed] == ["12", "14", "007", "WK-3", "90"]


def test_hyphenated_code_is_not_a_range():
    assert [c for c, _ in codes.parse_code_list("OP17-045 WK-3")] == ["OP17-045", "WK-3"]


def test_compact_format_round_trips():
    owned = ["1", "2", "3", "5", "9", "10", "11", "WK-3", "001", "002"]
    text = codes.format_code_list(owned, compact=True)
    assert text == "1-3, 001-002, 5, 9-11, WK-3"
    assert {codes.code_key(c) for c, _ in codes.parse_code_list(text)} == {codes.code_key(c) for c in owned}


# ---- F-09 : recherche (CA-12)


@pytest.mark.parametrize("case", VECTORS["queries"], ids=lambda c: c["q"])
def test_search_vectors(case):
    terms = search.parse_query(case["q"])
    found = [
        card["id"]
        for card in VECTORS["cards"]
        if search.matches(terms, search.card_tokens(card["code"], card["name"], card["group"], card["teams"]))
    ]
    assert found == case["expect"]


# ---- RG-15 : avancement


def test_progress_on_base_when_types_are_mixed_and_a_base_card_is_owned():
    p = progress({"base": 200, "insert": 100}, {"base": 50, "insert": 10})
    assert (p.owned, p.total, p.scope, p.label) == (50, 200, "base", "25 %")


def test_progress_on_whole_series_without_base_card():
    p = progress({"base": 200, "insert": 100}, {"insert": 3})
    assert (p.owned, p.total, p.scope, p.label) == (3, 300, "all", "1 %")


def test_progress_below_one_percent():
    assert progress({"base": 4042}, {"base": 1}).label == "<1 %"
    assert progress({"base": 4042}, {}).label == "0 %"


def test_progress_is_rounded_down():
    assert progress({"base": 300}, {"base": 299}).label == "99 %"


# ---- RG-05, RG-06, RG-09


def test_doubles():
    assert [doubles(q) for q in (0, 1, 2, 5)] == [0, 0, 1, 4]


@pytest.mark.parametrize(
    ("variant", "group", "expected"),
    [
        ("Gold 35/50", "", True),
        ("Refractor", "", True),
        ("Base", "", False),
        ("", "", False),
        ("Auto", "", False),
        ("Rookie Patch Auto", "", False),
        ("Rookie Patch Auto Bronze 08/49", "", True),
        ("Current Stars Auto", "Current Stars Auto", False),
        ("Current Stars Auto · Orange 02/25", "Current Stars Auto", True),
    ],
)
def test_is_parallel_variant(variant, group, expected):
    assert is_parallel_variant(variant, group) is expected


def test_numbering():
    assert numbering("Gold 35/50") == (35, 50)
    assert numbering("Refractor") is None
    assert numbering("Orange 60/25") is None
