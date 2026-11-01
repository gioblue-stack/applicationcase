import type { Metadata, Viewport } from "next";
import { Nunito } from "next/font/google";
import ServiceWorker from "@/components/ServiceWorker";
import ThemeSync from "@/components/ThemeSync";
import { THEME_BOOT_SCRIPT } from "@/lib/theme";
import "./globals.css";

// Округлый шрифт в духе маскота; кириллица нужна для всего интерфейса.
const nunito = Nunito({ subsets: ["latin", "cyrillic"], weight: ["400", "600", "700", "800"], variable: "--font-nunito" });

export const metadata: Metadata = {
  title: "Дневник самочувствия",
  description: "Дневник, опросники, приём лекарств и связь с лечащим врачом",
  manifest: "/manifest.webmanifest",
  // iPhone: «На экран „Домой“» открывает сайт как отдельное приложение, без адресной строки.
  appleWebApp: { capable: true, title: "Самочувствие", statusBarStyle: "default" },
  icons: { icon: "/icons/icon-192.png", apple: "/icons/apple-touch-icon.png" },
  formatDetection: { telephone: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#2F6FA8", // меняется под тему и тёмный режим (ThemeSync)
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // data-theme / data-mode ставит скрипт до отрисовки — расхождение с серверной разметкой ожидаемо.
    <html lang="ru" className={nunito.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body className="font-sans antialiased">
        {children}
        <ThemeSync />
        <ServiceWorker />
      </body>
    </html>
  );
}
