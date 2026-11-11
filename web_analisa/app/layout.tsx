import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Analisa Produk TikTok Shop",
  description: "Dashboard riset produk berbasis Kalodata Open API",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="id">
      <body>{children}</body>
    </html>
  );
}
