"""Телефоны на экране помощи (§5.5, §7.6): всегда 112 и федеральный номер, плюс региональный."""

from __future__ import annotations

from app.content.models import HelpPhone, HelpPhones


def phones_for_region(catalog: HelpPhones, region: str | None) -> list[HelpPhone]:
    by_id = {phone.id: phone for phone in catalog.phones}
    result = [by_id[phone_id] for phone_id in catalog.always_show]
    if region:
        result += [p for p in catalog.phones if p.region == region and p.id not in catalog.always_show]
    return result
