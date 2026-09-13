"use client";

import { motion } from "framer-motion";
import { useTelemetry, type TelemetryEvent } from "@/lib/websocket";

const NODE_ORDER = ["orchestrator", "architect", "execution", "red_team", "self_heal"];

function statusColor(type: string) {
  if (type.includes("completed")) return "text-hud-ok";
  if (type.includes("running")) return "text-hud-accent";
  if (type.includes("failed")) return "text-hud-danger";
  return "text-slate-400";
}

function NodeBadge({ id, events }: { id: string; events: TelemetryEvent[] }) {
  const latest = events.find((event) => event.payload?.node_id === id);
  const label = latest?.type?.replace("node_", "") ?? "idle";

  return (
    <motion.div
      layout
      className="rounded-lg border border-slate-700/80 bg-hud-panel/80 p-3"
      animate={{ scale: label === "running" ? 1.02 : 1 }}
      transition={{ type: "spring", stiffness: 260, damping: 20 }}
    >
      <div className="text-xs uppercase tracking-widest text-slate-500">{id}</div>
      <div className={`mt-1 font-mono text-sm ${statusColor(label)}`}>{label}</div>
    </motion.div>
  );
}

export function NeuralStream() {
  const { connected, events } = useTelemetry();

  return (
    <section className="flex h-full flex-col rounded-xl border border-slate-800 bg-hud-panel/60 p-4 backdrop-blur">
      <header className="mb-4 flex items-center justify-between">
        <h2 className="font-mono text-sm uppercase tracking-[0.2em] text-hud-accent">
          Neural Stream
        </h2>
        <span className={`text-xs ${connected ? "text-hud-ok" : "text-hud-warn"}`}>
          {connected ? "LIVE" : "RECONNECTING"}
        </span>
      </header>

      <div className="grid grid-cols-1 gap-2">
        {NODE_ORDER.map((node) => (
          <NodeBadge key={node} id={node} events={events} />
        ))}
      </div>

      <div className="mt-4 flex-1 overflow-auto rounded-lg border border-slate-800 bg-black/30 p-3 font-mono text-xs">
        {events.length === 0 ? (
          <p className="text-slate-500">Awaiting swarm telemetry…</p>
        ) : (
          events.slice(0, 12).map((event, index) => (
            <div key={`${event.type}-${index}`} className="mb-2 border-b border-slate-800 pb-2">
              <span className="text-hud-accent">{event.type}</span>
              <pre className="mt-1 whitespace-pre-wrap text-slate-400">
                {JSON.stringify(event.payload, null, 2)}
              </pre>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
