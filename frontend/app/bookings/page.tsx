"use client";

import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, errorMessage, money, type Booking } from "@/lib/api";

function time(s: string) { return new Date(s).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }); }

export default function BookingsPage() {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<Booking[]>("/api/v1/bookings").then(setBookings).catch((e) => setError(errorMessage(e)));
  }, []);
  useEffect(load, [load]);

  async function cancel(b: Booking) {
    if (!confirm(`Cancel booking ${b.reference}? Your seats will be released.`)) return;
    try { await api(`/api/v1/bookings/${encodeURIComponent(b.id)}/cancel`, { method: "POST" }); load(); }
    catch (e) { setError(errorMessage(e)); }
  }

  return (
    <Shell>
      <h1 className="mb-6">My trips</h1>
      {error && <p className="error mb-4" role="alert">{error}</p>}
      <div className="space-y-3">
        {bookings.map((b) => (
          <div key={b.id} className={`card flex flex-wrap items-center justify-between gap-4 ${b.status === "cancelled" ? "opacity-60" : ""}`}>
            <div>
              <div className="font-mono text-xs text-slate-500">{b.reference} · {b.flight.flight_number}</div>
              <div className="text-lg font-medium">{b.flight.origin} → {b.flight.destination}</div>
              <div className="text-sm text-slate-500">{time(b.flight.departs_at)} · {b.passengers} passenger{b.passengers > 1 ? "s" : ""}</div>
            </div>
            <div className="text-right">
              <div className="font-semibold">{money(b.amount_cents)}</div>
              <div className="text-xs text-amber-700">+{b.points_earned} points</div>
              {b.status === "confirmed"
                ? <button className="btn-quiet mt-1 text-rose-700" onClick={() => cancel(b)}>Cancel</button>
                : <div className="mt-1 text-xs text-slate-500">Cancelled</div>}
            </div>
          </div>
        ))}
        {bookings.length === 0 && <p className="text-slate-500">You have no trips yet. <a className="text-sky-700 underline" href="/flights">Find a flight</a>.</p>}
      </div>
    </Shell>
  );
}
