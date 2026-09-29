import { useState, type ReactNode } from "react";
import { Cpu, FolderTree, LayoutDashboard, Settings as SettingsIcon, Shield } from "lucide-react";
import { WorkspaceProvider, useWorkspace } from "./workspace";
import { Ide } from "./components/Ide";
import { Dashboard, GenerateModal, Npu, Privacy, SettingsPage } from "./components/Pages";
import type { View } from "./types";

export function App() {
  return (
    <WorkspaceProvider>
      <Shell />
    </WorkspaceProvider>
  );
}

function Shell() {
  const ws = useWorkspace();
  const [menu, setMenu] = useState<string | null>(null);
  const engine = ws.engine;
  const npu = engine?.npu_active;
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            <polygon points="8,1 14,4.5 14,11.5 8,15 2,11.5 2,4.5" fill="none" stroke="#3dbea5" strokeWidth="1.2" />
          </svg>
          HEXA-R <small>RTL</small>
        </div>
        <nav className="menus">
          <Menu id="project" open={menu} setOpen={setMenu} label="Project" items={[
            ["Open UART demo", () => void ws.runDemo("open")],
            ["New file in editor", () => ws.setView("ide")],
          ]} />
          <Menu id="run" open={menu} setOpen={setMenu} label="Run" items={[
            ["Compile", () => void ws.compile()],
            ["Simulate", () => void ws.simulate()],
            ["Synthesize with Yosys", () => void ws.synth()],
          ]} />
          <Menu id="verify" open={menu} setOpen={setMenu} label="Verify" items={[
            ["Verify RTL", () => void ws.verify()],
            ["Static analysis", () => void ws.analyze()],
            ["Generate testbench", () => void ws.writeTestbench()],
          ]} />
          <Menu id="ai" open={menu} setOpen={setMenu} label="AI" items={[
            ["Generate RTL", () => void ws.generateRtl("Create a parameterized 32-bit synchronous FIFO with full and empty flags.")],
            ["Explain active file", () => void ws.ask("Explain this module.")],
            ["Debug last failure", () => void ws.debug()],
          ]} />
          <button className="ghost" onClick={() => ws.setView("settings")}>Settings</button>
        </nav>
        <div className="spacer" />
        <button className="btn-primary" onClick={() => void ws.verify()} disabled={!ws.project}>Verify RTL</button>
        <div className={`pill ${npu ? "npu-live" : ""}`} title={engine?.detail}>
          <span className={`dot ${npu ? "ok" : "warn"}`} />
          <span>AI ENGINE <strong>{engine?.label ?? "…"}</strong></span>
        </div>
        <div className="pill"><span className="dot ok" /> OFFLINE</div>
      </header>
      <div className="shell">
        <nav className="activity">
          <Activity icon={<LayoutDashboard size={18} />} id="dashboard" label="Dashboard" view={ws.view} setView={ws.setView} />
          <Activity icon={<FolderTree size={18} />} id="ide" label="Editor" view={ws.view} setView={ws.setView} />
          <Activity icon={<Shield size={18} />} id="privacy" label="Privacy" view={ws.view} setView={ws.setView} />
          <Activity icon={<Cpu size={18} />} id="npu" label="NPU" view={ws.view} setView={ws.setView} />
          <Activity icon={<SettingsIcon size={18} />} id="settings" label="Settings" view={ws.view} setView={ws.setView} />
        </nav>
        <main>
          {ws.view === "dashboard" && <Dashboard />}
          {ws.view === "ide" && <Ide />}
          {ws.view === "privacy" && <Privacy />}
          {ws.view === "npu" && <Npu />}
          {ws.view === "settings" && <SettingsPage />}
        </main>
      </div>
      <footer className="statusbar">
        <span>{ws.project ? ws.project.name : "No project"}</span>
        <span>{ws.active ?? ""}</span>
        <span>{ws.busy}</span>
        <span className="spacer" />
        <span>{ws.tools?.icarus.detected ? `iverilog ${ws.tools.icarus.version}` : "Simulation engine not detected"}</span>
        <span>{engine?.network}</span>
        <span>{ws.settings?.engineering_mode}</span>
      </footer>
      {ws.error && <div className="toast" role="alert">{ws.error} <button className="text-btn" onClick={() => ws.setError("")}>Dismiss</button></div>}
      <GenerateModal />
      {ws.palette && <Palette />}
    </div>
  );
}

function Activity({ icon, id, label, view, setView }: { icon: ReactNode; id: View; label: string; view: View; setView: (view: View) => void }) {
  return <button className={view === id ? "active" : ""} title={label} onClick={() => setView(id)}>{icon}</button>;
}

function Menu({ id, label, open, setOpen, items }: { id: string; label: string; open: string | null; setOpen: (value: string | null) => void; items: [string, () => void][] }) {
  return (
    <div className="menu">
      <button onClick={() => setOpen(open === id ? null : id)}>{label}</button>
      {open === id && (
        <div className="dropdown">
          {items.map(([name, action]) => (
            <button key={name} onClick={() => { setOpen(null); action(); }}>{name}</button>
          ))}
        </div>
      )}
    </div>
  );
}

function Palette() {
  const ws = useWorkspace();
  const [query, setQuery] = useState("");
  const commands: [string, () => void][] = [
    ["Verify RTL", () => void ws.verify()],
    ["Run simulation", () => void ws.simulate()],
    ["Static analysis", () => void ws.analyze()],
    ["Generate testbench", () => void ws.writeTestbench()],
    ["Generate RTL", () => void ws.generateRtl("Create a parameterized 32-bit synchronous FIFO with full and empty flags.")],
    ["Open privacy", () => ws.setView("privacy")],
    ["Open NPU", () => ws.setView("npu")],
    ["Open settings", () => ws.setView("settings")],
    ["Debug last failure", () => void ws.debug()],
  ];
  const shown = commands.filter(([name]) => name.toLowerCase().includes(query.toLowerCase()));
  return (
    <div className="modal-back" onClick={() => ws.setPalette(false)}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <input autoFocus type="text" placeholder="Command" value={query} onChange={(event) => setQuery(event.target.value)} />
        <div className="stack" style={{ marginTop: 8 }}>
          {shown.map(([name, action]) => (
            <button key={name} className="list-btn" onClick={() => { ws.setPalette(false); action(); }}>{name}</button>
          ))}
        </div>
      </div>
    </div>
  );
}
