import { useState } from "react";
import { ChevronDown, ChevronRight, FileCode2 } from "lucide-react";
import { useWorkspace } from "../workspace";
import { CodeEditor } from "./Editor";
import { Waveform } from "./Waveform";
import type { TreeNode } from "../types";

export function Ide() {
  const ws = useWorkspace();
  const file = ws.files.find((item) => item.path === ws.active);
  return (
    <div className="ide">
      <aside className="explorer">
        <div className="panel-h">
          <span>Project</span>
          <button className="text-btn" onClick={() => void ws.restoreDemo()} disabled={!ws.project || (ws.project.template !== "uart" && ws.project.template !== "counter")}>Restore demo</button>
        </div>
        <div className="tree">
          {ws.tree.map((node) => <Node key={node.path} node={node} depth={0} />)}
        </div>
      </aside>
      <section className="editor-pane">
        <div className="demo">
          <strong style={{ fontSize: 11, letterSpacing: "0.08em" }}>DEMO</strong>
          {[
            ["open", "1 Open UART"],
            ["rtl", "2 Show RTL"],
            ["tb", "3 Testbench"],
            ["verify1", "4 Verify"],
            ["cause", "5 Explain"],
            ["apply", "6 Apply fix"],
            ["verify2", "7 Verify again"],
            ["npu", "8 NPU"],
          ].map(([id, label]) => (
            <button key={id} className="chip" onClick={() => void ws.runDemo(id)}>{label}</button>
          ))}
          <span style={{ color: "var(--dim)" }}>{ws.demoNote}</span>
        </div>
        <div className="tabs">
          {ws.files.map((item) => (
            <button key={item.path} className={item.path === ws.active ? "active" : ""} onClick={() => ws.setActive(item.path)}>
              {item.path.split("/").pop()}{item.content !== item.saved ? " *" : ""}
            </button>
          ))}
        </div>
        <div className="editor-host">
          {file ? (
            <CodeEditor
              path={file.path}
              value={file.content}
              settings={ws.settings}
              diagnostics={ws.diagnostics}
              onChange={ws.edit}
              onSelection={ws.setSelection}
              onAction={(action, selection) => {
                if (action === "testbench") void ws.writeTestbench();
                else if (action === "synth") void ws.ask("Check synthesizability of this RTL.", selection);
                else if (action === "bugs") void ws.ask("Find bugs in this module.", selection);
                else if (action === "assertions") void ws.ask("Generate assertions for this module.", selection);
                else if (action === "optimize") void ws.ask("Optimize this RTL for area.", selection);
                else if (action === "fix") void ws.ask("Fix this RTL.", selection);
                else void ws.ask("Explain this code.", selection);
              }}
            />
          ) : <p className="lede" style={{ padding: 16 }}>Open a file from the project tree.</p>}
        </div>
      </section>
      <Bottom />
      <Copilot />
    </div>
  );
}

function Node({ node, depth }: { node: TreeNode; depth: number }) {
  const ws = useWorkspace();
  const [open, setOpen] = useState(true);
  if (node.type === "dir") {
    return (
      <div>
        <button className="file-btn" style={{ paddingLeft: 10 + depth * 12 }} onClick={() => setOpen((value) => !value)}>
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />} {node.name}
        </button>
        {open && node.children?.map((child) => <Node key={child.path} node={child} depth={depth + 1} />)}
      </div>
    );
  }
  return (
    <button className={`file-btn ${ws.active === node.path ? "active" : ""}`} style={{ paddingLeft: 22 + depth * 12 }} onClick={() => void ws.openPath(node.path)}>
      <FileCode2 size={14} /> {node.name}
    </button>
  );
}

function Bottom() {
  const ws = useWorkspace();
  const [command, setCommand] = useState("iverilog -g2012 -s uart_tb rtl/uart_tx.sv rtl/uart_rx.sv tb/uart_tb.sv");
  const tabs = [
    ["problems", `Problems ${ws.diagnostics.length}`],
    ["output", "Output"],
    ["simulation", "Simulation"],
    ["waveform", "Waveform"],
    ["report", "Report"],
    ["diff", "Diff"],
  ];
  return (
    <section className="bottom">
      {ws.steps.length > 0 && (
        <div className="pipeline">
          {ws.steps.map((step) => (
            <div key={step.id} className={`pipe ${step.status}`}>
              <span className={`dot ${step.status === "pass" ? "ok" : step.status === "fail" ? "err" : "warn"}`} />
              {step.label}
            </div>
          ))}
        </div>
      )}
      <div className="tabs-line">
        {tabs.map(([id, label]) => (
          <button key={id} className={ws.bottom === id ? "active" : ""} onClick={() => ws.setBottom(id)}>{label}</button>
        ))}
      </div>
      <div className="scroll">
        {ws.bottom === "problems" && (
          ws.diagnostics.length === 0 ? <p>No diagnostics. Run static analysis.</p> : ws.diagnostics.map((diag, index) => (
            <button key={`${diag.file}-${diag.line}-${index}`} className={`diag ${diag.severity}`} onClick={() => void ws.openPath(diag.file)}>
              <b>{diag.severity.toUpperCase()} · {diag.file}:{diag.line}</b>
              <div>{diag.problem}</div>
              <p>Why: {diag.why}</p>
              <p>Fix: {diag.fix}</p>
            </button>
          ))
        )}
        {ws.bottom === "output" && (
          <>
            <form className="form-row" onSubmit={(event) => { event.preventDefault(); void ws.runCommand(command); }}>
              <input type="text" value={command} onChange={(event) => setCommand(event.target.value)} style={{ flex: 1 }} />
              <button className="btn" type="submit">Run</button>
            </form>
            <pre className="log">{ws.output || "Compiler and tool output appears here. The command box only runs iverilog, vvp, verilator, or yosys inside this project."}</pre>
          </>
        )}
        {ws.bottom === "simulation" && <pre className="log">{ws.simLog || "Simulation has not been run."}</pre>}
        {ws.bottom === "waveform" && <Waveform wave={ws.wave} />}
        {ws.bottom === "report" && <ReportView />}
        {ws.bottom === "diff" && <DiffView />}
      </div>
    </section>
  );
}

function DiffView() {
  const ws = useWorkspace();
  const proposal = ws.proposal;
  if (!proposal) return <p>No patch is waiting. A failing simulation can propose one. Nothing is edited until you apply it.</p>;
  return (
    <div>
      <p><b>Root cause.</b> {proposal.root_cause}</p>
      <p><b>Evidence.</b></p>
      <ul>{proposal.evidence.map((item) => <li key={item}>{item}</li>)}</ul>
      <p><b>Proposed fix.</b> {proposal.proposed_fix}</p>
      <p><b>Why it works.</b> {proposal.why}</p>
      <div className="row">
        <button className="btn-primary" disabled={!proposal.can_apply} onClick={() => void ws.applyProposal()}>Apply Fix</button>
        <button className="btn" onClick={() => ws.setProposal(null)}>Reject</button>
        <button className="btn" onClick={() => void ws.ask("Why does this testbench or RTL fail?")}>Ask AI</button>
        <button className="btn" onClick={() => void ws.explainProposal()}>Explain Change</button>
      </div>
      <div className="diff" style={{ marginTop: 8 }}>
        {(proposal.diff || "No diff. The rule engine did not produce a patch.").split("\n").map((line, index) => (
          <div key={index} className={line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : "meta"}>{line || " "}</div>
        ))}
      </div>
    </div>
  );
}

function ReportView() {
  const ws = useWorkspace();
  if (!ws.report) return <p>No verification report yet.</p>;
  const report = ws.report;
  return (
    <div>
      <div className="row">
        <b>RTL VERIFICATION REPORT</b>
        <button className="btn" onClick={() => download(ws.reportMarkdown || "No report", `${report.project.replace(/\s+/g, "_")}_report.md`)}>Export Report</button>
      </div>
      <pre className="log">{ws.reportMarkdown}</pre>
    </div>
  );
}

function download(text: string, name: string) {
  const blob = new Blob([text], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

function Copilot() {
  const ws = useWorkspace();
  const [text, setText] = useState("");
  const prompts = [
    "Explain this always_ff block.",
    "Why is this latch being inferred?",
    "Generate assertions for this FIFO.",
    "Optimize this RTL for area.",
    "Why does my testbench fail?",
    "Find race conditions.",
    "Generate constrained-random tests.",
  ];
  return (
    <aside className="copilot">
      <div className="panel-h"><span>HEXA-R Copilot</span><span>{ws.engine?.backend_id ?? ""}</span></div>
      <div className="copilot-log">
        {ws.messages.length === 0 && <p className="lede">The copilot reads the active file, selection, diagnostics, and the last simulation log. It does not send them off the machine.</p>}
        {ws.messages.map((message) => (
          <div key={message.id} className={`bubble ${message.role}`}>
            <div className="meta">{message.role}{message.route ? ` · ${message.route}` : ""}</div>
            <pre>{message.text}</pre>
            {message.code && message.suggested_path && (
              <button className="btn" style={{ marginTop: 6 }} onClick={() => void ws.insertCode(message.suggested_path!, message.code!)}>
                Insert {message.suggested_path}
              </button>
            )}
          </div>
        ))}
        {ws.thinking && <div className="thinking">Rule engine</div>}
      </div>
      <div className="composer">
        <div className="prompts">
          {prompts.map((prompt) => <button key={prompt} onClick={() => void ws.ask(prompt)}>{prompt}</button>)}
        </div>
        <textarea
          value={text}
          placeholder="Ask HEXA-R about the open RTL..."
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              if (text.trim()) {
                void ws.ask(text.trim());
                setText("");
              }
            }
          }}
        />
        <div className="row">
          <button className="btn-primary" onClick={() => { if (text.trim()) { void ws.ask(text.trim()); setText(""); } }}>Send</button>
          <span style={{ color: "var(--mute)" }}>{ws.busy}</span>
        </div>
      </div>
    </aside>
  );
}
