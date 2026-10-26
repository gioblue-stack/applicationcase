"use client";
// PHQ-9 и GAD-7 по неделям (действующие заполнения).
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { scoreRows } from "@/lib/charts";
import { formatDate } from "@/lib/labels";
import type { InstrumentHistory } from "@/lib/types";

export function ScoresChart({ histories }: { histories: InstrumentHistory[] }) {
  const rows = scoreRows(histories);
  if (rows.length === 0) return <p className="text-sm text-slate-500">Опросников ещё нет.</p>;
  return (
    <div className="h-56 rounded border bg-white p-3">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="day" tickFormatter={(d) => formatDate(String(d)).slice(0, 5)} fontSize={11} />
          <YAxis domain={[0, 27]} fontSize={11} />
          <Tooltip labelFormatter={(d) => formatDate(String(d))} />
          <Legend />
          <Line dataKey="PHQ9" name="PHQ-9" stroke="#0f172a" strokeWidth={2} connectNulls={false}
                isAnimationActive={false} />
          <Line dataKey="GAD7" name="GAD-7" stroke="#0891b2" strokeWidth={2} connectNulls={false}
                isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
