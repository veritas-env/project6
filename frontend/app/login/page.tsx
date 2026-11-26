"use client";

import { useState } from "react";
import { api, errorMessage, type Session } from "@/lib/api";

const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "TravelEase";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api<Session>("/api/v1/auth/login", { method: "POST", json: { email, password } });
      window.location.assign("/flights"); // fixed destination: no open redirect
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4" autoComplete="on">
        <h1>Sign in to {APP_NAME}</h1>
        {error && <p className="error" role="alert">{error}</p>}
        <div>
          <label className="label" htmlFor="email">Email</label>
          <input id="email" className="input" type="email" autoComplete="username" required maxLength={254}
                 value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="password">Password</label>
          <input id="password" className="input" type="password" autoComplete="current-password" required maxLength={128}
                 value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        <button className="btn w-full justify-center" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <p className="text-center text-sm text-slate-500">New here? <a className="text-sky-700 underline" href="/register">Create an account</a></p>
      </form>
    </main>
  );
}
