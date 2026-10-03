import type { Metadata } from "next";
import { Cairo, Tajawal } from "next/font/google";
import "./globals.css";
import { LangProvider } from "@/lib/i18n";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { AiBanner } from "@/components/AiBanner";

const cairo = Cairo({ variable: "--font-cairo", subsets: ["arabic", "latin"], weight: ["500", "600", "700", "800"] });
const tajawal = Tajawal({ variable: "--font-tajawal", subsets: ["arabic", "latin"], weight: ["400", "500", "700"] });

export const metadata: Metadata = {
  title: "تحقّق — Tahaqqaq",
  description: "Verify hadith and Islamic texts against approved sources before you publish.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ar" dir="rtl" className={`${cairo.variable} ${tajawal.variable}`} suppressHydrationWarning>
      <body style={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
        <LangProvider>
          <a href="#main" className="skip-link">تخطي إلى المحتوى · Skip to content</a>
          <AiBanner />
          <div className="hero"><Header /></div>
          {children}
          <Footer />
        </LangProvider>
      </body>
    </html>
  );
}
