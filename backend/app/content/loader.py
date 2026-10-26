from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.content.models import Content
from app.core.config import get_settings


def _read(path: Path) -> object:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def load_content(content_dir: Path | None = None) -> Content:
    root = content_dir or get_settings().content_dir
    return Content.model_validate(
        {
            "phq9": _read(root / "instruments" / "phq9.ru.v1.json"),
            "gad7": _read(root / "instruments" / "gad7.ru.v1.json"),
            "suicide_block": _read(root / "instruments" / "suicide_block.ru.v1.json"),
            "help_phones": _read(root / "help_phones.json"),
            "thresholds": _read(root / "thresholds.json"),
            "diary": _read(root / "instruments" / "diary.ru.v1.json"),
            "patient_texts": _read(root / "patient_texts.ru.json"),
            "crisis_words": _read(root / "crisis_words.ru.json"),
            "alarming_symptoms": _read(root / "alarming_symptoms.ru.json"),
            "drugs": _read(root / "drugs_demo.json"),
            "treatment_texts": _read(root / "treatment_texts.ru.json"),
            "consent": _read(root / "consent.ru.json"),
            "icd": _read(root / "icd10_subset.json"),
            "assistant": _read(root / "assistant_tree.ru.json"),
            "approved_texts": _read(root / "approved_texts.ru.json"),
            "interactions": _read(root / "interaction_rules.json"),
        }
    )
