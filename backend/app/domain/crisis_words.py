"""Поиск кризисных слов в свободном тексте (§7.4).

Правила: без учёта регистра, «ё» = «е», поиск по основе слова, одна опечатка в словах длиннее
6 букв, отрицание срабатывание не отменяет. Ложное срабатывание безопаснее пропуска, поэтому
сравнение намеренно мягкое: основы совпадают по префиксу, между словами фразы допускаются
до двух посторонних слов («не хочу больше жить»).
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from functools import lru_cache

import snowballstemmer

from app.content.models import CrisisWords

_WORD = re.compile(r"[а-яa-z0-9]+")
_OPTIONAL_ENDING = re.compile(r"(\w+)\((\w+)\)")
_MAX_GAP = 2
_TYPO_MIN_LENGTH = 7  # «длиннее 6 букв»

_stemmer = snowballstemmer.stemmer("russian")
_stem_lock = threading.Lock()


@lru_cache(maxsize=4096)
def stem(word: str) -> str:
    with _stem_lock:  # объект стеммера не потокобезопасен
        return _stemmer.stemWord(word)


def normalize(text: str) -> list[str]:
    return _WORD.findall(text.lower().replace("ё", "е"))


def expand_optional_endings(phrase: str) -> list[str]:
    """«устал(а) жить» → «устал жить», «устала жить»."""
    match = _OPTIONAL_ENDING.search(phrase)
    if match is None:
        return [phrase]
    base, ending = match.groups()
    head, tail = phrase[: match.start()], phrase[match.end() :]
    return [
        variant
        for word in (base, base + ending)
        for variant in expand_optional_endings(head + word + tail)
    ]


def damerau_levenshtein(a: str, b: str) -> int:
    """Расстояние с перестановкой соседних букв (вариант OSA)."""
    prev2: list[int] = []
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[-1]


@dataclass(frozen=True)
class _Token:
    word: str
    stem: str

    @classmethod
    def of(cls, word: str) -> _Token:
        return cls(word, stem(word))


def _common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        n += 1
    return n


def tokens_match(text: _Token, pattern: _Token) -> bool:
    a, b = text.stem, pattern.stem
    if a == b:
        return True
    shorter = min(len(a), len(b))
    if shorter >= 3 and (a.startswith(b) or b.startswith(a)):
        return True
    prefix = _common_prefix(a, b)
    if prefix >= 4 and prefix >= shorter - 1:
        return True
    if len(pattern.word) >= _TYPO_MIN_LENGTH:
        return min(damerau_levenshtein(text.word, pattern.word), damerau_levenshtein(a, b)) <= 1
    return False


def _sequence_matches(text: list[_Token], pattern: tuple[_Token, ...]) -> bool:
    def rest(k: int, pos: int) -> bool:
        if k == len(pattern):
            return True
        for i in range(pos, min(len(text), pos + 1 + _MAX_GAP)):
            if tokens_match(text[i], pattern[k]) and rest(k + 1, i + 1):
                return True
        return False

    return any(tokens_match(t, pattern[0]) and rest(1, i + 1) for i, t in enumerate(text))


@dataclass(frozen=True)
class _Pattern:
    phrase: str  # фраза из списка §7.4
    group: str
    tokens: tuple[_Token, ...]


@dataclass(frozen=True)
class CrisisMatch:
    phrase: str
    group: str


class CrisisMatcher:
    def __init__(self, words: CrisisWords) -> None:
        self._patterns = [
            _pattern(variant, phrase, group.id)
            for group in words.groups
            for phrase in group.phrases
            for variant in expand_optional_endings(phrase)
        ] + [
            _pattern(form.phrase, form.form_of, words.group_of(form.form_of))
            for form in words.word_forms.phrases
        ]

    def find(self, text: str) -> list[CrisisMatch]:
        tokens = [_Token.of(w) for w in normalize(text)]
        found: dict[str, CrisisMatch] = {}
        for p in self._patterns:
            if p.phrase not in found and _sequence_matches(tokens, p.tokens):
                found[p.phrase] = CrisisMatch(phrase=p.phrase, group=p.group)
        return list(found.values())

    def is_crisis(self, text: str) -> bool:
        return bool(self.find(text))


def _pattern(text: str, phrase: str, group: str) -> _Pattern:
    return _Pattern(phrase=phrase, group=group, tokens=tuple(_Token.of(w) for w in normalize(text)))


@lru_cache
def default_matcher() -> CrisisMatcher:
    from app.content.loader import load_content

    return CrisisMatcher(load_content().crisis_words)
