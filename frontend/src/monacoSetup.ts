import * as monaco from "monaco-editor";
import { loader } from "@monaco-editor/react";
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";

self.MonacoEnvironment = {
  getWorker() {
    return new editorWorker();
  },
};

loader.config({ monaco });

let registered = false;

export function registerSystemVerilog(monacoApi: typeof monaco) {
  if (registered) return;
  registered = true;
  monacoApi.languages.register({ id: "systemverilog" });
  monacoApi.languages.setLanguageConfiguration("systemverilog", {
    comments: { lineComment: "//", blockComment: ["/*", "*/"] },
    brackets: [
      ["{", "}"],
      ["[", "]"],
      ["(", ")"],
    ],
    folding: {
      markers: { start: /\bbegin\b/, end: /\bend\b/ },
    },
    autoClosingPairs: [
      { open: "(", close: ")" },
      { open: "[", close: "]" },
      { open: "{", close: "}" },
    ],
  });
  monacoApi.languages.setMonarchTokensProvider("systemverilog", {
    keywords: [
      "module", "endmodule", "input", "output", "inout", "logic", "wire", "reg", "bit",
      "int", "integer", "parameter", "localparam", "assign", "always", "always_ff",
      "always_comb", "always_latch", "posedge", "negedge", "begin", "end", "if", "else",
      "case", "endcase", "default", "unique", "priority", "for", "while", "return",
      "function", "endfunction", "task", "endtask", "typedef", "enum", "struct",
      "package", "import", "assert", "property", "disable", "iff", "signed", "unsigned",
      "generate", "endgenerate", "genvar", "initial", "posedge",
    ],
    tokenizer: {
      root: [
        [/\/\/.*$/, "comment"],
        [/\/\*/, "comment", "@comment"],
        [/`[A-Za-z_]\w*/, "keyword"],
        [/\b\d+'[bBhHdD][0-9a-fA-FxXzZ_]+\b/, "number"],
        [/\b\d+\b/, "number"],
        [/"([^"\\]|\\.)*"/, "string"],
        [/[A-Za-z_]\w*/, { cases: { "@keywords": "keyword", "@default": "identifier" } }],
        [/[{}()\[\]]/, "@brackets"],
        [/[<>=!~&|^+\-*/]+/, "operator"],
      ],
      comment: [
        [/[^/*]+/, "comment"],
        [/\*\//, "comment", "@pop"],
        [/[/*]/, "comment"],
      ],
    },
  });
  monacoApi.languages.registerCompletionItemProvider("systemverilog", {
    provideCompletionItems: (model, position) => {
      const word = model.getWordUntilPosition(position);
      const range = {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: word.startColumn,
        endColumn: word.endColumn,
      };
      const keywords = ["always_ff", "always_comb", "logic", "module", "endmodule", "posedge", "parameter", "assert", "unique", "case", "default"];
      return {
        suggestions: keywords.map((label) => ({
          label,
          kind: monacoApi.languages.CompletionItemKind.Keyword,
          insertText: label,
          range,
        })),
      };
    },
  });
  monacoApi.editor.defineTheme("hexa-graphite", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "keyword", foreground: "7dcea0" },
      { token: "comment", foreground: "6d7680" },
      { token: "number", foreground: "e0a15a" },
      { token: "string", foreground: "d7ba7d" },
      { token: "identifier", foreground: "e6e8eb" },
    ],
    colors: {
      "editor.background": "#16181b",
      "editor.foreground": "#e6e8eb",
      "editorLineNumber.foreground": "#5c656e",
      "editorLineNumber.activeForeground": "#c5cdd4",
      "editor.selectionBackground": "#23423c",
      "editor.lineHighlightBackground": "#1c2024",
      "editorCursor.foreground": "#3dbea5",
      "editorWidget.background": "#1e2227",
      "minimap.background": "#16181b",
    },
  });
  monacoApi.editor.defineTheme("hexa-contrast", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "keyword", foreground: "9eefd6" },
      { token: "comment", foreground: "8b97a3" },
      { token: "number", foreground: "ffcc80" },
      { token: "string", foreground: "ffe082" },
      { token: "identifier", foreground: "ffffff" },
    ],
    colors: {
      "editor.background": "#0c0d0f",
      "editor.foreground": "#ffffff",
      "editorLineNumber.foreground": "#8b97a3",
      "editor.selectionBackground": "#1f4d45",
      "editor.lineHighlightBackground": "#15181c",
      "editorCursor.foreground": "#5ee0c5",
    },
  });
}

registerSystemVerilog(monaco);
