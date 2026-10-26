"""Публичный контент для приложения: открывается без входа и кэшируется на устройстве.

Экран помощи, телефоны и план действий должны работать без входа, PIN и интернета (§5.5),
поэтому всё необходимое для них отдаётся здесь. Персональных данных и врачебных пометок
(степени тяжести, «что может означать» симптом) в ответе нет.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.api.deps import ContentDep

router = APIRouter(prefix="/content", tags=["Контент"])

_INSTRUMENT_PUBLIC = {"severity_bands_doctor_only"}


@router.get("/bootstrap")
def bootstrap(content: ContentDep, response: Response) -> dict:
    response.headers["Cache-Control"] = "public, max-age=3600"
    return {
        "disclaimer": content.consent.disclaimer,
        "consent": content.consent.model_dump(mode="json", exclude={"source"}),
        "help_phones": content.help_phones.model_dump(mode="json"),
        "suicide_block": content.suicide_block.model_dump(mode="json"),
        "crisis_words": content.crisis_words.model_dump(mode="json"),
        "instruments": {
            "PHQ9": content.phq9.model_dump(mode="json", exclude=_INSTRUMENT_PUBLIC),
            "GAD7": content.gad7.model_dump(mode="json", exclude=_INSTRUMENT_PUBLIC),
            "DIARY": content.diary.model_dump(mode="json"),
        },
        "patient_texts": content.patient_texts.model_dump(mode="json"),
        "treatment_texts": content.treatment_texts.model_dump(mode="json"),
        "alarming_symptoms": content.alarming_symptoms.model_dump(
            mode="json", exclude={"source": True, "symptoms": {"__all__": {"doctor_meaning"}}}),
        "thresholds": content.thresholds.values,
        "assistant": content.assistant.model_dump(mode="json"),
        "interaction_substances": [s.model_dump(mode="json") for s in content.interactions.substances],
    }
