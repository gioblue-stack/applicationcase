import hashlib
import json

import pytest
from pydantic import ValidationError

from app.content.loader import load_content
from app.content.models import Approval, SuicideBlockDef
from app.domain.enums import InstrumentCode

CONTENT = load_content()

# Тексты PHQ-9 и GAD-7 переносятся дословно (§4.1): изменение одного слова даёт непроверенный опросник.
# Если хеш изменился — это правка медицинского текста, её подтверждают врачи команды.
VERBATIM_SHA256 = {
    InstrumentCode.PHQ9: "e2cef50f27766a214fa3db644dd7e2dca6c2816b8f0b10dd52ed398007e16099",
    InstrumentCode.GAD7: "14e8ff44aa78731209576fb9552d5009e13d1acf2e44d604b7e23c99b7c7c077",
}


@pytest.mark.parametrize("code", list(VERBATIM_SHA256))
def test_questionnaire_texts_are_verbatim(code):
    instrument = CONTENT.instrument(code)
    payload = instrument.model_dump(
        include={"instruction", "options", "items", "difficulty", "copyright"}, mode="json"
    )
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    assert digest == VERBATIM_SHA256[code]


def test_gad7_uses_zolotareva_version_not_second_pfizer_translation():
    texts = " ".join(item.text for item in CONTENT.gad7.items)
    assert "нервничали" not in texts


def test_no_low_risk_wording_anywhere_in_protocol_texts():
    block = CONTENT.suicide_block
    texts = [block.intro.text, *(s.text for s in block.screens.values())]
    for text in texts:
        assert "низк" not in text.lower(), text


def test_medical_texts_without_signature_are_marked_draft():
    assert CONTENT.suicide_block.approval.status == "draft"
    assert CONTENT.suicide_block.approval.note


def test_approved_text_requires_doctor_name_and_date():
    with pytest.raises(ValidationError):
        Approval(status="approved")


def _block_with(**changes):
    raw = CONTENT.suicide_block.model_dump(mode="json")
    raw.update(changes)
    return raw


def test_block_rejects_follow_up_question_shown_without_q2():
    questions = CONTENT.suicide_block.model_dump(mode="json")["questions"]
    questions[2]["shown_if"] = None
    with pytest.raises(ValidationError, match="условие показа"):
        SuicideBlockDef.model_validate(_block_with(questions=questions))


def test_block_rejects_missing_dismissed_screen():
    screens = CONTENT.suicide_block.model_dump(mode="json")["screens"]
    del screens["dismissed"]
    with pytest.raises(ValidationError, match="dismissed"):
        SuicideBlockDef.model_validate(_block_with(screens=screens))


def test_block_rejects_hidden_help_phones_on_intro():
    intro = CONTENT.suicide_block.model_dump(mode="json")["intro"]
    intro["show_help_phones"] = False
    with pytest.raises(ValidationError, match="вступительном"):
        SuicideBlockDef.model_validate(_block_with(intro=intro))


def test_help_phones_include_112_and_federal_line():
    assert CONTENT.help_phones.always_show == ["112", "8-800-100-49-94"]
