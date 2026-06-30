// The review tray: lists every staged line comment grouped by file (click one to
// jump to its line), and sends them, as one assembled message, into the selected
// claude tmux pane (or copies them to the clipboard).
import { useMemo, useState } from "react";

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
  const head =
    `Code review of \`${project}\` — comparing ${base} → ${tl}.\n` +
    `${staged.length} inline comment(s) were left, each anchored to a specific line:`;
  const body = staged
    .map((c, i) => {
      const side = c.side === "old" ? "old/left side" : "new/right side";
      const code = c.code.trim() ? `\n   on line (${side}): \`${c.code.trim()}\`` : ` (${side})`;
      return `${i + 1}. ${c.file}:${c.line}${code}\n   comment: ${c.body}`;
    })
    .join("\n\n");
  return `${head}\n\n${body}`;
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

/** Wrap the review in a structured instruction so the headless agent resolves it well. */
function agentPrompt(review: string): string {
  return [
    "You are an expert software engineer resolving the results of a code review in this repository.",
    "A human reviewer read through the changes and left inline comments, each pinned to a specific",
    "file and line. Your job is to resolve every comment below.",
    "",
    review,
    "",
    "How to work:",
    "- Treat each numbered comment as a task. Open the referenced file and find the line — the quoted",
    "  code shows what is on it (old/left = the pre-change side, new/right = the post-change side).",
    "- Make the change the comment asks for by editing the file directly. If a comment is a question",
    "  or asks for an explanation rather than a change, do not edit — answer it in your summary.",
    "- Keep every edit tightly scoped to what the comment asks. Do not refactor unrelated code,",
    "  reformat untouched lines, or change behavior beyond the comments.",
    "- Match the surrounding code style and conventions. Keep existing tests passing; add or update",
    "  tests only when a comment calls for it.",
    "- If a comment is ambiguous or you disagree, make the most reasonable interpretation and flag it.",
    "- As you work, write a short one-line note before each comment you start (e.g. \"Comment 2:",
    "  switching to an absolute path in cli.py\") so progress is visible while you go.",
    "",
    "When finished, give a concise summary mapping each comment number to what you changed",
    "(which file, what was done) — or why you intentionally left it unchanged.",
  ].join("\n");
}

export function ReviewTray() {
  const { project, base, target, staged, session, settings, unstage, clearStaged, selectFile, setScrollTo } =
    useStore();
  const { data: agent } = useAgentAvailable();
  const [open, setOpen] = useState(false);
  const [msg, setMsg] = useState("");
  const [agentRun, setAgentRun] = useState<{ prompt: string; full: boolean } | null>(null);

  // Group comments by file, preserving first-seen order, for the grouped list.
  const groups = useMemo(() => {
    const m = new Map<string, typeof staged>();
    for (const c of staged) (m.get(c.file) ?? m.set(c.file, []).get(c.file)!).push(c);
    return [...m.entries()];
  }, [staged]);

  const jump = (file: string, side: string, line: number) => {
    selectFile(file);
    setScrollTo(`${side}:${line}`);
    setOpen(false);
  };

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
        <PopoverContent className="w-[460px]">
        {staged.length === 0 ? (
          <div className="p-6 text-center text-dim">
            No staged comments.
            <br />
            Click a diff line to add one.
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between border-b border-line px-3 py-2 text-[11px] text-dim">
              <span>
                <b className="text-fg">{staged.length}</b> comment{staged.length > 1 ? "s" : ""} across{" "}
                <b className="text-fg">{groups.length}</b> file{groups.length > 1 ? "s" : ""}
              </span>
            </div>
            <div className="overflow-auto">
              {groups.map(([file, comments]) => (
                <div key={file}>
                  <div className="sticky top-0 z-[1] flex items-center gap-2 border-b border-panel2 bg-panel px-3 py-1.5">
                    <span className="truncate font-mono text-[11px] text-fg" title={file}>
                      {file}
                    </span>
                    <span className="ml-auto flex-none rounded-full bg-panel2 px-1.5 text-[10px] text-dim">
                      {comments.length}
                    </span>
                  </div>
                  {comments.map((c) => (
                    <div
                      key={c.id}
                      className="group flex items-start gap-2 border-b border-panel2 px-3 py-2 hover:bg-panel"
                    >
                      <button
                        onClick={() => jump(c.file, c.side, c.line)}
                        title="Jump to this line"
                        className="flex-none rounded bg-panel2 px-1.5 py-0.5 font-mono text-[10px] text-accent hover:bg-accent hover:text-white"
                      >
                        {c.side === "old" ? "L" : "R"}
                        {c.line}
                      </button>
                      <button
                        onClick={() => jump(c.file, c.side, c.line)}
                        className="flex-1 cursor-pointer text-left text-[13px] leading-snug"
                      >
                        {c.body}
                      </button>
                      <button
                        onClick={() => unstage(c.id)}
                        className="flex-none rounded p-0.5 leading-none text-dim opacity-0 transition hover:bg-del-bg hover:text-del group-hover:opacity-100"
                        title="remove"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
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
