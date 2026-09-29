import { useEffect, useMemo, useRef, useState } from "react";
import type { Wave } from "../types";

export function Waveform({ wave }: { wave: Wave | null }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [query, setQuery] = useState("");
  const [zoom, setZoom] = useState(1);
  const [cursor, setCursor] = useState<number | null>(null);
  const signals = useMemo(
    () => (wave?.signals ?? []).filter((sig) => sig.name.toLowerCase().includes(query.toLowerCase())),
    [wave, query],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !wave?.available) return;
    const width = canvas.parentElement?.clientWidth ?? 600;
    const height = Math.max(signals.length, 1) * 26;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#101214";
    ctx.fillRect(0, 0, width, height);
    const end = Math.max(wave.end || 1, 1);
    const span = end / zoom;
    signals.forEach((sig, index) => {
      const y = index * 26 + 13;
      ctx.strokeStyle = "#3dbea5";
      ctx.beginPath();
      let started = false;
      const changes = sig.changes.length ? sig.changes : [[0, "x"] as [number, string]];
      changes.forEach(([time, value], changeIndex) => {
        const next = changes[changeIndex + 1]?.[0] ?? end;
        const x1 = ((time - 0) / span) * width;
        const x2 = (next / span) * width;
        const high = value === "1" || value === "1".repeat(sig.width);
        const level = high ? y - 6 : y + 6;
        if (!started) {
          ctx.moveTo(Math.max(0, x1), level);
          started = true;
        } else ctx.lineTo(Math.max(0, x1), level);
        ctx.lineTo(Math.max(0, x2), level);
        if (sig.width > 1 && x2 - x1 > 28) {
          ctx.fillStyle = "#d7ba7d";
          ctx.font = "10px IBM Plex Mono";
          ctx.fillText(value, x1 + 4, y + 4);
        }
      });
      ctx.stroke();
    });
    if (cursor != null) {
      ctx.strokeStyle = "#e0a15a";
      ctx.beginPath();
      ctx.moveTo(cursor, 0);
      ctx.lineTo(cursor, height);
      ctx.stroke();
    }
  }, [wave, signals, zoom, cursor]);

  if (!wave) return <p className="lede">No waveform captured. Run simulation to generate a VCD.</p>;
  if (!wave.available) return <p className="lede">{wave.reason}</p>;
  const time = cursor == null || !wave.end ? null : Math.round(((cursor / (canvasRef.current?.clientWidth || 1)) * (wave.end / zoom)));
  return (
    <div>
      <div className="row" style={{ marginBottom: 8 }}>
        <input type="text" placeholder="Signal search" value={query} onChange={(event) => setQuery(event.target.value)} />
        <label className="field">Zoom
          <input type="number" min={1} max={20} value={zoom} onChange={(event) => setZoom(Number(event.target.value) || 1)} />
        </label>
        <span>{wave.timescale} {wave.truncated ? "· truncated" : ""} {time != null ? `· cursor ${time}` : ""}</span>
      </div>
      <div className="wave-wrap">
        <div className="wave-names">
          {signals.map((sig) => <div key={sig.id}>{sig.name}</div>)}
        </div>
        <div onClick={(event) => {
          const rect = (event.currentTarget as HTMLDivElement).getBoundingClientRect();
          setCursor(event.clientX - rect.left);
        }}>
          <canvas ref={canvasRef} className="wave" />
        </div>
      </div>
    </div>
  );
}
