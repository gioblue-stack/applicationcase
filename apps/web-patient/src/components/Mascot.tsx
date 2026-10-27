// Маскот — синий пингвин. Позы: спокойно стоит, машет одним крылом, радуется обоими.
// На экранах помощи и в уточняющем блоке его нет: там нужен спокойный тон без игровых элементов.
import Image from "next/image";

export type Pose = "standing" | "one-wing" | "both-wings";

const ALT: Record<Pose, string> = {
  standing: "Пингвин",
  "one-wing": "Пингвин машет крылом",
  "both-wings": "Пингвин радуется",
};

export default function Mascot({ pose = "standing", size = 96, className = "" }: {
  pose?: Pose;
  size?: number;
  className?: string;
}) {
  return (
    <Image src={`/mascot/${pose}.svg`} alt={ALT[pose]} width={size} height={size * 1.25} priority
           className={`shrink-0 select-none ${className}`} draggable={false} />
  );
}

/** Пингвин с репликой в облачке — как подсказки в Duolingo. */
export function MascotSays({ pose = "standing", size = 88, children }: {
  pose?: Pose;
  size?: number;
  children: React.ReactNode;
}) {
  return (
    <div className="mt-4 flex items-end gap-3">
      <Mascot pose={pose} size={size} />
      <div className="relative mb-6 flex-1 rounded-2xl border-2 border-brand-100 bg-white px-4 py-3 text-[15px] leading-snug font-semibold text-brand-900">
        {children}
        <span aria-hidden
              className="absolute -left-[9px] bottom-4 size-4 rotate-45 border-b-2 border-l-2 border-brand-100 bg-white" />
      </div>
    </div>
  );
}
