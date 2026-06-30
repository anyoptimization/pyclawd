// A modal that dispatches a headless `claude -p` agent for the staged review and
// streams its progress live. Edits are auto-accepted server-side, so the agent acts
// on the comments directly; the diff view auto-refreshes (SSE) as files change.
import { useEffect, useRef, useState } from "react";

import { type StreamEvent, streamAgent } from "@/api";
import { Markdown } from "@/components/Markdown";
import { Button } from "@/components/ui/button";

interface AgentPanelProps {
  project: string;
  prompt: string;
  fullAccess: boolean;
  onClose: () => void;
}

/** The prompt sent to the agent, shown as the opening "you" message (collapsible). */
function PromptMessage({ prompt }: { prompt: string }) {
  const [open, setOpen] = useState(false);
  const firstLine = prompt.split("\n", 1)[0];
  return (
    <div className="mb-3 overflow-hidden rounded-md border border-line bg-panel">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] text-dim hover:bg-panel2"
      >
        <span className="grid h-5 w-5 flex-none place-items-center rounded-full bg-panel2 text-[10px]">
          🧑
        </span>
        <span className="font-semibold text-fg">You</span>
        {!open && <span className="truncate text-dim">{firstLine}</span>}
        <span className="ml-auto flex-none">{open ? "▾ hide prompt" : "▸ show prompt"}</span>
      </button>
      {open && (
        <div className="max-h-56 overflow-auto whitespace-pre-wrap border-t border-line px-3 py-2 font-mono text-[11.5px] leading-relaxed text-fg">
          {prompt}
        </div>
      )}
    </div>
  );
}

/** Renders one agent event, styled by kind. */
function EventLine({ event }: { event: StreamEvent }) {
  switch (event.kind) {
    case "user": // a follow-up message you sent — right-aligned bubble
      return (
        <div className="mb-2 flex justify-end">
          <div className="max-w-[85%] whitespace-pre-wrap rounded-md border border-accent/30 bg-[#ddf4ff] px-3 py-1.5 text-[13px] text-fg">
            {event.text}
          </div>
        </div>
      );
    case "text": // assistant narration — prose (markdown)
      return (
        <div className="mb-2 rounded-md bg-panel px-3 py-2">
          <Markdown>{event.text}</Markdown>
        </div>
      );
    case "tool": // a tool call — monospace, dim
      return <div className="mb-1 truncate font-mono text-[12px] text-accent">{event.text}</div>;
    case "result": // final summary — boxed (markdown)
      return (
        <div className="my-2 rounded-md border border-add/40 bg-add-bg px-3 py-2">
          <Markdown>{event.text}</Markdown>
        </div>
      );
    case "done":
      return <div className="mb-1 font-mono text-[12px] text-add">✓ {event.text}</div>;
    case "error":
      return <div className="mb-1 whitespace-pre-wrap font-mono text-[12px] text-del">{event.text}</div>;
    default: // log
      return <div className="mb-1 font-mono text-[12px] text-dim">{event.text}</div>;
  }
}

const MODELS = ["sonnet", "opus", "haiku"];

export function AgentPanel({ project, prompt, fullAccess, onClose }: AgentPanelProps) {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [running, setRunning] = useState(true);
  const [model, setModel] = useState("sonnet");
  const [session, setSession] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const logRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const modelRef = useRef(model);
  modelRef.current = model;
  const started = useRef(false);

  // Run one turn (initial prompt, or a follow-up that resumes the session id).
  const run = (text: string, resume?: string) => {
    const controller = new AbortController();
    abortRef.current = controller;
    setRunning(true);
    streamAgent(
      { project, prompt: text, fullAccess, model: modelRef.current, resume },
      (e) => {
        if (e.kind === "session") setSession(e.text); // capture id; don't render
        else setEvents((prev) => [...prev, e]);
      },
      controller.signal,
    )
      .catch((err) => {
        if (err?.name !== "AbortError")
          setEvents((prev) => [...prev, { kind: "error", text: String(err.message ?? err) }]);
      })
      .finally(() => setRunning(false));
  };

  // Kick off the initial run exactly once.
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    run(prompt);
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [events]);

  const sendFollowUp = () => {
    const text = draft.trim();
    if (!text || running || !session) return;
    setEvents((prev) => [...prev, { kind: "user", text }]);
    setDraft("");
    run(text, session);
  };

  return (
    <div
      className="fixed inset-0 z-[110] flex items-center justify-center bg-[rgba(20,24,28,0.3)]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !running) onClose();
      }}
    >
      <div className="flex h-[78vh] w-[760px] max-w-[94vw] flex-col overflow-hidden rounded-xl border border-line bg-canvas shadow-[0_18px_54px_rgba(0,0,0,0.28)]">
        <div className="flex items-center gap-2 border-b border-line bg-panel px-4 py-2.5">
          <span className="font-semibold">🤖 Claude agent · {project}</span>
          <span className={`font-mono text-xs ${fullAccess ? "text-del" : "text-dim"}`}>
            {fullAccess ? "full access" : "edits only"}
          </span>
          <label className="ml-2 flex items-center gap-1 text-xs text-dim">
            model
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="rounded-md border border-line bg-canvas px-1.5 py-0.5 text-xs text-fg outline-none focus:border-accent"
            >
              {MODELS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <span className="flex-1" />
          {running ? (
            <span className="flex items-center gap-1.5 text-xs text-accent">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" /> working…
            </span>
          ) : (
            <span className="text-xs text-add">idle</span>
          )}
        </div>

        <div ref={logRef} className="flex-1 overflow-auto p-4 leading-relaxed">
          <PromptMessage prompt={prompt} />
          {events.length === 0 && <div className="font-mono text-xs text-dim">starting agent…</div>}
          {events.map((e, i) => (
            <EventLine key={i} event={e} />
          ))}
        </div>

        <div className="space-y-2 border-t border-line px-4 py-2.5">
          <div className="flex items-end gap-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendFollowUp();
                }
              }}
              placeholder={
                running ? "Agent is working…" : session ? "Reply to the agent — Enter to send, Shift+Enter for a newline" : "Starting…"
              }
              rows={2}
              className="min-h-[40px] flex-1 resize-y rounded-md border border-line bg-canvas p-2 font-sans text-[13px] leading-relaxed outline-none focus:border-accent focus:ring-2 focus:ring-accent/25 disabled:opacity-60"
              disabled={running || !session}
            />
            <Button
              variant="accent"
              onClick={sendFollowUp}
              disabled={running || !draft.trim() || !session}
            >
              Send
            </Button>
          </div>
          <div className="flex items-center gap-2">
            {running ? (
              <Button onClick={() => abortRef.current?.abort()}>Stop</Button>
            ) : (
              <Button onClick={onClose}>Close</Button>
            )}
            <span className="text-xs text-dim">
              The agent edits files directly — changes appear live in the diff. Reply to keep the chat going.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
