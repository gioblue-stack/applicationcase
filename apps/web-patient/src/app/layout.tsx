import type { Metadata, Viewport } from "next";
import { Nunito } from "next/font/google";
import ServiceWorker from "@/components/ServiceWorker";
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
  themeColor: "#3b6fc4",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru" className={nunito.variable}>
      <body className="font-sans antialiased">
        {children}
        <ServiceWorker />
      </body>
    </html>
  );
}
