import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Faturamento · CONAP Ferramentas", template: "%s · Faturamento · CONAP" },
  description: "Acompanhamento mensal de faturamento por empresa: relatório da SEFAZ × sistema contábil.",
  robots: { index: false, follow: false },
  icons: { icon: "/icone.png" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f6f3" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0b0d" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
