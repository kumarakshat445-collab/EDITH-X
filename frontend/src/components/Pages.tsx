import { useState } from "react";
import { useWorkspace } from "../workspace";
import type { ModelRow, Settings } from "../types";
import { api } from "../api";
import { useEffect } from "react";

function metric(value: number | null | undefined, suffix = "") {
  if (value == null) return "—";
  return `${value}${suffix}`;
}

export function Dashboard() {
  const ws = useWorkspace();
  const [name, setName] = useState("New RTL");
  const [template, setTemplate] = useState("empty");
  const project = ws.project ?? ws.projects[0];
  return (
    <div className="page">
      <h1>HEXA-R</h1>
      <p className="lede">Private, offline AI copilot for writing, debugging, simulating, and verifying RTL on this machine. Qualcomm Hexagon acceleration is reported only when that backend is actually active.</p>
      <div className="banner">
        <span className="dot ok" />
        <div>
          <b>OFFLINE MODE</b>
          <div>No source code leaves this device. Cloud AI is {ws.settings?.allow_cloud ? "allowed in settings, with no provider configured" : "off"}.</div>
        </div>
      </div>
      <div className="split">
        <div>
          <div className="panel-h" style={{ paddingLeft: 0 }}>Projects</div>
          {ws.projects.map((item) => (
            <button key={item.id} className={`list-btn ${project?.id === item.id ? "active" : ""}`} onClick={() => void ws.openProject(item.id)}>
              <b>{item.name}</b>
              <div style={{ color: "var(--dim)" }}>{item.description}</div>
            </button>
          ))}
          <form className="stack" onSubmit={(event) => { event.preventDefault(); void ws.createProject(name, template); }}>
            <label className="field">New project
              <input type="text" value={name} onChange={(event) => setName(event.target.value)} />
            </label>
            <label className="field">Template
              <select value={template} onChange={(event) => setTemplate(event.target.value)}>
                <option value="empty">Empty</option>
                <option value="uart">UART Controller demo</option>
                <option value="counter">Counter defect</option>
              </select>
            </label>
            <button className="btn" type="submit">Create Project</button>
          </form>
        </div>
        <div>
          {project ? (
            <>
              <div className="grid">
                <Stat k="Project" v={project.name} />
                <Stat k="RTL Files" v={String(project.rtl_files)} />
                <Stat k="Testbenches" v={String(project.testbenches)} />
                <Stat k="Tests" v={metric(project.tests)} />
                <Stat k="Passing" v={metric(project.passing)} />
                <Stat k="Failing" v={metric(project.failing)} />
                <Stat k="Synthesizability" v={project.synthesizability == null ? "—" : `${project.synthesizability}%`} />
                <Stat k="Simulation" v={project.simulation ?? "not run"} />
              </div>
              <div className="grid" style={{ marginTop: 10 }}>
                <Stat k="AI Model" v={ws.engine?.model ?? "—"} />
                <Stat k="Execution" v={ws.engine?.npu_active ? "Snapdragon Hexagon NPU" : "On-device CPU rule engine"} />
                <Stat k="Privacy" v="100% on device" />
                <Stat k="Network" v={ws.engine?.network ?? "Offline"} />
              </div>
              <div className="row" style={{ marginTop: 14 }}>
                <button className="btn-primary" onClick={() => void ws.openProject(project.id)}>Open</button>
                <button className="btn-primary" onClick={() => { void ws.openProject(project.id).then(() => ws.verify()); }}>Verify RTL</button>
              </div>
            </>
          ) : <p>No project yet.</p>}
        </div>
      </div>
    </div>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return <div className="card"><div className="k">{k}</div><div className="v" style={{ fontSize: v.length > 18 ? 14 : 22 }}>{v}</div></div>;
}

export function Privacy() {
  const ws = useWorkspace();
  const settings = ws.settings;
  if (!settings) return null;
  return (
    <div className="page">
      <h1>Privacy</h1>
      <p className="lede">Your RTL and hardware IP remain on this machine unless you explicitly enable an external service. No external service is configured in this build.</p>
      <div className="check"><span>Source code</span><b className="ok-text">Local</b></div>
      <div className="check"><span>AI inference</span><b className="ok-text">Local · {ws.engine?.label}</b></div>
      <div className="check"><span>Simulation</span><b className="ok-text">Local</b></div>
      <div className="check"><span>Telemetry</span><b className="ok-text">{settings.telemetry ? "Flag on, nothing is transmitted" : "Disabled"}</b></div>
      <div className="check"><span>Crash reports</span><b className="ok-text">{settings.crash_reports ? "Flag on, stored only if a local log exists" : "Disabled"}</b></div>
      <div className="check"><span>Cloud upload</span><b className={settings.allow_cloud ? "warn-text" : "ok-text"}>{settings.allow_cloud ? "Allowed, no provider configured" : "Disabled"}</b></div>
      <div className="section stack">
        <Toggle label="Allow Cloud AI" checked={settings.allow_cloud} onChange={(value) => void ws.saveSettings({ ...settings, allow_cloud: value })} />
        <Toggle label="Telemetry" checked={settings.telemetry} onChange={(value) => void ws.saveSettings({ ...settings, telemetry: value })} />
        <Toggle label="Crash reports" checked={settings.crash_reports} onChange={(value) => void ws.saveSettings({ ...settings, crash_reports: value })} />
      </div>
    </div>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="row">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      {label} · {checked ? "ON" : "OFF"}
    </label>
  );
}

export function Npu() {
  const ws = useWorkspace();
  const [models, setModels] = useState<ModelRow[]>([]);
  useEffect(() => {
    void api<{ models: ModelRow[] }>("/api/models").then((data) => setModels(data.models));
  }, []);
  const engine = ws.engine;
  const tel = engine?.telemetry;
  return (
    <div className="page">
      <h1>NPU Performance</h1>
      <p className="lede">{engine?.detail}</p>
      <div className="grid">
        <div className="card"><div className="k">AI backend</div><div className="v" style={{ fontSize: 16 }}>{engine?.label ?? "—"}</div><div className="s">{engine?.model}</div></div>
        <div className="card"><div className="k">Status</div><div className="v" style={{ fontSize: 16 }}>{engine?.npu_active ? "Available" : "Not active"}</div><div className="s">{engine?.npu_library_present ? "QNN library detected" : "QNN library not detected"}</div></div>
        <div className="card"><div className="k">Execution</div><div className="v" style={{ fontSize: 16 }}>{engine?.execution}</div><div className="s">{engine?.network}</div></div>
        <div className="card"><div className="k">Precision</div><div className="v" style={{ fontSize: 16 }}>{engine?.precision}</div><div className="s">{engine?.onnx_installed ? `ONNX providers: ${engine.onnx_providers.join(", ") || "none"}` : "ONNX Runtime not installed"}</div></div>
      </div>
      <div className="grid" style={{ marginTop: 10 }}>
        <Metric k="NPU inference latency" v={tel?.inference_latency_ms == null ? "Telemetry unavailable" : `${tel.inference_latency_ms} ms`} />
        <Metric k="Tokens/sec" v={tel?.tokens_per_sec == null ? "Telemetry unavailable" : String(tel.tokens_per_sec)} />
        <Metric k="CPU utilization" v={tel?.cpu_utilization_pct == null ? "Telemetry unavailable" : `${tel.cpu_utilization_pct}%`} />
        <Metric k="NPU utilization" v={tel?.npu_utilization_pct == null ? "Telemetry unavailable" : `${tel.npu_utilization_pct}%`} />
        <Metric k="Memory" v={tel?.memory_mb == null ? "Telemetry unavailable" : `${tel.memory_mb} MB`} />
        <Metric k="Rule engine latency" v={engine?.rule_engine_latency_ms == null ? "No request yet" : `${engine.rule_engine_latency_ms} ms`} />
      </div>
      <div className="section arch">
        <div>HEXA-R</div>
        <div>│</div>
        <div className="on">Task router · active</div>
        <div>│</div>
        <div className="on">HEXA-R RTL Analyst · active</div>
        <div>│</div>
        <div>ONNX / AI Hub model · {engine?.model_loaded ? "loaded" : "not loaded"}</div>
        <div>│</div>
        <div>Qualcomm QNN backend · {engine?.npu_active ? "active" : "not active"}</div>
        <div>│</div>
        <div>Hexagon NPU · {engine?.npu_active ? "active" : "not active"}</div>
        <div>│</div>
        <div>Snapdragon SoC · host CPU is running the rule engine</div>
      </div>
      <h2 className="section">Model manager</h2>
      <table className="table">
        <thead><tr><th>Model</th><th>Quantization</th><th>Format</th><th>Device</th><th>Size</th><th>Status</th></tr></thead>
        <tbody>
          {models.map((model) => (
            <tr key={model.id}>
              <td>{model.name}</td>
              <td>{model.quantization}</td>
              <td>{model.format}</td>
              <td>{model.device}</td>
              <td>{model.size_bytes == null ? "—" : `${model.size_bytes} B`}</td>
              <td>{model.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Metric({ k, v }: { k: string; v: string }) {
  return <div className="card"><div className="k">{k}</div><div className="s" style={{ marginTop: 8 }}>{v}</div></div>;
}

export function SettingsPage() {
  const ws = useWorkspace();
  const [draft, setDraft] = useState<Settings | null>(ws.settings);
  useEffect(() => setDraft(ws.settings), [ws.settings]);
  if (!draft) return null;
  function set<K extends keyof Settings>(key: K, value: Settings[K]) {
    setDraft({ ...draft!, [key]: value });
  }
  return (
    <div className="page">
      <h1>Settings</h1>
      <div className="split">
        <div className="stack">
          <h2>General</h2>
          <label className="field">Theme
            <select value={draft.theme} onChange={(event) => set("theme", event.target.value)}>
              <option value="graphite">Graphite</option>
              <option value="contrast">High contrast</option>
            </select>
          </label>
          <label className="field">Font size
            <input type="number" min={11} max={20} value={draft.font_size} onChange={(event) => set("font_size", Number(event.target.value))} />
          </label>
          <label className="field">Tab size
            <input type="number" min={2} max={8} value={draft.tab_size} onChange={(event) => set("tab_size", Number(event.target.value))} />
          </label>
          <label className="row"><input type="checkbox" checked={draft.minimap} onChange={(event) => set("minimap", event.target.checked)} /> Minimap</label>
          <label className="row"><input type="checkbox" checked={draft.word_wrap} onChange={(event) => set("word_wrap", event.target.checked)} /> Word wrap</label>
          <label className="row"><input type="checkbox" checked={draft.autosave} onChange={(event) => set("autosave", event.target.checked)} /> Auto-save</label>
        </div>
        <div className="stack">
          <h2>AI</h2>
          <label className="field">Engineering mode
            <select value={draft.engineering_mode} onChange={(event) => set("engineering_mode", event.target.value)}>
              <option value="beginner">Beginner</option>
              <option value="student">Student</option>
              <option value="professional">Professional</option>
            </select>
          </label>
          <label className="field">Backend preference
            <select value={draft.backend_preference} onChange={(event) => set("backend_preference", event.target.value)}>
              <option value="auto">Auto</option>
              <option value="rules">Rule engine</option>
              <option value="onnx">ONNX</option>
              <option value="qnn">Qualcomm QNN</option>
            </select>
          </label>
          <label className="field">Temperature (stored for a future LLM; the rule engine ignores it)
            <input type="number" step="0.1" min={0} max={2} value={draft.temperature} onChange={(event) => set("temperature", Number(event.target.value))} />
          </label>
          <label className="field">Context size
            <input type="number" min={1024} max={32768} value={draft.context_size} onChange={(event) => set("context_size", Number(event.target.value))} />
          </label>
          <h2>Simulation paths</h2>
          <label className="field">Icarus Verilog
            <input type="text" placeholder={ws.tools?.icarus.path ?? "not detected"} value={draft.icarus_path} onChange={(event) => set("icarus_path", event.target.value)} />
          </label>
          <label className="field">Verilator
            <input type="text" placeholder={ws.tools?.verilator.path ?? "not detected"} value={draft.verilator_path} onChange={(event) => set("verilator_path", event.target.value)} />
          </label>
          <label className="field">Yosys
            <input type="text" placeholder={ws.tools?.yosys.path ?? "not detected"} value={draft.yosys_path} onChange={(event) => set("yosys_path", event.target.value)} />
          </label>
          {!ws.tools?.icarus.detected && <p>{ws.tools?.icarus.hint}</p>}
          <button className="btn-primary" onClick={() => void ws.saveSettings(draft)}>Save settings</button>
        </div>
      </div>
    </div>
  );
}

export function GenerateModal() {
  const ws = useWorkspace();
  const [prompt, setPrompt] = useState("Create a parameterized 32-bit synchronous FIFO with full and empty flags.");
  if (!ws.generated && !ws.palette) return null;
  if (!ws.generated) return null;
  const generated = ws.generated;
  return (
    <div className="modal-back" onClick={() => ws.setGenerated(null)}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <h2>{generated.title}</h2>
        <p>{generated.message}</p>
        {generated.ok && (
          <>
            <p><b>Assumptions</b></p>
            <ul>{generated.assumptions.map((item) => <li key={item}>{item}</li>)}</ul>
            <pre className="log" style={{ maxHeight: 220 }}>{generated.files.map((file) => `// ${file.path}\n${file.content}`).join("\n")}</pre>
          </>
        )}
        <div className="row" style={{ marginTop: 8 }}>
          <button className="btn-primary" disabled={!generated.ok} onClick={() => void ws.insertGenerated()}>Insert into project</button>
          <button className="btn" disabled={!generated.ok} onClick={() => void ws.insertGenerated().then(() => ws.analyze())}>Run static analysis</button>
          <button className="btn" disabled={!generated.ok} onClick={() => void ws.insertGenerated().then(() => ws.writeTestbench())}>Generate testbench</button>
          <button className="btn" disabled={!generated.ok} onClick={() => void ws.insertGenerated().then(() => ws.verify())}>Verify</button>
          <button className="btn-quiet" onClick={() => ws.setGenerated(null)}>Close</button>
        </div>
        <form className="stack" style={{ marginTop: 10 }} onSubmit={(event) => { event.preventDefault(); void ws.generateRtl(prompt); }}>
          <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} style={{ height: 64, background: "var(--bg-inset)", border: "1px solid var(--line)", padding: 8 }} />
          <button className="btn" type="submit">Generate RTL</button>
        </form>
      </div>
    </div>
  );
}
