// A modal that dispatches a headless `claude -p` agent for the staged review and
// streams its progress live. Edits are auto-accepted server-side, so the agent acts
// on the comments directly; the diff view auto-refreshes (SSE) as files change.
import { useEffect, useRef, useState } from "react";

import { type StreamEvent, streamAgent } from "@/api";
import { Button } from "@/components/ui/button";

interface AgentPanelProps {
  project: string;
  prompt: string;
  fullAccess: boolean;
  onClose: () => void;
}

/** Renders one agent event, styled by kind. */
function EventLine({ event }: { event: StreamEvent }) {
  switch (event.kind) {
    case "text": // assistant narration — prose
      return <div className="mb-2 whitespace-pre-wrap font-sans text-[13px] text-fg">{event.text}</div>;
    case "tool": // a tool call — monospace, dim
      return <div className="mb-1 truncate font-mono text-[12px] text-accent">{event.text}</div>;
    case "result": // final summary — boxed
      return (
        <div className="my-2 whitespace-pre-wrap rounded-md border border-add/40 bg-add-bg px-3 py-2 font-sans text-[13px] text-fg">
          {event.text}
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

export function AgentPanel({ project, prompt, fullAccess, onClose }: AgentPanelProps) {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [running, setRunning] = useState(true);
  const logRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;
    streamAgent(project, prompt, fullAccess, (e) => setEvents((prev) => [...prev, e]), controller.signal)
      .catch((err) => {
        if (err?.name !== "AbortError") {
          setEvents((prev) => [...prev, { kind: "error", text: String(err.message ?? err) }]);
        }
      })
      .finally(() => setRunning(false));
    return () => controller.abort();
  }, [project, prompt, fullAccess]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [events]);

  return (
    <div
      className="fixed inset-0 z-[110] flex items-center justify-center bg-[rgba(20,24,28,0.3)]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !running) onClose();
      }}
    >
      <div className="flex h-[70vh] w-[760px] max-w-[94vw] flex-col overflow-hidden rounded-xl border border-line bg-canvas shadow-[0_18px_54px_rgba(0,0,0,0.28)]">
        <div className="flex items-center gap-2 border-b border-line bg-panel px-4 py-2.5">
          <span className="font-semibold">🤖 Claude agent · {project}</span>
          <span className={`font-mono text-xs ${fullAccess ? "text-del" : "text-dim"}`}>
            claude -p · {fullAccess ? "full access" : "edits only"}
          </span>
          <span className="flex-1" />
          {running ? (
            <span className="flex items-center gap-1.5 text-xs text-accent">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" /> working…
            </span>
          ) : (
            <span className="text-xs text-add">finished</span>
          )}
        </div>

        <div ref={logRef} className="flex-1 overflow-auto p-4 leading-relaxed">
          {events.length === 0 && <div className="font-mono text-xs text-dim">starting agent…</div>}
          {events.map((e, i) => (
            <EventLine key={i} event={e} />
          ))}
        </div>

        <div className="flex items-center gap-2 border-t border-line px-4 py-2.5">
          {running ? (
            <Button onClick={() => abortRef.current?.abort()}>Stop agent</Button>
          ) : (
            <Button variant="accent" onClick={onClose}>
              Close
            </Button>
          )}
          <span className="text-xs text-dim">
            The agent edits files directly — changes appear live in the diff.
          </span>
        </div>
      </div>
    </div>
  );
}
