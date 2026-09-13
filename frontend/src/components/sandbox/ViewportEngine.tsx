"use client";

import { useEffect, useState } from "react";

type ViewportMetrics = {
  fps: number;
  memoryMb: number;
  errors: number;
};

export function ViewportEngine() {
  const [metrics, setMetrics] = useState<ViewportMetrics>({ fps: 60, memoryMb: 128, errors: 0 });

  useEffect(() => {
    const timer = setInterval(() => {
      setMetrics((prev) => ({
        fps: 55 + Math.floor(Math.random() * 10),
        memoryMb: prev.memoryMb + (Math.random() > 0.7 ? 1 : 0),
        errors: prev.errors,
      }));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <section className="relative flex h-full flex-col overflow-hidden rounded-xl border border-slate-800 bg-black/50">
      <div className="absolute inset-x-0 top-0 z-10 flex gap-4 bg-black/60 px-4 py-2 font-mono text-xs text-slate-300">
        <span>FPS {metrics.fps}</span>
        <span>MEM {metrics.memoryMb}MB</span>
        <span className={metrics.errors ? "text-hud-danger" : "text-hud-ok"}>
          ERR {metrics.errors}
        </span>
      </div>

      <iframe
        title="Nexus Poly-Engine Viewport"
        className="h-full w-full border-0 bg-gradient-to-br from-slate-950 via-slate-900 to-cyan-950"
        sandbox="allow-scripts"
        srcDoc={`<!doctype html><html><body style='margin:0;background:#020617;color:#e2e8f0;font-family:monospace;display:grid;place-items:center;height:100vh'><div><h1 style='color:#38bdf8'>Nexus Poly-Engine</h1><p>Ephemeral sandbox viewport ready.</p></div></body></html>`}
      />
    </section>
  );
}
