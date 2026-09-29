import { useEffect, useRef } from "react";
import Editor, { type OnMount } from "@monaco-editor/react";
import type * as Monaco from "monaco-editor";
import { registerSystemVerilog } from "../monacoSetup";
import type { Diagnostic, Settings } from "../types";

type Props = {
  path: string;
  value: string;
  settings: Settings | null;
  diagnostics: Diagnostic[];
  onChange: (value: string) => void;
  onSelection: (value: string) => void;
  onAction: (action: string, selection: string) => void;
};

export function CodeEditor({ path, value, settings, diagnostics, onChange, onSelection, onAction }: Props) {
  const editorRef = useRef<Monaco.editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<typeof Monaco | null>(null);
  const actionRef = useRef(onAction);
  const selectRef = useRef(onSelection);
  actionRef.current = onAction;
  selectRef.current = onSelection;

  const onMount: OnMount = (editor, monaco) => {
    registerSystemVerilog(monaco);
    const model = editor.getModel();
    if (model) monaco.editor.setModelLanguage(model, "systemverilog");
    editorRef.current = editor;
    monacoRef.current = monaco;
    editor.onDidChangeCursorSelection(() => {
      selectRef.current(editor.getModel()?.getValueInRange(editor.getSelection()!) ?? "");
    });
    const actions: [string, string][] = [
      ["explain", "HEXA-R: Explain"],
      ["fix", "HEXA-R: Fix"],
      ["optimize", "HEXA-R: Optimize"],
      ["testbench", "HEXA-R: Generate testbench"],
      ["bugs", "HEXA-R: Find bugs"],
      ["synth", "HEXA-R: Check synthesizability"],
      ["assertions", "HEXA-R: Generate assertions"],
    ];
    actions.forEach(([id, label], index) => {
      editor.addAction({
        id: `hexa-${id}`,
        label,
        contextMenuGroupId: "hexa",
        contextMenuOrder: index,
        run: (ed) => {
          const text = ed.getModel()?.getValueInRange(ed.getSelection()!) ?? "";
          actionRef.current(id, text);
        },
      });
    });
  };

  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    const model = editor?.getModel();
    if (!editor || !monaco || !model) return;
    const markers = diagnostics
      .filter((diag) => diag.file === path)
      .map((diag) => ({
        severity:
          diag.severity === "error"
            ? monaco.MarkerSeverity.Error
            : diag.severity === "info"
              ? monaco.MarkerSeverity.Info
              : monaco.MarkerSeverity.Warning,
        message: `${diag.problem}\n\nWhy: ${diag.why}\n\nFix: ${diag.fix}`,
        startLineNumber: diag.line,
        startColumn: 1,
        endLineNumber: diag.line,
        endColumn: 200,
      }));
    monaco.editor.setModelMarkers(model, "hexa", markers);
  }, [diagnostics, path, value]);

  const theme = settings?.theme === "contrast" ? "hexa-contrast" : "hexa-graphite";
  return (
    <Editor
      path={path}
      language="systemverilog"
      theme={theme}
      value={value}
      onChange={(next) => onChange(next ?? "")}
      onMount={onMount}
      options={{
        fontFamily: "IBM Plex Mono, ui-monospace, monospace",
        fontSize: settings?.font_size ?? 13,
        tabSize: settings?.tab_size ?? 4,
        minimap: { enabled: settings?.minimap ?? true },
        wordWrap: settings?.word_wrap ? "on" : "off",
        scrollBeyondLastLine: false,
        renderLineHighlight: "line",
        bracketPairColorization: { enabled: true },
        folding: true,
        automaticLayout: true,
        padding: { top: 8 },
      }}
    />
  );
}
