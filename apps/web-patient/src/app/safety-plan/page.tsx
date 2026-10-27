// План безопасности (§2.5): свои сигналы, что помогает, близкие и специалисты. Каждое сохранение — новая версия.
"use client";

import { useEffect, useState } from "react";
import Shell, { Card, ErrorText, PrimaryButton } from "@/components/Shell";
import { api } from "@/lib/client";
import { saveHelpProfile } from "@/lib/local";
import type { Contact, SafetyPlan } from "@/lib/types";

const TEXTS = [
  { key: "warning_signs", label: "Мои тревожные сигналы", hint: "Мысли, чувства, ситуации, после которых становится хуже" },
  { key: "coping_strategies", label: "Что мне помогает", hint: "Что я могу сделать сам(а), чтобы стало легче" },
  { key: "means_restriction", label: "Как сделать обстановку безопаснее", hint: "Например, отдать лекарства на хранение близкому" },
] as const;

type Draft = { warning_signs: string; coping_strategies: string; means_restriction: string; contacts: Contact[]; professionals: Contact[] };

function toDraft(plan: SafetyPlan | null): Draft {
  return {
    warning_signs: plan?.warning_signs ?? "",
    coping_strategies: plan?.coping_strategies ?? "",
    means_restriction: plan?.means_restriction ?? "",
    contacts: plan?.contacts ?? [],
    professionals: plan?.professionals ?? [],
  };
}

function Contacts({ title, list, onChange }: { title: string; list: Contact[]; onChange: (list: Contact[]) => void }) {
  const update = (i: number, patch: Partial<Contact>) => onChange(list.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  return (
    <Card>
      <p className="font-semibold">{title}</p>
      {list.map((c, i) => (
        <div key={i} className="mt-2 flex gap-2">
          <input value={c.name} onChange={(e) => update(i, { name: e.target.value })} placeholder="Имя"
                 className="w-1/2 rounded-lg border border-gray-300 px-2 py-2" />
          <input value={c.phone ?? ""} onChange={(e) => update(i, { phone: e.target.value || null })} placeholder="Телефон"
                 inputMode="tel" className="w-1/2 rounded-lg border border-gray-300 px-2 py-2" />
          <button type="button" aria-label="Удалить" onClick={() => onChange(list.filter((_, j) => j !== i))}
                  className="px-2 text-gray-400">✕</button>
        </div>
      ))}
      <button type="button" onClick={() => onChange([...list, { name: "", phone: null }])}
              className="mt-3 text-sm text-teal-700">+ Добавить</button>
    </Card>
  );
}

export default function SafetyPlanPage() {
  const [plan, setPlan] = useState<SafetyPlan | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api<SafetyPlan | null>("me/safety-plan")
      .then((p) => { setPlan(p); setDraft(toDraft(p)); setEditing(!p); })
      .catch((e) => setError((e as Error).message));
  }, []);

  async function save() {
    setError("");
    try {
      const clean = (list: Contact[]) =>
        list.filter((c) => c.name.trim()).map((c) => ({ name: c.name.trim(), phone: c.phone?.trim() || null }));
      const p = await api<SafetyPlan>("me/safety-plan", {
        method: "PUT",
        body: {
          warning_signs: draft!.warning_signs.trim() || null,
          coping_strategies: draft!.coping_strategies.trim() || null,
          means_restriction: draft!.means_restriction.trim() || null,
          contacts: clean(draft!.contacts),
          professionals: clean(draft!.professionals),
        },
      });
      setPlan(p);
      setDraft(toDraft(p));
      setEditing(false);
      setSaved(true);
      saveHelpProfile({ contacts: p.contacts });
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (!draft) return <Shell title="План безопасности" back><ErrorText>{error}</ErrorText></Shell>;

  if (!editing && plan) {
    const groups = [
      { title: "Близкие, кому я могу позвонить", list: plan.contacts },
      { title: "Специалисты", list: plan.professionals },
    ].filter((g) => g.list.length > 0);
    return (
      <Shell title="План безопасности" back>
        {saved && <p className="mt-3 rounded-lg bg-teal-50 p-3 text-sm text-teal-900">Сохранено. Врач увидит новую версию.</p>}
        {TEXTS.filter((t) => plan[t.key]).map((t) => (
          <Card key={t.key}>
            <p className="text-sm font-semibold text-gray-500">{t.label}</p>
            <p className="mt-1 whitespace-pre-line">{plan[t.key]}</p>
          </Card>
        ))}
        {groups.map((g) => (
          <Card key={g.title}>
            <p className="text-sm font-semibold text-gray-500">{g.title}</p>
            {g.list.map((c) => (
              <p key={`${c.name}${c.phone}`} className="mt-2">
                {c.name}{c.phone && <> — <a href={`tel:${c.phone}`} className="font-semibold text-teal-800">{c.phone}</a></>}
              </p>
            ))}
          </Card>
        ))}
        <PrimaryButton onClick={() => { setEditing(true); setSaved(false); }} className="mt-4">Изменить</PrimaryButton>
      </Shell>
    );
  }

  return (
    <Shell title="План безопасности" back>
      <p className="mt-2 text-sm text-gray-600">Заполните, когда вам спокойно. В трудную минуту план откроется на экране помощи.</p>
      {TEXTS.map((t) => (
        <Card key={t.key}>
          <label className="font-semibold" htmlFor={t.key}>{t.label}</label>
          <p className="text-xs text-gray-500">{t.hint}</p>
          <textarea id={t.key} value={draft[t.key]} onChange={(e) => setDraft({ ...draft, [t.key]: e.target.value })}
                    rows={3} maxLength={1000} className="mt-2 w-full rounded-lg border border-gray-300 p-2" />
        </Card>
      ))}
      <Contacts title="Близкие, кому я могу позвонить" list={draft.contacts}
                onChange={(contacts) => setDraft({ ...draft, contacts })} />
      <Contacts title="Специалисты" list={draft.professionals}
                onChange={(professionals) => setDraft({ ...draft, professionals })} />
      <ErrorText>{error}</ErrorText>
      <PrimaryButton onClick={save} className="mt-4">Сохранить</PrimaryButton>
    </Shell>
  );
}
