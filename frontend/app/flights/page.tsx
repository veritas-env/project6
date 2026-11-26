"use client";

import { useCallback, useEffect, useState } from "react";
import Shell, { useSession } from "@/components/Shell";
import { api, errorMessage, money, type Flight } from "@/lib/api";

function time(s: string) { return new Date(s).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }); }

export default function FlightsPage() {
  const session = useSession();
  const [flights, setFlights] = useState<Flight[]>([]);
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [booking, setBooking] = useState<Flight | null>(null);
  const [passengers, setPassengers] = useState(1);

  const load = useCallback(() => {
    const qs = new URLSearchParams();
    if (origin) qs.set("origin", origin);
    if (destination) qs.set("destination", destination);
    api<Flight[]>(`/api/v1/flights?${qs}`).then(setFlights).catch((e) => setError(errorMessage(e)));
  }, [origin, destination]);
  useEffect(load, [load]);

  async function confirm() {
    if (!booking) return;
    try {
      await api("/api/v1/bookings", { method: "POST", json: { flight_id: booking.id, passengers, contact_email: session?.user.email } });
      setBooking(null);
      window.location.assign("/bookings");
    } catch (e) { setError(errorMessage(e)); }
  }

  return (
    <Shell>
      <h1 className="mb-6">Find flights</h1>
      {error && <p className="error mb-4" role="alert">{error}</p>}
      <div className="card mb-6 flex flex-wrap items-end gap-3">
        <div><label className="label" htmlFor="o">From</label><input id="o" className="input w-28 uppercase" maxLength={3} placeholder="LHR" value={origin} onChange={(e) => setOrigin(e.target.value.toUpperCase())} /></div>
        <div><label className="label" htmlFor="d">To</label><input id="d" className="input w-28 uppercase" maxLength={3} placeholder="JFK" value={destination} onChange={(e) => setDestination(e.target.value.toUpperCase())} /></div>
        <button className="btn" onClick={load}>Search</button>
      </div>
      <div className="space-y-3">
        {flights.map((f) => (
          <div key={f.id} className="card flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="font-mono text-xs text-slate-500">{f.flight_number} · {f.cabin}</div>
              <div className="text-lg font-medium">{f.origin} → {f.destination}</div>
              <div className="text-sm text-slate-500">{time(f.departs_at)} — {time(f.arrives_at)} · {f.seats_available} seats left</div>
            </div>
            <div className="text-right">
              <div className="text-xl font-semibold">{money(f.price_cents)}</div>
              <button className="btn mt-1" disabled={f.seats_available < 1} onClick={() => { setBooking(f); setPassengers(1); }}>Book</button>
            </div>
          </div>
        ))}
        {flights.length === 0 && <p className="text-slate-500">No flights match your search.</p>}
      </div>

      {booking && (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-900/30" onClick={() => setBooking(null)}>
          <div className="card w-full max-w-sm space-y-4" onClick={(e) => e.stopPropagation()}>
            <h2>Book {booking.origin} → {booking.destination}</h2>
            <p className="text-sm text-slate-500">{time(booking.departs_at)} · {booking.flight_number}</p>
            <label className="block text-sm">Passengers
              <select className="input" value={passengers} onChange={(e) => setPassengers(Number(e.target.value))}>
                {Array.from({ length: Math.min(9, booking.seats_available) }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <div className="flex items-center justify-between">
              <span className="text-lg font-semibold">{money(booking.price_cents * passengers)}</span>
              <div className="flex gap-2"><button className="btn-quiet" onClick={() => setBooking(null)}>Cancel</button><button className="btn" onClick={confirm}>Confirm</button></div>
            </div>
            <p className="text-xs text-slate-400">You'll earn {Math.floor((booking.price_cents * passengers) / 100)} loyalty points.</p>
          </div>
        </div>
      )}
    </Shell>
  );
}
