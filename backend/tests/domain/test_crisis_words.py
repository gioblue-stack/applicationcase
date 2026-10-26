import json

import pytest

from app.content.loader import load_content
from app.core.config import get_settings
from app.domain.crisis_words import (
    CrisisMatcher,
    damerau_levenshtein,
    default_matcher,
    expand_optional_endings,
)

VECTORS = json.loads((get_settings().content_dir / "test_vectors" / "crisis_words.json").read_text(encoding="utf-8"))
MATCHER = default_matcher()


@pytest.mark.parametrize("case", VECTORS["positive"], ids=lambda c: c["text"])
def test_shared_positive_vectors(case):
    assert case["group"] in {m.group for m in MATCHER.find(case["text"])}


@pytest.mark.parametrize("text", VECTORS["negative"])
def test_shared_negative_vectors(text):
    assert MATCHER.find(text) == []


@pytest.mark.parametrize(
    "phrase", [p for g in load_content().crisis_words.groups for p in g.phrases]
)
def test_every_listed_phrase_matches_itself(phrase):
    for variant in expand_optional_endings(phrase):
        assert MATCHER.is_crisis(variant), variant


def test_negation_does_not_cancel():
    assert MATCHER.is_crisis("я точно не хочу умирать, просто устала")


def test_match_reports_canonical_phrase_from_the_list():
    [match] = MATCHER.find("скоро уйду из жизни")
    assert (match.phrase, match.group) == ("уйти из жизни", "direct")


def test_yo_and_e_are_equal():
    assert MATCHER.is_crisis("свести счёты с жизнью")
    assert MATCHER.is_crisis("свести счеты с жизнью")


def test_long_gap_between_phrase_words_does_not_match():
    # Больше двух посторонних слов между «не хочу» и «жить» — уже другой смысл.
    assert not CrisisMatcher(load_content().crisis_words).find("не хочу идти на работу, хочу жить дома")


def test_expand_optional_endings():
    assert expand_optional_endings("лучше бы я умер(ла)") == ["лучше бы я умер", "лучше бы я умерла"]
    assert expand_optional_endings("без скобок") == ["без скобок"]


@pytest.mark.parametrize(("a", "b", "d"), [("abc", "abc", 0), ("abc", "acb", 1), ("abc", "ab", 1), ("abc", "xyz", 3)])
def test_damerau_levenshtein(a, b, d):
    assert damerau_levenshtein(a, b) == d
