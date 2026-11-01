// Маскот — пингвин в цвете выбранной темы. Позы: спокойно стоит, машет одним крылом, радуется обоими.
// Рисунок встроен в страницу (а не <img>), чтобы его красили переменные темы — и на карточках выбора темы тоже.
// На экранах помощи и в уточняющем блоке его нет: там нужен спокойный тон без игровых элементов.
import { PENGUIN_POSES } from "./penguin-art";

export type Pose = "standing" | "one-wing" | "both-wings";

const ALT: Record<Pose, string> = {
  standing: "Пингвин",
  "one-wing": "Пингвин машет крылом",
  "both-wings": "Пингвин радуется",
};

// Детали по теме (видна только своя — globals.css, --acc-*). Рисуются поверх, в координатах того же viewBox.
const ACCESSORIES = `
<g class="p-acc-pink">
  <g stroke="var(--p-ink)" stroke-width="4" stroke-linecap="round" fill="none">
    <path d="M140 94 L131 84"/><path d="M150 88 L145 76"/><path d="M162 86 L162 74"/>
    <path d="M260 94 L269 84"/><path d="M250 88 L255 76"/><path d="M238 86 L238 74"/>
  </g>
  <path d="M200 44 C194 30 206 18 216 24 C224 30 216 42 207 36" stroke="var(--p-dark)" stroke-width="7" stroke-linecap="round" fill="none"/>
  <ellipse cx="136" cy="184" rx="15" ry="8" fill="#F29BB2" opacity="0.75"/>
  <ellipse cx="264" cy="184" rx="15" ry="8" fill="#F29BB2" opacity="0.75"/>
</g>
<g class="p-acc-sage">
  <path d="M202 44 C200 24 218 10 242 12 C240 34 224 46 202 44 Z" fill="#8CC48A"/>
  <path d="M206 40 C216 30 226 22 236 17" stroke="#5E9A5C" stroke-width="3" stroke-linecap="round" fill="none"/>
</g>
<g class="p-acc-lavender">
  <path d="M244 60 L222 44 Q216 58 224 74 Z" fill="#F4C7DA"/>
  <path d="M244 60 L266 44 Q272 58 264 74 Z" fill="#F4C7DA"/>
  <circle cx="244" cy="60" r="8" fill="#E9A8C3"/>
</g>
<g class="p-acc-sand">
  <path d="M100 222 C150 242 250 242 300 222 L304 246 C252 268 148 268 96 246 Z" fill="#6E8F8C"/>
  <path d="M236 250 L246 300 L268 296 L262 248 Z" fill="#5E7E7B"/>
  <path d="M120 236 C160 250 240 250 282 236" stroke="#8FB0AD" stroke-width="3" stroke-dasharray="2 9" stroke-linecap="round" fill="none"/>
</g>`;

export default function Mascot({ pose = "standing", size = 96, className = "" }: {
  pose?: Pose;
  size?: number;
  className?: string;
}) {
  return (
    <svg viewBox="0 0 400 500" width={size} height={size * 1.25} role="img" aria-label={ALT[pose]}
         className={`shrink-0 select-none ${className}`}
         dangerouslySetInnerHTML={{ __html: PENGUIN_POSES[pose] + ACCESSORIES }} />
  );
}

/** Пингвин с репликой в облачке. */
export function MascotSays({ pose = "standing", size = 84, children }: {
  pose?: Pose;
  size?: number;
  children: React.ReactNode;
}) {
  return (
    <div className="mt-4 flex items-end gap-3">
      <Mascot pose={pose} size={size} />
      <div className="relative mb-6 flex-1 rounded-3xl bg-surface px-4 py-3 text-[15px] leading-snug font-semibold text-ink shadow-soft">
        {children}
        <span aria-hidden className="absolute -left-[7px] bottom-4 size-4 rotate-45 bg-surface" />
      </div>
    </div>
  );
}
