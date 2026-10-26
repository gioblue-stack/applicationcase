import pytest

from app.content.loader import load_content
from app.domain.help_phones import phones_for_region
from app.domain.scoring import (
    InvalidQuestionnaire,
    safety_item_value,
    severity_band_for_doctor,
    total_score,
)

CONTENT = load_content()


def test_phq9_total_excludes_difficulty_question():
    assert total_score(CONTENT.phq9, [1, 2, 3, 0, 1, 2, 3, 0, 1]) == 13


def test_gad7_total():
    assert total_score(CONTENT.gad7, [3] * 7) == 21


@pytest.mark.parametrize("answers", [[0] * 8, [0] * 10, [0] * 8 + [4], [0] * 8 + [-1], [0] * 8 + [True]])
def test_phq9_rejects_invalid_answers(answers):
    with pytest.raises(InvalidQuestionnaire):
        total_score(CONTENT.phq9, answers)


@pytest.mark.parametrize(
    ("total", "label"),
    [(0, "Минимальная"), (4, "Минимальная"), (5, "Лёгкая"), (9, "Лёгкая"), (10, "Умеренная"),
     (15, "Умеренно тяжёлая"), (19, "Умеренно тяжёлая"), (20, "Тяжёлая"), (27, "Тяжёлая")],
)
def test_phq9_bands(total, label):
    assert severity_band_for_doctor(CONTENT.phq9, total) == label


@pytest.mark.parametrize(("total", "label"), [(4, "Минимальная"), (14, "Умеренная"), (15, "Тяжёлая"), (21, "Тяжёлая")])
def test_gad7_bands(total, label):
    assert severity_band_for_doctor(CONTENT.gad7, total) == label


def test_safety_item_is_phq9_question_9_regardless_of_total():
    # Сумма низкая, а сигнал есть: протокол запускается независимо от суммы (§4.4).
    assert safety_item_value(CONTENT.phq9, [0] * 8 + [1]) == 1
    assert safety_item_value(CONTENT.gad7, [0] * 7) is None


@pytest.mark.parametrize(
    ("region", "expected_ids"),
    [
        (None, ["112", "8-800-100-49-94"]),
        ("moscow", ["112", "8-800-100-49-94", "msk-051"]),
        ("spb", ["112", "8-800-100-49-94", "spb-neuroses"]),
        ("kazan", ["112", "8-800-100-49-94"]),
    ],
)
def test_help_phones_always_112_and_federal_plus_regional(region, expected_ids):
    assert [p.id for p in phones_for_region(CONTENT.help_phones, region)] == expected_ids
