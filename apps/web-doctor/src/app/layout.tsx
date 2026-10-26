import type { Metadata } from "next";
import "./globals.css";
import { DISCLAIMER } from "@/lib/labels";

export const metadata: Metadata = {
  title: "Кабинет врача — прототип",
  description: DISCLAIMER,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body className="antialiased min-h-screen bg-slate-50 text-slate-900">
        <div className="bg-slate-800 px-4 py-1 text-center text-xs text-slate-100">{DISCLAIMER}</div>
        {children}
      </body>
    </html>
  );
}
