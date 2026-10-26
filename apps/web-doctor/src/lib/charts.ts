// Подготовка данных для графиков. Пропуск остаётся null — Recharts рисует разрыв линии,
// а не падение до нуля (§1.1: «пропущенный день — это пропуск, а не ноль»).
import type { DiarySeries, InstrumentHistory, TreatmentMarker } from "./types";

export type DiaryRow = { day: string } & Record<string, number | null | string>;

export function diaryRows(series: DiarySeries): DiaryRow[] {
  return series.days.map((day, i) => {
    const row: DiaryRow = { day };
    for (const [metric, values] of Object.entries(series.values)) {
      row[metric] = values[i] ?? null;
    }
    return row;
  });
}

export function markersInRange(markers: TreatmentMarker[], start: string, end: string): TreatmentMarker[] {
  return markers.filter((m) => m.day >= start && m.day <= end);
}

export type ScoreRow = { day: string; PHQ9: number | null; GAD7: number | null };

/** Еженедельные баллы: только действующие версии (заменённые повторным заполнением не рисуются). */
export function scoreRows(histories: InstrumentHistory[]): ScoreRow[] {
  const rows = new Map<string, ScoreRow>();
  for (const h of histories) {
    for (const p of h.points) {
      if (p.superseded_by || p.context !== "weekly") continue;
      const day = p.submitted_at.slice(0, 10);
      const row = rows.get(day) ?? { day, PHQ9: null, GAD7: null };
      row[h.instrument as "PHQ9" | "GAD7"] = p.total;
      rows.set(day, row);
    }
  }
  return [...rows.values()].sort((a, b) => a.day.localeCompare(b.day));
}

export function coveragePercent(series: DiarySeries): number {
  return series.days.length ? Math.round((100 * series.filled_days) / series.days.length) : 0;
}
