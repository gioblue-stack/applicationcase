// Экран помощи: текст, кнопки звонка и все телефоны региона (§5.5, §7.1, §7.6).
import Link from "next/link";
import { actionLink } from "@/lib/help";
import type { Contact, HelpScreen } from "@/lib/types";

export default function HelpView({ screen, contacts = [] }: { screen: HelpScreen; contacts?: Contact[] }) {
  const links = screen.actions.map((a) => actionLink(a, screen, contacts)).filter(Boolean);
  return (
    <div className={screen.fullscreen ? "rounded-2xl bg-red-50 p-5 ring-1 ring-red-200" : "rounded-2xl bg-white p-5"}>
      <p className="text-lg leading-relaxed">{screen.text}</p>
      <div className="mt-5 flex flex-col gap-3">
        {links.map((link) =>
          link!.kind === "call" ? (
            <a key={link!.href} href={link!.href}
               className="rounded-xl bg-red-600 px-4 py-4 text-center text-lg font-semibold text-white active:bg-red-700">
              {link!.label}
            </a>
          ) : (
            <Link key={link!.href} href={link!.href}
                  className="rounded-xl bg-white px-4 py-4 text-center text-lg font-semibold text-teal-800 ring-1 ring-teal-600">
              {link!.label}
            </Link>
          ),
        )}
      </div>
      <h2 className="mt-6 text-sm font-semibold uppercase tracking-wide text-gray-500">Телефоны помощи</h2>
      <ul className="mt-2 divide-y divide-gray-200">
        {screen.phones.map((p) => (
          <li key={p.id} className="py-3">
            <a href={`tel:${p.tel}`} className="block">
              <span className="text-lg font-semibold text-teal-800">{p.display}</span>
              <span className="block text-sm text-gray-700">{p.service}</span>
              <span className="block text-xs text-gray-500">{p.hours}</span>
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
