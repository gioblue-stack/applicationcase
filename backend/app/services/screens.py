"""Экраны помощи для пациента: текст, кнопки и телефоны по региону (§5.5, §7.1, §7.6)."""

from __future__ import annotations

from dataclasses import dataclass

from app.content.models import Content, HelpPhone
from app.domain.help_phones import phones_for_region


@dataclass(frozen=True)
class ScreenAction:
    action: str
    label: str


@dataclass(frozen=True)
class HelpScreen:
    key: str
    text: str
    fullscreen: bool
    actions: list[ScreenAction]
    phones: list[HelpPhone]
    helpline: HelpPhone


def build_screen(content: Content, key: str, region_code: str | None) -> HelpScreen:
    screen = content.suicide_block.screens[key]
    labels = content.suicide_block.action_labels
    catalog = content.help_phones
    helpline = next(p for p in catalog.phones if p.id == catalog.helpline_default)
    return HelpScreen(
        key=key,
        text=screen.text,
        fullscreen=screen.fullscreen,
        actions=[ScreenAction(action=a, label=labels[a]) for a in screen.actions],
        phones=phones_for_region(catalog, region_code),
        helpline=helpline,
    )


def help_screen_for(content: Content, region_code: str | None, *, has_doctor: bool) -> HelpScreen:
    """Экран помощи вне уточняющего блока: у пользователя без врача — свой текст, без упоминания врача."""
    return build_screen(content, "help" if has_doctor else "self_user_help", region_code)
