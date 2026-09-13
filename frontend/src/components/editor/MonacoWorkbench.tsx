"use client";

import dynamic from "next/dynamic";
import { useState } from "react";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

const FILES: Record<string, string> = {
  "backend/app/main.py": `from app.main import create_app\n\napp = create_app()\n`,
  "backend/app/engine/swarm/graph.py": `class SwarmOrchestrator:\n    async def run_goal(self, goal: str, session_id: str):\n        ...\n`,
  "frontend/src/app/command-center/page.tsx": `export default function CommandCenterPage() {\n  return <main>EDITH-X HUD</main>;\n}\n`,
};

export function MonacoWorkbench() {
  const [activeFile, setActiveFile] = useState("backend/app/main.py");
  const [contents, setContents] = useState(FILES);

  return (
    <section className="flex h-full flex-col overflow-hidden rounded-xl border border-slate-800 bg-hud-panel/70">
      <header className="border-b border-slate-800 px-4 py-2 font-mono text-xs uppercase tracking-widest text-slate-400">
        Monaco Workbench
      </header>
      <div className="flex min-h-0 flex-1">
        <aside className="w-48 overflow-auto border-r border-slate-800 p-2 text-xs">
          {Object.keys(contents).map((path) => (
            <button
              key={path}
              type="button"
              onClick={() => setActiveFile(path)}
              className={`mb-1 block w-full rounded px-2 py-1 text-left ${
                activeFile === path ? "bg-cyan-500/20 text-hud-accent" : "text-slate-400 hover:bg-slate-800"
              }`}
            >
              {path}
            </button>
          ))}
        </aside>
        <div className="min-h-0 flex-1">
          <MonacoEditor
            height="100%"
            theme="vs-dark"
            language="python"
            value={contents[activeFile]}
            onChange={(value) =>
              setContents((prev) => ({ ...prev, [activeFile]: value ?? "" }))
            }
            options={{
              minimap: { enabled: false },
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 13,
              wordWrap: "on",
            }}
          />
        </div>
      </div>
    </section>
  );
}
