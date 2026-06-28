// Typed fetch client for the dashboard's REST API. Every call returns the typed
// shapes from types.ts; non-2xx responses throw with the backend's error detail.
import type {
  ChangesResponse,
  FileView,
  ProjectsResponse,
  RefInfo,
  Session,
} from "@/types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const qs = (params: Record<string, string | boolean | undefined>): string => {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
};

export const api = {
  projects: () => request<ProjectsResponse>("/api/projects"),

  refs: (project: string) => request<RefInfo>(`/api/refs${qs({ project })}`),

  files: (project: string) =>
    request<{ files: string[] }>(`/api/files${qs({ project })}`),

  changes: (project: string, base: string, target: string, all: boolean) =>
    request<ChangesResponse>(`/api/changes${qs({ project, base, target, all })}`),

  diff: (project: string, base: string, target: string, path: string, mode: string) =>
    request<FileView>(`/api/diff${qs({ project, base, target, path, mode })}`),

  sessions: () => request<{ sessions: Session[] }>("/api/sessions"),

  config: () => request<{ roots: string[] }>("/api/config"),

  setConfig: (roots: string[]) =>
    request<{ roots: string[] }>("/api/config", {
      method: "POST",
      body: JSON.stringify({ roots }),
    }),

  star: (name: string, starred: boolean) =>
    request<{ ok: boolean }>("/api/projects/star", {
      method: "POST",
      body: JSON.stringify({ name, starred }),
    }),

  addProject: (path: string, name?: string) =>
    request<{ name: string }>("/api/projects/add", {
      method: "POST",
      body: JSON.stringify({ path, name }),
    }),

  removeProject: (name: string) =>
    request<{ ok: boolean }>("/api/projects/remove", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  send: (target: string, text: string, submit: boolean, focus: boolean) =>
    request<{ ok: boolean }>("/api/send", {
      method: "POST",
      body: JSON.stringify({ target, text, submit, focus }),
    }),

  agentAvailable: () => request<{ available: boolean }>("/api/agent"),

  runAvailable: (project: string) =>
    request<{ pyclawd: boolean; configured: boolean; verbs: string[] }>(
      `/api/run${qs({ project })}`,
    ),
};

/** One streamed progress frame from the agent or the verb runner. */
export interface StreamEvent {
  kind: "log" | "text" | "tool" | "result" | "out" | "done" | "error";
  text: string;
}

/** POST `body` to `url` and invoke `onEvent` for each SSE frame until the stream ends. */
async function streamSSE(
  url: string,
  body: unknown,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const data = frame.split("\n").find((l) => l.startsWith("data: "));
      if (data) onEvent(JSON.parse(data.slice(6)) as StreamEvent);
    }
  }
}

/** Dispatch a headless `claude -p` agent and stream its progress (abort to stop it). */
export const streamAgent = (
  project: string,
  prompt: string,
  fullAccess: boolean,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
) => streamSSE("/api/agent/run", { project, prompt, full_access: fullAccess }, onEvent, signal);

/** Run a pyclawd verb in the project and stream its output (abort to stop it). */
export const streamRun = (
  project: string,
  verb: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
) => streamSSE("/api/run", { project, verb }, onEvent, signal);
