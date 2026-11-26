import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

export const metadata: Metadata = {
  title: process.env.NEXT_PUBLIC_APP_NAME ?? "TravelEase",
  robots: { index: false, follow: false },
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Reading headers makes every page render per request, so each gets its own CSP nonce.
  await headers();
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
