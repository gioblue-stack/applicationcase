// Шкала 0–10 кнопками. Повторное нажатие снимает ответ: «не ответил» ≠ 0 (§1.1).
"use client";

export default function Scale({ value, onChange, minLabel, maxLabel }: {
  value: number | null;
  onChange: (value: number | null) => void;
  minLabel?: string;
  maxLabel?: string;
}) {
  return (
    <div>
      <div className="grid grid-cols-11 gap-1">
        {Array.from({ length: 11 }, (_, n) => (
          <button key={n} type="button" aria-pressed={value === n} onClick={() => onChange(value === n ? null : n)}
                  className={`rounded-md py-2 text-sm ${value === n ? "bg-teal-600 font-semibold text-white" : "bg-gray-100"}`}>
            {n}
          </button>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-xs text-gray-500">
        <span>{minLabel}</span>
        <span>{maxLabel}</span>
      </div>
    </div>
  );
}
