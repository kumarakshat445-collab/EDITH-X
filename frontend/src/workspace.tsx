import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, streamCopilot } from "./api";
import type {
  ChatMessage,
  Diagnostic,
  Engine,
  Generated,
  Project,
  Proposal,
  Report,
  Settings,
  Step,
  Tools,
  TreeNode,
  View,
  Wave,
} from "./types";

type OpenFile = { path: string; content: string; saved: string };

type WorkspaceValue = {
  view: View;
  setView: (view: View) => void;
  engine: Engine | null;
  tools: Tools | null;
  settings: Settings | null;
  saveSettings: (next: Settings) => Promise<void>;
  projects: Project[];
  project: Project | null;
  openProject: (id: string) => Promise<void>;
  createProject: (name: string, template: string) => Promise<void>;
  tree: TreeNode[];
  files: OpenFile[];
  active: string | null;
  openPath: (path: string) => Promise<void>;
  setActive: (path: string) => void;
  edit: (content: string) => void;
  selection: string;
  setSelection: (value: string) => void;
  save: () => Promise<void>;
  diagnostics: Diagnostic[];
  analyze: () => Promise<void>;
  steps: Step[];
  busy: string;
  verify: () => Promise<void>;
  compile: () => Promise<void>;
  simulate: () => Promise<void>;
  synth: () => Promise<void>;
  writeTestbench: () => Promise<void>;
  proposal: Proposal | null;
  setProposal: (value: Proposal | null) => void;
  applyProposal: () => Promise<void>;
  explainProposal: () => Promise<void>;
  debug: () => Promise<void>;
  output: string;
  simLog: string;
  report: Report | null;
  reportMarkdown: string;
  wave: Wave | null;
  loadWave: () => Promise<void>;
  runCommand: (command: string) => Promise<void>;
  messages: ChatMessage[];
  thinking: boolean;
  ask: (message: string, selection?: string) => Promise<void>;
  insertCode: (path: string, content: string) => Promise<void>;
  generated: Generated | null;
  setGenerated: (value: Generated | null) => void;
  generateRtl: (prompt: string) => Promise<void>;
  insertGenerated: () => Promise<void>;
  restoreDemo: () => Promise<void>;
  refreshProjects: () => Promise<void>;
  error: string;
  setError: (value: string) => void;
  bottom: string;
  setBottom: (value: string) => void;
  demoNote: string;
  runDemo: (step: string) => Promise<void>;
  palette: boolean;
  setPalette: (value: boolean) => void;
};

const Ctx = createContext<WorkspaceValue | null>(null);
export function useWorkspace() {
  const value = useContext(Ctx);
  if (!value) throw new Error("Workspace missing");
  return value;
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [view, setView] = useState<View>("dashboard");
  const [engine, setEngine] = useState<Engine | null>(null);
  const [tools, setTools] = useState<Tools | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const projectIdRef = useRef<string | null>(null);
  const [tree, setTree] = useState<TreeNode[]>([]);
  const [files, setFiles] = useState<OpenFile[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [selection, setSelection] = useState("");
  const [diagnostics, setDiagnostics] = useState<Diagnostic[]>([]);
  const [steps, setSteps] = useState<Step[]>([]);
  const [busy, setBusy] = useState("");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [output, setOutput] = useState("");
  const [simLog, setSimLog] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [reportMarkdown, setReportMarkdown] = useState("");
  const [wave, setWave] = useState<Wave | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [thinking, setThinking] = useState(false);
  const [generated, setGenerated] = useState<Generated | null>(null);
  const [error, setError] = useState("");
  const [bottom, setBottom] = useState("problems");
  const [demoNote, setDemoNote] = useState("");
  const [palette, setPalette] = useState(false);

  const project = projects.find((item) => item.id === projectId) ?? null;
  const current = files.find((file) => file.path === active) ?? null;
  const filesRef = useRef(files);
  const activeRef = useRef(active);
  filesRef.current = files;
  activeRef.current = active;

  async function boot() {
    try {
      const [eng, tool, pref, list] = await Promise.all([
        api<Engine>("/api/engine"),
        api<Tools>("/api/tools"),
        api<Settings>("/api/settings"),
        api<{ projects: Project[] }>("/api/projects"),
      ]);
      setEngine(eng);
      setTools(tool);
      setSettings(pref);
      setProjects(list.projects);
      document.documentElement.dataset.theme = pref.theme;
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "API unreachable");
    }
  }

  useEffect(() => {
    void boot();
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void save();
      }
      if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === "p") {
        event.preventDefault();
        setPalette(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  useEffect(() => {
    if (!settings?.autosave || !current || current.content === current.saved) return;
    const handle = window.setTimeout(() => void save(), 700);
    return () => window.clearTimeout(handle);
  }, [current?.content, current?.path, settings?.autosave]);

  async function refreshProjects() {
    const list = await api<{ projects: Project[] }>("/api/projects");
    setProjects(list.projects);
    const eng = await api<Engine>("/api/engine");
    setEngine(eng);
  }

  async function openProject(id: string) {
    projectIdRef.current = id;
    setProjectId(id);
    const data = await api<{ tree: TreeNode[] }>(`/api/projects/${id}`);
    setTree(data.tree);
    setView("ide");
    const first = findFile(data.tree, (path) => path.startsWith("rtl/") && path.endsWith(".sv"));
    if (first) await openPath(first, id);
  }

  async function createProject(name: string, template: string) {
    const created = await api<Project>("/api/projects", { method: "POST", body: JSON.stringify({ name, template }) });
    await refreshProjects();
    await openProject(created.id);
  }

  async function openPath(path: string, id = projectIdRef.current) {
    if (!id) return;
    const file = await api<{ path: string; content: string }>(`/api/projects/${id}/file?path=${encodeURIComponent(path)}`);
    setFiles((prev) => {
      const others = prev.filter((item) => item.path !== path);
      return [...others, { path, content: file.content, saved: file.content }];
    });
    setActive(path);
  }

  function edit(content: string) {
    if (!active) return;
    setFiles((prev) => prev.map((file) => (file.path === active ? { ...file, content } : file)));
  }

  async function save() {
    const open = filesRef.current.find((file) => file.path === activeRef.current);
    if (!projectIdRef.current || !open || open.content === open.saved) return;
    await api(`/api/projects/${projectIdRef.current}/file`, {
      method: "PUT",
      body: JSON.stringify({ path: open.path, content: open.content }),
    });
    setFiles((prev) => prev.map((file) => (file.path === open.path ? { ...file, saved: open.content } : file)));
  }

  async function analyze() {
    if (!projectIdRef.current) return;
    setBusy("Analyzing");
    try {
      await save();
      const result = await api<{ diagnostics: Diagnostic[] }>(`/api/projects/${projectIdRef.current}/analyze`, {
        method: "POST",
        body: JSON.stringify({ path: null }),
      });
      setDiagnostics(result.diagnostics);
      setBottom("problems");
      await refreshProjects();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Analysis failed");
    } finally {
      setBusy("");
    }
  }

  async function writeTestbench() {
    if (!projectIdRef.current) return;
    setBusy("Generating testbench");
    try {
      await save();
      const result = await api<{ written?: boolean; path?: string; message?: string; ok?: boolean }>(
        `/api/projects/${projectIdRef.current}/testbench/write`,
        { method: "POST", body: JSON.stringify({ path: active }) },
      );
      if (result.path) {
        const data = await api<{ tree: TreeNode[] }>(`/api/projects/${projectIdRef.current}`);
        setTree(data.tree);
        await openPath(result.path);
      }
      setOutput(result.message || `Wrote ${result.path}`);
      setBottom("output");
      await refreshProjects();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Testbench generation failed");
    } finally {
      setBusy("");
    }
  }

  function absorbVerify(result: { steps: Step[]; report: Report; proposal: Proposal }) {
    setSteps(result.steps);
    setReport(result.report);
    setProposal(result.proposal);
    const sim = result.steps.find((step) => step.id === "simulate");
    const compile = result.steps.find((step) => step.id === "compile");
    setSimLog(sim?.log || "");
    setOutput(compile?.log || "");
    const diags = result.steps.find((step) => step.id === "static")?.diagnostics ?? [];
    setDiagnostics(diags);
    setBottom(result.proposal?.can_apply ? "diff" : sim?.status === "fail" ? "simulation" : "report");
  }

  async function verify() {
    if (!projectIdRef.current) return;
    setBusy("Verifying");
    setSteps([
      { id: "parse", label: "Parse", status: "run" },
      { id: "static", label: "Static Analysis", status: "run" },
      { id: "compile", label: "Compile", status: "run" },
      { id: "testbench", label: "Testbench", status: "run" },
      { id: "simulate", label: "Simulation", status: "run" },
      { id: "assertions", label: "Assertions", status: "run" },
      { id: "ai", label: "AI Analysis", status: "run" },
    ]);
    setBottom("simulation");
    try {
      await save();
      const result = await api<{ steps: Step[]; report: Report; proposal: Proposal }>(`/api/projects/${projectIdRef.current}/verify`, { method: "POST" });
      absorbVerify(result);
      const data = await api<{ tree: TreeNode[] }>(`/api/projects/${projectIdRef.current}`);
      setTree(data.tree);
      if (result.report.simulation === "PASS" || result.report.simulation === "FAIL") {
        setWave(await api<Wave>(`/api/projects/${projectIdRef.current}/waveform`));
      }
      const reportBody = await api<{ markdown: string }>(`/api/projects/${projectIdRef.current}/report`);
      setReportMarkdown(reportBody.markdown);
      await refreshProjects();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Verification failed");
    } finally {
      setBusy("");
    }
  }

  async function compile() {
    if (!projectIdRef.current) return;
    setBusy("Compiling");
    try {
      await save();
      const result = await api<{ log: string; ok: boolean }>(`/api/projects/${projectIdRef.current}/compile`, { method: "POST" });
      setOutput(result.log);
      setBottom("output");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Compile failed");
    } finally {
      setBusy("");
    }
  }

  async function simulate() {
    if (!projectIdRef.current) return;
    setBusy("Simulating");
    try {
      await save();
      const result = await api<{ log: string; ok: boolean; waveform: boolean }>(`/api/projects/${projectIdRef.current}/simulate`, { method: "POST" });
      setSimLog(result.log);
      setBottom("simulation");
      if (result.waveform) setWave(await api<Wave>(`/api/projects/${projectIdRef.current}/waveform`));
      await refreshProjects();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Simulation failed");
    } finally {
      setBusy("");
    }
  }

  async function synth() {
    if (!projectIdRef.current) return;
    setBusy("Synthesizing");
    try {
      const result = await api<{ log: string; ok: boolean; cells: string | null }>(`/api/projects/${projectIdRef.current}/synth`, { method: "POST" });
      setOutput(result.log || (result.ok ? "Yosys finished." : "Yosys failed."));
      setBottom("output");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Synthesis failed");
    } finally {
      setBusy("");
    }
  }

  async function applyProposal() {
    if (!projectIdRef.current || !proposal?.path || !proposal.updated) return;
    setBusy("Applying");
    try {
      await api(`/api/projects/${projectIdRef.current}/apply`, {
        method: "POST",
        body: JSON.stringify({ path: proposal.path, content: proposal.updated }),
      });
      await openPath(proposal.path);
      setOutput(`Applied ${proposal.rule} to ${proposal.path}. Source backup is in .hexa/backups.`);
      setBottom("output");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Apply failed");
    } finally {
      setBusy("");
    }
  }

  async function explainProposal() {
    if (!proposal?.diff) return;
    const result = await api<{ text: string }>("/api/explain-diff", {
      method: "POST",
      body: JSON.stringify({ diff: proposal.diff, mode: settings?.engineering_mode ?? "professional" }),
    });
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "assistant", text: result.text, route: "diff" }]);
    setView("ide");
  }

  async function debug() {
    if (!projectIdRef.current) return;
    setBusy("Debugging");
    try {
      const result = await api<Proposal>(`/api/projects/${projectIdRef.current}/debug`, { method: "POST" });
      setProposal(result);
      setBottom("diff");
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          route: result.rule,
          text: `Root cause\n${result.root_cause}\n\nEvidence\n${result.evidence.map((item) => `- ${item}`).join("\n")}\n\nProposed fix\n${result.proposed_fix}\n\nWhy\n${result.why}`,
        },
      ]);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Debug failed");
    } finally {
      setBusy("");
    }
  }

  async function loadWave() {
    if (!projectIdRef.current) return;
    setWave(await api<Wave>(`/api/projects/${projectIdRef.current}/waveform`));
    setBottom("waveform");
  }

  async function runCommand(command: string) {
    if (!projectIdRef.current) return;
    try {
      const result = await api<{ stdout: string; stderr: string; exit_code: number }>(`/api/projects/${projectIdRef.current}/command`, {
        method: "POST",
        body: JSON.stringify({ command }),
      });
      setOutput(`$ ${command}\nexit ${result.exit_code}\n${result.stdout}${result.stderr}`);
      setBottom("output");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Command rejected");
    }
  }

  async function ask(message: string, selected?: string) {
    if (!projectIdRef.current) {
      setError("Open a project before asking HEXA-R.");
      return;
    }
    const id = crypto.randomUUID();
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "user", text: message }, { id, role: "assistant", text: "" }]);
    setThinking(true);
    try {
      const done = await streamCopilot(
        {
          project: projectIdRef.current,
          message,
          file: active,
          selection: selected ?? selection,
          mode: settings?.engineering_mode ?? "professional",
        },
        (text) => {
          setMessages((prev) => prev.map((item) => (item.id === id ? { ...item, text: item.text + text } : item)));
        },
      );
      setMessages((prev) =>
        prev.map((item) =>
          item.id === id
            ? {
                ...item,
                text: String(done.text ?? item.text),
                route: String(done.route ?? ""),
                code: (done.code as string | null) ?? null,
                suggested_path: (done.suggested_path as string | null) ?? null,
              }
            : item,
        ),
      );
      if (done.proposal && typeof done.proposal === "object") {
        setProposal(done.proposal as Proposal);
        setBottom("diff");
      }
      const eng = await api<Engine>("/api/engine");
      setEngine(eng);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Copilot failed");
    } finally {
      setThinking(false);
    }
  }

  async function insertCode(path: string, content: string) {
    if (!projectIdRef.current) return;
    await api(`/api/projects/${projectIdRef.current}/file`, { method: "PUT", body: JSON.stringify({ path, content }) });
    const data = await api<{ tree: TreeNode[] }>(`/api/projects/${projectIdRef.current}`);
    setTree(data.tree);
    await openPath(path);
    await refreshProjects();
  }

  async function generateRtl(prompt: string) {
    if (!projectIdRef.current) return;
    setBusy("Generating RTL");
    try {
      const result = await api<Generated>(`/api/projects/${projectIdRef.current}/generate/rtl`, {
        method: "POST",
        body: JSON.stringify({ prompt, mode: settings?.engineering_mode ?? "professional" }),
      });
      setGenerated(result);
      if (!result.ok) setError(result.message);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Generation failed");
    } finally {
      setBusy("");
    }
  }

  async function insertGenerated() {
    if (!generated?.ok) return;
    for (const file of generated.files) await insertCode(file.path, file.content);
    setGenerated(null);
  }

  async function restoreDemo() {
    if (!projectIdRef.current) return;
    await api(`/api/projects/${projectIdRef.current}/restore`, { method: "POST" });
    setFiles([]);
    setProposal(null);
    setSteps([]);
    setReport(null);
    const data = await api<{ tree: TreeNode[] }>(`/api/projects/${projectIdRef.current}`);
    setTree(data.tree);
    const rx = findFile(data.tree, (path) => path.endsWith("uart_rx.sv") || path.endsWith("counter.sv"));
    if (rx) await openPath(rx);
    await refreshProjects();
    setDemoNote("Demo sources restored.");
  }

  async function saveSettings(next: Settings) {
    const saved = await api<Settings>("/api/settings", { method: "PUT", body: JSON.stringify(next) });
    setSettings(saved);
    document.documentElement.dataset.theme = saved.theme;
    setEngine(await api<Engine>("/api/engine"));
    setTools(await api<Tools>("/api/tools"));
  }

  async function runDemo(step: string) {
    setDemoNote("");
    if (step === "open") {
      await openProject("uart");
      setDemoNote("UART Controller is open.");
      return;
    }
    if (!projectIdRef.current) {
      setError("Open the UART project first.");
      return;
    }
    if (step === "rtl") {
      await openPath("rtl/uart_rx.sv");
      setDemoNote("Receiver RTL is in the editor. The DATA state is the sampling path.");
      return;
    }
    if (step === "tb") {
      await openPath("rtl/uart_rx.sv");
      await writeTestbench();
      setDemoNote("Testbench written to tb/uart_tb.sv. It checks five loopback bytes.");
      return;
    }
    if (step === "verify1") {
      await verify();
      setDemoNote("Verification finished. A failing loopback means the sample point is still wrong.");
      return;
    }
    if (step === "cause") {
      await debug();
      setDemoNote("The rule engine quoted the late compare and the failing bytes.");
      return;
    }
    if (step === "apply") {
      if (!proposal?.can_apply) {
        setError("There is no patch to apply. Run debug after a failing simulation.");
        return;
      }
      await applyProposal();
      setDemoNote("Patch applied. The previous file is in .hexa/backups.");
      return;
    }
    if (step === "verify2") {
      await verify();
      setDemoNote("Second verification uses the edited receiver.");
      return;
    }
    if (step === "npu") {
      setView("npu");
      setEngine(await api<Engine>("/api/engine"));
      setDemoNote("NPU page shows the backend that actually ran.");
    }
  }

  const value = useMemo<WorkspaceValue>(
    () => ({
      view, setView, engine, tools, settings, saveSettings, projects, project, openProject, createProject,
      tree, files, active, openPath, setActive, edit, selection, setSelection, save, diagnostics, analyze,
      steps, busy, verify, compile, simulate, synth, writeTestbench, proposal, setProposal, applyProposal,
      explainProposal, debug, output, simLog, report, reportMarkdown, wave, loadWave, runCommand, messages,
      thinking, ask, insertCode, generated, setGenerated, generateRtl, insertGenerated, restoreDemo,
      refreshProjects, error, setError, bottom, setBottom, demoNote, runDemo, palette, setPalette,
    }),
    [
      view, engine, tools, settings, projects, project, tree, files, active, selection, diagnostics, steps,
      busy, proposal, output, simLog, report, reportMarkdown, wave, messages, thinking, generated, error,
      bottom, demoNote, palette,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

function findFile(nodes: TreeNode[], test: (path: string) => boolean): string | null {
  for (const node of nodes) {
    if (node.type === "file" && test(node.path)) return node.path;
    if (node.children) {
      const found = findFile(node.children, test);
      if (found) return found;
    }
  }
  return null;
}
