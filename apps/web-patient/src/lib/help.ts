// Экран помощи без сервера: телефоны и тексты берутся из закэшированного контента (§5.5).
import type { Bootstrap, Contact, HelpScreen, Phone } from "./types";

/** Телефоны для региона: сначала «всегда показывать» (112, линия помощи), потом региональные. */
export function phonesFor(catalog: Bootstrap["help_phones"], region: string | null): Phone[] {
  const always = catalog.always_show.map((id) => catalog.phones.find((p) => p.id === id)).filter(Boolean) as Phone[];
  const regional = catalog.phones.filter((p) => region && p.region === region && !catalog.always_show.includes(p.id));
  return [...always, ...regional];
}

/** Тот же экран, что строит сервер (services/screens.py), — когда ответа сервера нет или его не ждём. */
export function localScreen(content: Bootstrap, key: string, region: string | null): HelpScreen {
  const screen = content.suicide_block.screens[key];
  const catalog = content.help_phones;
  const helpline = catalog.phones.find((p) => p.id === catalog.helpline_default)!;
  return {
    key,
    text: screen.text,
    fullscreen: screen.fullscreen,
    actions: screen.actions.map((action) => ({ action, label: content.suicide_block.action_labels[action] })),
    phones: phonesFor(catalog, region),
    helpline,
  };
}

export type ActionLink = { label: string; href: string; kind: "call" | "link" } | null;

/** Кнопка экрана помощи → звонок или переход. «Позвонить близкому» — первый контакт с телефоном из плана. */
export function actionLink(
  action: { action: string; label: string },
  screen: HelpScreen,
  contacts: Contact[] = [],
): ActionLink {
  switch (action.action) {
    case "call_112":
      return { label: action.label, href: "tel:112", kind: "call" };
    case "call_helpline":
      return { label: action.label, href: `tel:${screen.helpline.tel}`, kind: "call" };
    case "call_trusted_contact": {
      const person = contacts.find((c) => c.phone);
      return person ? { label: `${action.label}: ${person.name}`, href: `tel:${telOf(person.phone!)}`, kind: "call" } : null;
    }
    case "open_safety_plan":
      return { label: action.label, href: "/safety-plan", kind: "link" };
    case "show_help_phones":
      return null; // телефоны и так показаны списком под текстом
    default:
      return null;
  }
}

export function telOf(phone: string): string {
  return phone.replace(/[^\d+]/g, "");
}

/** Вопросы уточняющего блока, которые видны при текущих ответах (q3–q5 — только после «да» на q2). */
export function visibleRiskQuestions<Q extends { id: string; shown_if: Record<string, boolean> | null }>(
  questions: Q[],
  answers: Record<string, boolean | undefined>,
): Q[] {
  return questions.filter(
    (q) => !q.shown_if || Object.entries(q.shown_if).every(([id, value]) => answers[id] === value),
  );
}
