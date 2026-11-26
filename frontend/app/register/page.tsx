"use client";

import { useState } from "react";
import { api, errorMessage, type Session } from "@/lib/api";

const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "TravelEase";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api<Session>("/api/v1/auth/register", { method: "POST", json: { email, display_name: name, password } });
      window.location.assign("/flights");
    } catch (err) { setError(errorMessage(err)); setBusy(false); }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4">
        <h1>Create your {APP_NAME} account</h1>
        {error && <p className="error" role="alert">{error}</p>}
        <div><label className="label" htmlFor="name">Name</label><input id="name" className="input" required maxLength={100} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} /></div>
        <div><label className="label" htmlFor="email">Email</label><input id="email" className="input" type="email" required maxLength={254} autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
        <div><label className="label" htmlFor="pw">Password</label><input id="pw" className="input" type="password" required minLength={12} maxLength={128} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /><p className="mt-1 text-xs text-slate-500">At least 12 characters.</p></div>
        <button className="btn w-full justify-center" disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
        <p className="text-center text-sm text-slate-500">Already have an account? <a className="text-sky-700 underline" href="/login">Sign in</a></p>
      </form>
    </main>
  );
}
