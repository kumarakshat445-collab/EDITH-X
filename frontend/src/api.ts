export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const detail = data.detail;
    throw new Error(typeof detail === "string" ? detail : response.statusText);
  }
  return data as T;
}

export async function streamCopilot(
  body: unknown,
  onChunk: (text: string) => void,
): Promise<Record<string, unknown>> {
  const response = await fetch("/api/copilot", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let donePayload: Record<string, unknown> | null = null;
  while (true) {
    const chunk = await reader.read();
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.split("\n").find((item) => item.startsWith("data: "));
      if (!line) continue;
      const payload = JSON.parse(line.slice(6)) as { type: string; text?: string; detail?: string };
      if (payload.type === "error") throw new Error(payload.detail || "Copilot failed.");
      if (payload.type === "chunk" && payload.text) onChunk(payload.text);
      if (payload.type === "done") donePayload = payload as Record<string, unknown>;
    }
  }
  if (!donePayload) throw new Error("Copilot stream ended without a result.");
  return donePayload;
}
