"use client";

import { useState } from "react";
import { NeuralStream } from "@/components/hud/NeuralStream";
import { MonacoWorkbench } from "@/components/editor/MonacoWorkbench";
import { ViewportEngine } from "@/components/sandbox/ViewportEngine";
import { useTelemetry } from "@/lib/websocket";

export default function CommandCenterPage() {
  const { sendGoal, sessionId } = useTelemetry();
  const [goal, setGoal] = useState("Initialize Nexus Poly-Engine sandbox runtime");
  const [status, setStatus] = useState<string>("");

  async function handleDispatch() {
    setStatus("Dispatching DAG…");
    const response = await fetch(
      `${process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"}/api/v1/chat/`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message: goal }),
      },
    );
    const data = await response.json();
    setStatus(data.reply ?? "Goal accepted");
    await sendGoal(goal);
  }

  return (
    <main className="min-h-screen hud-grid p-4">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-800 bg-hud-panel/70 px-5 py-4 backdrop-blur">
        <div>
          <h1 className="font-mono text-xl tracking-[0.25em] text-hud-accent">COMMAND CENTER</h1>
          <p className="text-xs text-slate-500">Session {sessionId}</p>
        </div>
        <div className="flex min-w-[320px] flex-1 items-center gap-2">
          <input
            value={goal}
            onChange={(event) => setGoal(event.target.value)}
            className="flex-1 rounded-lg border border-slate-700 bg-black/40 px-3 py-2 font-mono text-sm outline-none ring-cyan-500/40 focus:ring"
            placeholder="Issue high-level intent…"
          />
          <button
            type="button"
            onClick={handleDispatch}
            className="rounded-lg bg-cyan-500/20 px-4 py-2 font-mono text-sm text-hud-accent hover:bg-cyan-500/30"
          >
            Dispatch
          </button>
        </div>
        {status && <p className="w-full font-mono text-xs text-slate-400">{status}</p>}
      </header>

      <div className="grid h-[calc(100vh-9rem)] grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-3">
          <NeuralStream />
        </div>
        <div className="col-span-12 lg:col-span-5">
          <ViewportEngine />
        </div>
        <div className="col-span-12 lg:col-span-4">
          <MonacoWorkbench />
        </div>
      </div>
    </main>
  );
}
