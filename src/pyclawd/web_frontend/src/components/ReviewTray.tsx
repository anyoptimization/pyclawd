// The review tray: lists staged line comments and sends them, as one assembled
// message, into the selected claude tmux pane (or copies them to the clipboard).
import { useState } from "react";

import { api } from "@/api";
import { AgentPanel } from "@/components/AgentPanel";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAgentAvailable } from "@/hooks";
import { useStore } from "@/store";
import { WORKING_TREE } from "@/types";

/** Build the human-readable review message from the staged comments. */
function reviewText(
  project: string | null,
  base: string,
  target: string,
  staged: ReturnType<typeof useStore>["staged"],
): string {
  const tl = target === WORKING_TREE ? "working tree" : target;
  const head = `Review of ${project} (${base} → ${tl}). Please address these ${staged.length} comment(s):`;
  const body = staged
    .map((c, i) => {
      const code = c.code.trim() ? ` (\`${c.code.trim()}\`)` : "";
      return `${i + 1}. ${c.file}:${c.line}${code} — ${c.body}`;
    })
    .join("\n");
  return `${head}\n${body}`;
}

async function copyText(text: string): Promise<void> {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.top = "-1000px";
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  ta.remove();
}

/** Wrap the review in an instruction so the headless agent makes the edits. */
function agentPrompt(review: string): string {
  return (
    "You are addressing code review comments in this repository. " +
    "Make the necessary edits to the files directly, then briefly summarise what you changed.\n\n" +
    review
  );
}

export function ReviewTray() {
  const { project, base, target, staged, session, settings, unstage, clearStaged } = useStore();
  const { data: agent } = useAgentAvailable();
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState("");
  const [agentRun, setAgentRun] = useState<{ prompt: string; full: boolean } | null>(null);

  const text = () => reviewText(project, base, target, staged);

  const copy = async () => {
    await copyText(text());
    setMsg("copied ✓");
  };

  const send = async () => {
    if (!session) {
      setMsg("no tmux session — use Copy instead");
      return;
    }
    setMsg("sending…");
    try {
      await api.send(session, text(), settings.sendSubmit, settings.sendFocus);
      clearStaged();
      setMsg("sent ✓");
      setTimeout(() => setOpen(false), 650);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "failed");
    }
  };

  const runAgent = (full: boolean) => {
    setOpen(false);
    setAgentRun({ prompt: agentPrompt(text()), full });
  };

  return (
    <>
      {agentRun !== null && project && (
        <AgentPanel
          project={project}
          prompt={agentRun.prompt}
          fullAccess={agentRun.full}
          onClose={() => setAgentRun(null)}
        />
      )}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button variant="default" className={staged.length ? "border-accent" : ""}>
            <b>Review ({staged.length})</b>
            <span className="text-[10px] text-dim">▾</span>
          </Button>
        </PopoverTrigger>
        <PopoverContent>
        {staged.length === 0 ? (
          <div className="p-6 text-center text-dim">
            No staged comments.
            <br />
            Click a diff line to add one.
          </div>
        ) : (
          <>
            <div className="overflow-auto">
              {staged.map((c) => (
                <div key={c.id} className="flex items-start gap-2 border-b border-panel2 px-3 py-2">
                  <span className="flex-none pt-0.5 font-mono text-[11px] text-accent">
                    {c.file.split("/").pop()}:{c.line}
                  </span>
                  <span className="flex-1">{c.body}</span>
                  <button
                    onClick={() => unstage(c.id)}
                    className="text-base leading-none text-dim hover:text-del"
                    title="remove"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2 border-t border-line px-3 py-2.5">
              <Button
                onClick={() => runAgent(false)}
                disabled={!agent?.available}
                title={
                  agent?.available
                    ? "Run a headless claude agent — edits files only (no commands)"
                    : "claude CLI not found"
                }
              >
                🤖 Run (edits only)
              </Button>
              <Button
                variant="accent"
                onClick={() => runAgent(true)}
                disabled={!agent?.available}
                title={
                  agent?.available
                    ? "Run a headless claude agent — edits files AND runs commands (full access)"
                    : "claude CLI not found"
                }
              >
                🤖 Run (full access)
              </Button>
              <Button onClick={send} disabled={!session} title={session ? "" : "pick a tmux session"}>
                {session ? `Send → tmux` : "Send (no session)"}
              </Button>
              <Button onClick={copy}>Copy</Button>
              <Button onClick={clearStaged}>Clear</Button>
              <span className="text-xs text-add">{msg}</span>
            </div>
          </>
        )}
        </PopoverContent>
      </Popover>
    </>
  );
}
