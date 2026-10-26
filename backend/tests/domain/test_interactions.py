import json

import pytest

from app.content.loader import load_content
from app.core.config import get_settings
from app.domain.interactions import SubstanceInfo, check_against, check_pair, needs_doctor, substance_from_content

CONTENT = load_content()
VECTORS = json.loads((get_settings().content_dir / "test_vectors" / "interactions.json").read_text(encoding="utf-8"))


def info(substance_id):
    return substance_from_content(CONTENT, substance_id)


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["name"])
def test_shared_vectors(case):
    other = info(case["b"]) if "b" in case else SubstanceInfo(None, case["free"])
    findings = check_pair(info(case["a"]), other, CONTENT)
    assert [f.severity for f in findings] == case["expected"]
    assert [f.rule_id for f in findings] == case["rules"]


def test_assistant_never_says_it_is_safe():
    texts = {r.patient_text for r in CONTENT.interactions.rules} | {CONTENT.interactions.unknown_text}
    for text in texts:
        assert "можно" not in text.lower() and "безопасн" not in text.lower(), text


def test_unknown_combination_goes_to_doctor():
    [finding] = check_pair(info("sertraline"), SubstanceInfo(None, "Парацетамол"), CONTENT)
    assert (finding.patient_text, finding.ask_doctor) == ("Данных о сочетании нет", True)


def test_check_against_sorts_by_danger_and_skips_same_substance():
    findings = check_against(info("alcohol"), [info("phenazepam"), info("sertraline"), info("alcohol")], CONTENT)
    assert [f.severity for f in findings] == ["red", "info", "info"]
    assert needs_doctor(findings)
    assert not needs_doctor(check_pair(info("sertraline"), info("alcohol"), CONTENT))
