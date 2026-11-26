"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { api, type Session } from "@/lib/api";

const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "TravelEase";
const SessionCtx = createContext<Session | null>(null);
export const useSession = () => useContext(SessionCtx);

export default function Shell({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    api<Session>("/api/v1/auth/me").then(setSession).catch(() => {});
  }, []);

  async function logout() {
    try { await api("/api/v1/auth/logout", { method: "POST" }); } finally { window.location.assign("/login"); }
  }

  const tabs = [
    { href: "/flights", label: "Find flights" },
    { href: "/bookings", label: "My trips" },
  ];

  return (
    <SessionCtx.Provider value={session}>
      <div className="min-h-screen">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3">
            <nav className="flex items-center gap-1">
              <Link href="/flights" className="mr-4 flex items-center gap-2 font-semibold">
                <span className="inline-block h-6 w-6 rounded bg-sky-600 text-center text-sm leading-6 text-white">T</span>{APP_NAME}
              </Link>
              {tabs.map((t) => (
                <Link key={t.href} href={t.href} className={`px-3 py-2 text-sm ${pathname.startsWith(t.href) ? "font-medium text-slate-900" : "text-slate-500 hover:text-slate-800"}`}>{t.label}</Link>
              ))}
            </nav>
            <div className="flex items-center gap-3 text-sm text-slate-600">
              {session && <span className="rounded bg-amber-50 px-2 py-1 text-amber-800">{session.user.loyalty_points.toLocaleString()} points</span>}
              {session?.user.is_platform_admin && <Link href="/admin" className="btn-quiet">Security alerts</Link>}
              {session && <span className="hidden sm:inline">{session.user.display_name}</span>}
              <button className="btn-quiet" onClick={logout}>Sign out</button>
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-6 py-8">{children}</main>
      </div>
    </SessionCtx.Provider>
  );
}
