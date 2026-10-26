import { describe, expect, it } from "vitest";
import { coveragePercent, diaryRows, markersInRange, scoreRows } from "./charts";
import { FLAG_REASON, formatDate } from "./labels";
import type { DiarySeries, InstrumentHistory, TreatmentMarker } from "./types";

const series = {
  days: ["2026-10-24", "2026-10-25", "2026-10-26"],
  values: { mood: [0, null, 6], sleep_hours: [7.5, null, null] },
  meds_taken: ["all", null, null],
  had_side_effects: [false, null, null],
  filled_late: [false, null, true],
  filled_days: 2,
} as unknown as DiarySeries;

describe("diaryRows", () => {
  it("keeps a missed day as null (gap), never as 0", () => {
    const rows = diaryRows(series);
    expect(rows.map((r) => r.mood)).toEqual([0, null, 6]); // 0 — «очень плохое», null — пропуск
    expect(rows[1].sleep_hours).toBeNull();
    expect(rows.map((r) => r.day)).toEqual(series.days);
  });

  it("reports how many days were filled", () => {
    expect(coveragePercent(series)).toBe(67);
  });
});

describe("markersInRange", () => {
  it("keeps only treatment changes inside the chart period", () => {
    const markers = [
      { day: "2026-09-01", kind: "start" }, { day: "2026-10-25", kind: "dose_change" },
    ] as TreatmentMarker[];
    expect(markersInRange(markers, "2026-10-01", "2026-10-26").map((m) => m.kind)).toEqual(["dose_change"]);
  });
});

describe("scoreRows", () => {
  it("plots only valid weekly versions, superseded refills are hidden", () => {
    const histories = [
      { instrument: "PHQ9", points: [
        { submitted_at: "2026-10-19T09:00:00Z", total: 12, context: "weekly", superseded_by: null },
        { submitted_at: "2026-10-26T09:00:00Z", total: 20, context: "weekly", superseded_by: "x" },
        { submitted_at: "2026-10-26T09:05:00Z", total: 9, context: "weekly", superseded_by: null },
      ] },
      { instrument: "GAD7", points: [{ submitted_at: "2026-10-26T09:00:00Z", total: 6, context: "weekly", superseded_by: null }] },
    ] as unknown as InstrumentHistory[];
    expect(scoreRows(histories)).toEqual([
      { day: "2026-10-19", PHQ9: 12, GAD7: null },
      { day: "2026-10-26", PHQ9: 9, GAD7: 6 },
    ]);
  });
});

describe("labels", () => {
  it("has a Russian label for every flag reason of the backend", () => {
    const reasons = ["risk_block_emergency", "risk_block_red", "risk_block_dismissed", "risk_block_yellow",
      "panic_button", "crisis_words", "alarming_symptom", "phq9_increase", "gad7_increase", "missed_doses",
      "self_dose_change", "low_mood_streak", "new_side_effect", "no_data"];
    expect(reasons.filter((r) => !FLAG_REASON[r])).toEqual([]);
  });

  it("formats dates the Russian way", () => {
    expect(formatDate("2027-09-20")).toBe("20.09.2027");
  });
});
