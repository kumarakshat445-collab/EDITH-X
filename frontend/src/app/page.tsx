import Link from "next/link";

export default function HomePage() {
  return (
    <main className="flex min-h-screen items-center justify-center hud-grid">
      <div className="rounded-2xl border border-slate-800 bg-hud-panel/80 p-10 text-center backdrop-blur">
        <h1 className="font-mono text-3xl text-hud-accent">EDITH-X V2</h1>
        <p className="mt-3 text-slate-400">Autonomous operating core + Nexus Poly-Engine</p>
        <Link
          href="/command-center"
          className="mt-6 inline-block rounded-lg bg-cyan-500/20 px-5 py-2 font-mono text-sm text-hud-accent hover:bg-cyan-500/30"
        >
          Enter Command Center
        </Link>
      </div>
    </main>
  );
}
