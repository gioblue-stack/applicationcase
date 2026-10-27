// Еженедельный PHQ-9 / GAD-7 (§4.4, §4.5). Дословный текст опросника, результат — простым языком, «не диагноз».
"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useRef, useState } from "react";
import HelpView from "@/components/HelpView";
import Shell, { Card, ErrorText, PrimaryButton } from "@/components/Shell";
import { api, newId, nowIso } from "@/lib/client";
import { useContent } from "@/lib/content";
import type { HelpScreen, Today } from "@/lib/types";

type Result = {
  submission_id: string;
  feedback: { result_text: string; change_text: string | null; note: string };
  risk: { next_step: "none" | "risk_block" | "self_user_help"; screen: HelpScreen | null } | null;
};

export default function QuestionnairePage() {
  const { code } = useParams<{ code: "PHQ9" | "GAD7" }>();
  const router = useRouter();
  const content = useContent();
  const [answers, setAnswers] = useState<(number | null)[]>([]);
  const [difficulty, setDifficulty] = useState<number | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [next, setNext] = useState<"PHQ9" | "GAD7" | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const clientId = useRef(newId());

  const instrument = content?.instruments[code];
  if (!instrument) return <Shell title="Опросник" back>{null}</Shell>;
  const complete = instrument.items.every((_, i) => answers[i] != null);

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const r = await api<Result>("me/questionnaires", {
        method: "POST",
        body: { client_id: clientId.current, instrument: code, answers, difficulty, client_submitted_at: nowIso() },
      });
      if (r.risk?.next_step === "risk_block") {
        // 9-й вопрос PHQ-9 не «Ни разу» — сразу уточняющий блок (§4.6), результат подождёт.
        router.replace(`/risk?trigger=phq9_item9&ref=${r.submission_id}`);
        return;
      }
      setResult(r);
      const today = await api<Today>("me/today");
      setNext(today.weekly?.pending[0] ?? null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <Shell title={instrument.title} back>
        {result.risk?.screen && <div className="mt-4"><HelpView screen={result.risk.screen} /></div>}
        <Card>
          <p className="text-lg">{result.feedback.result_text}</p>
          {result.feedback.change_text && <p className="mt-2">{result.feedback.change_text}</p>}
          <p className="mt-3 text-sm text-gray-500">{result.feedback.note}</p>
        </Card>
        {next ? (
          <Link href={`/questionnaire/${next}`} replace
                className="mt-4 block rounded-xl bg-teal-600 py-3 text-center font-semibold text-white">
            Дальше: {content!.instruments[next].title}
          </Link>
        ) : (
          <Link href="/" className="mt-4 block text-center text-teal-700">На главную</Link>
        )}
      </Shell>
    );
  }

  return (
    <Shell title={instrument.title} back>
      <p className="mt-2 font-medium">{instrument.instruction}</p>
      {instrument.items.map((item, i) => (
        <Card key={item.no}>
          <p className="mb-3">{item.no}. {item.text}</p>
          <div className="grid grid-cols-2 gap-2">
            {instrument.options.map((o) => (
              <button key={o.value} type="button"
                      onClick={() => setAnswers(Object.assign([...answers], { [i]: o.value }))}
                      className={`rounded-lg px-2 py-2 text-sm ${answers[i] === o.value ? "bg-teal-600 font-semibold text-white" : "bg-gray-100"}`}>
                {o.label}
              </button>
            ))}
          </div>
        </Card>
      ))}
      {instrument.difficulty && (
        <Card>
          <p className="mb-3">{instrument.difficulty.text}</p>
          <div className="grid grid-cols-2 gap-2">
            {instrument.difficulty.options.map((o) => (
              <button key={o.value} type="button" onClick={() => setDifficulty(difficulty === o.value ? null : o.value)}
                      className={`rounded-lg px-2 py-2 text-sm ${difficulty === o.value ? "bg-teal-600 font-semibold text-white" : "bg-gray-100"}`}>
                {o.label}
              </button>
            ))}
          </div>
        </Card>
      )}
      <ErrorText>{error}</ErrorText>
      <PrimaryButton onClick={submit} disabled={busy || !complete} className="mt-4">
        {complete ? "Отправить" : "Ответьте на все вопросы"}
      </PrimaryButton>
      {instrument.copyright && <p className="mt-4 text-xs text-gray-400">{instrument.copyright}</p>}
    </Shell>
  );
}
