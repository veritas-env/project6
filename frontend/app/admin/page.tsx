"use client";

import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, errorMessage, type Alert } from "@/lib/api";

const SEVERITY: Record<string, string> = {
  high: "bg-red-100 text-red-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-slate-100 text-slate-700",
};

export default function AdminPage() {
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<Alert[]>("/api/v1/admin/alerts").then(setAlerts).catch((e) => setError(errorMessage(e)));
  }, []);
  useEffect(load, [load]);

  async function ack(id: number) {
    try { await api(`/api/v1/admin/alerts/${id}/ack`, { method: "POST" }); load(); }
    catch (e) { setError(errorMessage(e)); }
  }

  return (
    <Shell>
      <h1 className="mb-6">Security alerts</h1>
      {error && <p className="error mb-4">{error}</p>}
      <div className="card overflow-x-auto p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-slate-500">
            <tr><th className="px-4 py-2">When</th><th className="px-4 py-2">Severity</th><th className="px-4 py-2">Alert</th><th className="px-4 py-2">Status</th><th /></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {alerts?.map((a) => (
              <tr key={a.id}>
                <td className="whitespace-nowrap px-4 py-2 text-slate-600">{new Date(a.at).toLocaleString()}</td>
                <td className="px-4 py-2"><span className={`rounded px-2 py-0.5 text-xs font-medium ${SEVERITY[a.severity] ?? SEVERITY.low}`}>{a.severity}</span></td>
                <td className="px-4 py-2">{a.summary}<div className="text-xs text-slate-500">{a.rule}</div></td>
                <td className="px-4 py-2 capitalize">{a.status}</td>
                <td className="px-4 py-2 text-right">{a.status === "open" && <button className="btn-quiet" onClick={() => ack(a.id)}>Acknowledge</button>}</td>
              </tr>
            ))}
            {alerts?.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-500">No alerts.</td></tr>}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
