// A modal that runs a pyclawd verb (check/test/golden/…) in the project and streams
// its output live, with a pass/fail verdict. Mirrors AgentPanel but for the
// deterministic CLI verbs rather than the LLM agent.
import { useEffect, useRef, useState } from "react";

import { type StreamEvent, streamRun } from "@/api";
import { Button } from "@/components/ui/button";

interface RunPanelProps {
  project: string;
  verb: string;
  onClose: () => void;
}

export function RunPanel({ project, verb, onClose }: RunPanelProps) {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [running, setRunning] = useState(true);
  const logRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;
    streamRun(project, verb, (e) => setEvents((prev) => [...prev, e]), controller.signal)
      .catch((err) => {
        if (err?.name !== "AbortError") {
          setEvents((prev) => [...prev, { kind: "error", text: String(err.message ?? err) }]);
        }
      })
      .finally(() => setRunning(false));
    return () => controller.abort();
  }, [project, verb]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [events]);

  const done = events.find((e) => e.kind === "done");
  const passed = done?.text.startsWith("✓");

  return (
    <div
      className="fixed inset-0 z-[110] flex items-center justify-center bg-[rgba(20,24,28,0.3)]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !running) onClose();
      }}
    >
      <div className="flex h-[70vh] w-[820px] max-w-[94vw] flex-col overflow-hidden rounded-xl border border-line bg-canvas shadow-[0_18px_54px_rgba(0,0,0,0.28)]">
        <div className="flex items-center gap-2 border-b border-line bg-panel px-4 py-2.5">
          <span className="font-semibold">⚙ pyclawd {verb}</span>
          <span className="font-mono text-xs text-dim">· {project}</span>
          <span className="flex-1" />
          {running ? (
            <span className="flex items-center gap-1.5 text-xs text-accent">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-accent" /> running…
            </span>
          ) : (
            <span className={`text-xs ${passed ? "text-add" : "text-del"}`}>{done?.text ?? "stopped"}</span>
          )}
        </div>

        <div ref={logRef} className="flex-1 overflow-auto bg-[#0d1117] p-4 font-mono text-xs leading-relaxed">
          {events.length === 0 && <div className="text-[#8b949e]">starting…</div>}
          {events.map((e, i) => {
            if (e.kind === "log") return <div key={i} className="mb-1 text-[#58a6ff]">{e.text}</div>;
            if (e.kind === "done")
              return (
                <div key={i} className={`mt-2 font-semibold ${passed ? "text-[#3fb950]" : "text-[#f85149]"}`}>
                  {e.text}
                </div>
              );
            if (e.kind === "error") return <div key={i} className="text-[#f85149]">{e.text}</div>;
            return <div key={i} className="whitespace-pre-wrap text-[#c9d1d9]">{e.text || " "}</div>;
          })}
        </div>

        <div className="flex items-center gap-2 border-t border-line px-4 py-2.5">
          {running ? (
            <Button onClick={() => abortRef.current?.abort()}>Stop</Button>
          ) : (
            <Button variant="accent" onClick={onClose}>
              Close
            </Button>
          )}
          <span className="text-xs text-dim">Runs the pyclawd verb contract in this project.</span>
        </div>
      </div>
    </div>
  );
}
