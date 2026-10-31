"use client";
// Новый пациент (§5.2): карточка → код приглашения и QR со ссылкой на сайт пациента. Только 18+.
import QRCode from "qrcode";
import { useState } from "react";
import { api } from "@/lib/client";
import { formatDateTime } from "@/lib/labels";
import type { InviteCard } from "@/lib/types";

const REGIONS = [
  { value: "moscow", label: "Москва" }, { value: "spb", label: "Санкт-Петербург" }, { value: "", label: "Другой" },
];

/** Сайт пациента: NEXT_PUBLIC_PATIENT_URL, иначе тот же хост на порту 3001 (локальный запуск). */
function patientSite() {
  return process.env.NEXT_PUBLIC_PATIENT_URL ?? `${window.location.protocol}//${window.location.hostname}:3001`;
}

export function NewPatient({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ full_name: "", birth_date: "", sex: "", city: "", region_code: "moscow" });
  const [invite, setInvite] = useState<{ card: InviteCard; link: string; qr: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [key]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const card = await api<InviteCard>("doctor/patients", {
        method: "POST",
        body: { full_name: form.full_name, birth_date: form.birth_date, sex: form.sex || null,
                city: form.city || null, region_code: form.region_code || null },
      });
      const link = `${patientSite()}/login?invite=${encodeURIComponent(card.invite_code)}`;
      setInvite({ card, link, qr: await QRCode.toDataURL(link, { margin: 1, width: 200 }) });
      onCreated();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function close() {
    setOpen(false);
    setInvite(null);
    setForm({ full_name: "", birth_date: "", sex: "", city: "", region_code: "moscow" });
  }

  if (!open) {
    return <button onClick={() => setOpen(true)} className="rounded bg-slate-800 px-3 py-1 text-sm text-white">
      + Новый пациент</button>;
  }

  if (invite) {
    return (
      <div className="mb-4 flex flex-wrap gap-6 rounded-lg bg-white p-4 shadow">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={invite.qr} alt="QR-код приглашения" width={200} height={200} />
        <div className="flex-1 space-y-2 text-sm">
          <p className="text-base font-semibold">Пациент добавлен</p>
          <p>Код приглашения: <b className="font-mono text-2xl tracking-widest">{invite.card.invite_code}</b></p>
          <p className="text-slate-600">Действует до {formatDateTime(invite.card.invite_expires_at)}.</p>
          <p>Пациент сканирует QR камерой телефона или открывает ссылку, входит по телефону и вводит код:</p>
          <p className="break-all font-mono text-xs">{invite.link}</p>
          <button onClick={close} className="rounded border px-3 py-1">Готово</button>
        </div>
      </div>
    );
  }

  const input = "mt-1 w-full rounded border px-2 py-1";
  return (
    <form onSubmit={submit} className="mb-4 grid gap-3 rounded-lg bg-white p-4 text-sm shadow sm:grid-cols-2">
      <p className="text-base font-semibold sm:col-span-2">Новый пациент</p>
      <label className="sm:col-span-2">ФИО
        <input required maxLength={200} value={form.full_name} onChange={set("full_name")} className={input} /></label>
      <label>Дата рождения
        <input required type="date" value={form.birth_date} onChange={set("birth_date")} className={input} /></label>
      <label>Пол
        <select value={form.sex} onChange={set("sex")} className={input}>
          <option value="">Не указан</option><option value="female">Женский</option><option value="male">Мужской</option>
        </select></label>
      <label>Город
        <input maxLength={100} value={form.city} onChange={set("city")} className={input} /></label>
      <label>Регион (для телефонов помощи)
        <select value={form.region_code} onChange={set("region_code")} className={input}>
          {REGIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
        </select></label>
      {error && <p role="alert" className="text-red-700 sm:col-span-2">{error}</p>}
      <div className="flex gap-2 sm:col-span-2">
        <button disabled={busy} className="rounded bg-slate-800 px-3 py-1 text-white">Создать и получить код</button>
        <button type="button" onClick={close} className="rounded border px-3 py-1">Отмена</button>
      </div>
    </form>
  );
}
