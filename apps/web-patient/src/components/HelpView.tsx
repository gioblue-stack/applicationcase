// Экран помощи: текст, кнопки звонка и все телефоны региона (§5.5, §7.1, §7.6).
import Link from "next/link";
import { actionLink } from "@/lib/help";
import type { Contact, HelpScreen } from "@/lib/types";

export default function HelpView({ screen, contacts = [] }: { screen: HelpScreen; contacts?: Contact[] }) {
  const links = screen.actions.map((a) => actionLink(a, screen, contacts)).filter(Boolean);
  return (
    <div className={screen.fullscreen ? "rounded-2xl bg-red-50 p-5 ring-1 ring-red-200" : "rounded-2xl bg-surface p-5"}>
      <p className="text-lg leading-relaxed">{screen.text}</p>
      <div className="mt-5 flex flex-col gap-3">
        {links.map((link) =>
          link!.kind === "call" ? (
            <a key={link!.href} href={link!.href}
               className="rounded-2xl bg-help btn-solid-red px-4 py-4 text-center text-lg font-semibold text-white">
              {link!.label}
            </a>
          ) : (
            <Link key={link!.href} href={link!.href}
                  className="rounded-2xl bg-surface px-4 py-4 text-center text-lg font-semibold text-brand-800 ring-1 ring-brand-600">
              {link!.label}
            </Link>
          ),
        )}
      </div>
      <h2 className="mt-6 text-sm font-semibold uppercase tracking-wide text-muted">Телефоны помощи</h2>
      <ul className="mt-2 divide-y divide-line">
        {screen.phones.map((p) => (
          <li key={p.id} className="py-3">
            <a href={`tel:${p.tel}`} className="block">
              <span className="text-lg font-semibold text-brand-800">{p.display}</span>
              <span className="block text-sm text-muted">{p.service}</span>
              <span className="block text-xs text-muted">{p.hours}</span>
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
