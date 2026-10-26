"use client";
// Графики дневника: пропущенный день — разрыв линии (connectNulls={false}), на тех же графиках —
// вертикальные отметки изменений лечения (§1.1).
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { diaryRows, markersInRange } from "@/lib/charts";
import { DIARY_METRICS, MARKER_KIND, formatDate } from "@/lib/labels";
import type { DiaryChart } from "@/lib/types";

const short = (day: string) => formatDate(day).slice(0, 5);

export function DiaryCharts({ chart }: { chart: DiaryChart }) {
  const rows = diaryRows(chart.series);
  const markers = markersInRange(chart.markers, chart.start, chart.end);
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {DIARY_METRICS.map((metric) => (
        <figure key={metric.key} className="rounded border bg-white p-3">
          <figcaption className="mb-1 text-sm font-medium">{metric.label}</figcaption>
          <div className="h-40">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: -24 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="day" tickFormatter={short} fontSize={11} minTickGap={16} />
                <YAxis domain={[0, metric.max]} fontSize={11} allowDecimals={false} />
                <Tooltip labelFormatter={(d) => formatDate(String(d))}
                         formatter={(v) => [v ?? "нет данных", metric.label]} />
                {markers.map((m) => (
                  <ReferenceLine key={`${m.prescription_id}-${m.day}-${m.kind}`} x={m.day} stroke="#6366f1"
                                 strokeDasharray="4 2"
                                 label={{ value: MARKER_KIND[m.kind] ?? m.kind, fontSize: 10, position: "top" }} />
                ))}
                <Line type="monotone" dataKey={metric.key} stroke="#0f172a" strokeWidth={2} dot={{ r: 2 }}
                      connectNulls={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </figure>
      ))}
    </div>
  );
}
