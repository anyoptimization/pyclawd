// Renders one file's FileView: inline or split hunks, or a full-file view. Each side
// carries its own comment gutter — a 💬 fades in on hover and stays (highlighted) on
// lines that already have a staged comment. In split view that means a comment
// affordance and line numbers on BOTH the old (left) and new (right) sides.
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "@/api";
import { Markdown } from "@/components/Markdown";
import { usePersisted } from "@/hooks";
import { statusBadge } from "@/lib/status";
import { useStore } from "@/store";
import type { DiffLine, FileView, Hunk, StagedComment } from "@/types";

/** Total px of the non-content split columns: 2×(marker+gutter) + divider. */
const SPLIT_FIXED_PX = 28 + 46 + 7 + 28 + 46;

/** colSpan large enough to span every column in either layout (browsers clamp). */
const SPAN = 12;

/** A side+line a comment attaches to, with the code on that line. */
interface Anchor {
  line: number;
  side: "old" | "new";
  code: string;
}

type Composing = Anchor | null;

/** Where to anchor a comment for a whole inline line (prefers the new side). */
function anchor(line: DiffLine): Anchor | null {
  if (line.kind === "del" && line.old != null) return { line: line.old, side: "old", code: line.content };
  if (line.new != null) return { line: line.new, side: "new", code: line.content };
  if (line.old != null) return { line: line.old, side: "old", code: line.content };
  return null;
}

export function DiffView({ view }: { view: FileView }) {
  const { layout, project, selected, staged, scrollTo, setScrollTo, selectFile } = useStore();
  const [composing, setComposing] = useState<Composing>(null);
  const [editing, setEditing] = useState<string | null>(null); // draft content, or null
  const [busy, setBusy] = useState(false);
  const qc = useQueryClient();

  // Drop any open composer / editor when switching files.
  useEffect(() => {
    setComposing(null);
    setEditing(null);
  }, [selected]);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["diff", project] });
    qc.invalidateQueries({ queryKey: ["changes", project] });
  };

  const startEdit = async () => {
    if (!project || !selected) return;
    setBusy(true);
    try {
      const { content } = await api.fileRaw(project, selected);
      setEditing(content);
    } finally {
      setBusy(false);
    }
  };

  const saveEdit = async () => {
    if (!project || !selected || editing === null) return;
    setBusy(true);
    try {
      await api.saveFile(project, selected, editing);
      setEditing(null);
      refresh();
    } finally {
      setBusy(false);
    }
  };

  const deleteFile = async () => {
    if (!project || !selected) return;
    if (!window.confirm(`Delete ${selected} from the working tree?`)) return;
    setBusy(true);
    try {
      await api.deleteFile(project, selected);
      selectFile(null);
      refresh();
    } finally {
      setBusy(false);
    }
  };

  // Scroll to (and briefly flash) a line when navigated from the review list.
  // Re-runs as the new file's diff renders; clears the request once it lands.
  useEffect(() => {
    if (!scrollTo) return;
    const el = document.querySelector<HTMLElement>(`[data-anchor~="${CSS.escape(scrollTo)}"]`);
    if (!el) return;
    el.scrollIntoView({ block: "center", behavior: "smooth" });
    el.classList.add("flash-line");
    const t = setTimeout(() => el.classList.remove("flash-line"), 1200);
    setScrollTo(null);
    return () => clearTimeout(t);
  }, [scrollTo, view, setScrollTo]);

  const fileComments = staged.filter((c) => c.file === selected).length;
  const shared = { composing, setComposing };

  let body: React.ReactNode;
  if (view.binary) {
    body = <div className="p-12 text-center text-dim">Binary file — no text diff.</div>;
  } else if (view.mode === "full") {
    body = <InlineTable rows={view.lines} {...shared} />;
  } else if (view.hunks.length === 0) {
    body = <div className="p-12 text-center text-dim">No textual changes.</div>;
  } else if (layout === "split") {
    body = <SplitTable hunks={view.hunks} {...shared} />;
  } else {
    body = <InlineTable hunks={view.hunks} {...shared} />;
  }

  const canEdit = !!selected && !view.binary;

  return (
    <>
      <div className="sticky top-0 z-[1] flex items-center gap-2.5 border-b border-line bg-panel px-4 py-2.5 font-mono text-xs">
        <span className={`h-[9px] w-[9px] rounded-[2px] ${statusBadge(view.status)}`} />
        {selected}
        {fileComments > 0 && (
          <span className="rounded-full bg-[#fff5e0] px-2 py-0.5 text-[11px] text-mod">
            💬 {fileComments} comment{fileComments > 1 ? "s" : ""}
          </span>
        )}
        <span className="flex-1" />
        {editing !== null ? (
          <>
            <HeaderBtn onClick={saveEdit} disabled={busy} tone="accent">
              {busy ? "Saving…" : "Save"}
            </HeaderBtn>
            <HeaderBtn onClick={() => setEditing(null)} disabled={busy}>
              Cancel
            </HeaderBtn>
          </>
        ) : (
          <>
            {canEdit && (
              <HeaderBtn onClick={startEdit} disabled={busy} title="Edit this file in the browser">
                ✎ Edit
              </HeaderBtn>
            )}
            {selected && (
              <HeaderBtn onClick={deleteFile} disabled={busy} tone="del" title="Delete this file">
                🗑 Delete
              </HeaderBtn>
            )}
          </>
        )}
      </div>
      {editing !== null ? (
        <div className="p-3">
          <textarea
            value={editing}
            onChange={(e) => setEditing(e.target.value)}
            spellCheck={false}
            className="block h-[calc(100vh-220px)] min-h-[320px] w-full resize-y rounded-md border border-line bg-canvas p-3 font-mono text-[12.5px] leading-[1.55] outline-none focus:border-accent [tab-size:var(--tab,4)]"
          />
        </div>
      ) : (
        body
      )}
    </>
  );
}

/** A compact header action button (used for Edit/Delete/Save/Cancel on a file). */
function HeaderBtn({
  onClick,
  disabled,
  tone,
  title,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  tone?: "accent" | "del";
  title?: string;
  children: React.ReactNode;
}) {
  const toneCls =
    tone === "accent"
      ? "border-accent bg-accent text-white hover:brightness-110"
      : tone === "del"
        ? "border-line text-del hover:bg-del-bg hover:border-del"
        : "border-line text-fg hover:bg-panel2";
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`rounded-md border px-2 py-0.5 text-[11px] font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${toneCls}`}
    >
      {children}
    </button>
  );
}

interface Shared {
  composing: Composing;
  setComposing: (c: Composing) => void;
}

// No background here — callers add exactly one (`bg-panel` for context, or the
// add/del tint), so the gutter never loses its tint to a CSS-order override.
const GUT =
  "w-px select-none whitespace-nowrap border-r border-line px-2 text-right align-top text-dim";

/** A line's code cell content: Pygments HTML when present, else plain text. */
function Code({ line }: { line?: DiffLine }) {
  if (!line) return null;
  if (line.html != null) return <span dangerouslySetInnerHTML={{ __html: line.html }} />;
  return <>{line.content}</>;
}

// --------------------------------------------------------------------------- //
// Inline / full-file.
// --------------------------------------------------------------------------- //

function InlineTable({ hunks, rows, composing, setComposing }: { hunks?: Hunk[]; rows?: DiffLine[] } & Shared) {
  return (
    <table className="w-full border-collapse font-mono text-xs leading-[1.55]">
      <tbody>
        {hunks
          ? hunks.map((h, hi) => (
              <HunkHeader key={`h${hi}`} header={h.header}>
                {h.lines.map((line, i) => (
                  <InlineRow key={i} line={line} composing={composing} setComposing={setComposing} />
                ))}
              </HunkHeader>
            ))
          : rows?.map((line, i) => (
              <InlineRow key={i} line={line} composing={composing} setComposing={setComposing} />
            ))}
      </tbody>
    </table>
  );
}

function InlineRow({ line, composing, setComposing }: { line: DiffLine } & Shared) {
  const a = anchor(line);
  const sign = line.kind === "add" ? "+" : line.kind === "del" ? "−" : "";
  const tone = line.kind === "add" ? "bg-add-bg" : line.kind === "del" ? "bg-del-bg" : "";
  const gutTone = line.kind === "add" ? "bg-add-gut" : line.kind === "del" ? "bg-del-gut" : "bg-panel";
  return (
    <>
      <tr className="group" data-anchor={a ? `${a.side}:${a.line}` : undefined}>
        <Marker anchor={a} onOpen={setComposing} />
        <td className={`${GUT} ${gutTone}`}>{line.old ?? ""}</td>
        <td className={`${GUT} ${gutTone}`}>{line.new ?? ""}</td>
        <td className={`px-1.5 text-center align-top text-dim ${tone}`}>{sign}</td>
        <td className={`whitespace-pre-wrap px-2.5 align-top [overflow-wrap:anywhere] [tab-size:var(--tab,4)] ${tone}`}><Code line={line} /></td>
      </tr>
      <Extras anchor={a} composing={composing} setComposing={setComposing} />
    </>
  );
}

// --------------------------------------------------------------------------- //
// Split (side-by-side). Each side has its own marker + line-number gutter.
// --------------------------------------------------------------------------- //

function SplitTable({ hunks, composing, setComposing }: { hunks: Hunk[] } & Shared) {
  const [ratio, setRatio] = usePersisted("pyclawd.web.splitRatio", 0.5);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const dragging = useRef(false);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setWidth(el.clientWidth));
    observer.observe(el);
    setWidth(el.clientWidth);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const move = (e: MouseEvent) => {
      if (!dragging.current || !wrapRef.current) return;
      const rect = wrapRef.current.getBoundingClientRect();
      const c = rect.width - SPLIT_FIXED_PX;
      setRatio(Math.max(0.1, Math.min(0.9, (e.clientX - rect.left - 74) / c))); // 74 = markerL + gutter
    };
    const up = () => {
      if (dragging.current) {
        dragging.current = false;
        document.body.style.userSelect = "";
      }
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, [setRatio]);

  const content = Math.max(0, width - SPLIT_FIXED_PX);
  const startDrag = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).dataset.mid) {
      dragging.current = true;
      document.body.style.userSelect = "none";
      e.preventDefault();
    }
  };

  return (
    <div ref={wrapRef} onMouseDown={startDrag}>
      <table style={{ width: width || "100%", tableLayout: "fixed" }} className="border-collapse font-mono text-xs leading-[1.55]">
        <colgroup>
          <col style={{ width: 28 }} />
          <col style={{ width: 46 }} />
          <col style={{ width: content * ratio }} />
          <col style={{ width: 7 }} />
          <col style={{ width: 28 }} />
          <col style={{ width: 46 }} />
          <col style={{ width: content * (1 - ratio) }} />
        </colgroup>
        <tbody>
          {hunks.map((h, hi) => (
            <HunkHeader key={hi} header={h.header}>
              <SplitRows lines={h.lines} composing={composing} setComposing={setComposing} />
            </HunkHeader>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SplitRows({ lines, composing, setComposing }: { lines: DiffLine[] } & Shared) {
  const rows: { left?: DiffLine; right?: DiffLine; ctx?: DiffLine }[] = [];
  let dels: DiffLine[] = [];
  let adds: DiffLine[] = [];
  const flush = () => {
    for (let i = 0; i < Math.max(dels.length, adds.length); i++) rows.push({ left: dels[i], right: adds[i] });
    dels = [];
    adds = [];
  };
  for (const line of lines) {
    if (line.kind === "ctx") {
      flush();
      rows.push({ ctx: line });
    } else if (line.kind === "del") dels.push(line);
    else adds.push(line);
  }
  flush();

  return (
    <>
      {rows.map((row, i) => {
        const left = row.ctx ?? row.left;
        const right = row.ctx ?? row.right;
        const leftAnchor = left ? anchor(left) : null;
        const rightAnchor = right ? anchor(right) : null;
        return (
          <ExtrasGroup key={i} anchors={[leftAnchor, rightAnchor]} composing={composing} setComposing={setComposing}>
            <tr
              className="group"
              data-anchor={[leftAnchor, rightAnchor]
                .filter((x): x is Anchor => x !== null)
                .map((x) => `${x.side}:${x.line}`)
                .join(" ")}
            >
              <Marker anchor={leftAnchor} onOpen={setComposing} />
              <td className={`${GUT} ${left && !row.ctx ? "bg-del-gut" : "bg-panel"}`}>{left?.old ?? ""}</td>
              <td className={`whitespace-pre-wrap px-2.5 align-top [overflow-wrap:anywhere] [tab-size:var(--tab,4)] ${left ? (row.ctx ? "" : "bg-del-bg") : "bg-panel2"}`}>
                <Code line={left} />
              </td>
              <td data-mid="1" className="cursor-col-resize bg-line p-0 hover:bg-accent" />
              <Marker anchor={rightAnchor} onOpen={setComposing} />
              <td className={`${GUT} ${right && !row.ctx ? "bg-add-gut" : "bg-panel"}`}>{right?.new ?? ""}</td>
              <td className={`whitespace-pre-wrap px-2.5 align-top [overflow-wrap:anywhere] [tab-size:var(--tab,4)] ${right ? (row.ctx ? "" : "bg-add-bg") : "bg-panel2"}`}>
                <Code line={right} />
              </td>
            </tr>
          </ExtrasGroup>
        );
      })}
    </>
  );
}

// --------------------------------------------------------------------------- //
// Shared pieces.
// --------------------------------------------------------------------------- //

function HunkHeader({ header, children }: { header: string; children: React.ReactNode }) {
  return (
    <>
      <tr>
        <td colSpan={SPAN} className="bg-[#ddf4ff] px-2.5 py-1 text-[#0550ae]">
          @@ {header}
        </td>
      </tr>
      {children}
    </>
  );
}

/** The per-side comment gutter cell. */
function Marker({ anchor, onOpen }: { anchor: Anchor | null; onOpen: (a: Anchor) => void }) {
  const { selected, staged } = useStore();
  const has = anchor
    ? staged.some((c) => c.file === selected && c.side === anchor.side && c.line === anchor.line)
    : false;
  return (
    <td
      onClick={anchor ? () => onOpen(anchor) : undefined}
      title={anchor ? "Comment on this line" : ""}
      className={`w-7 select-none border-r border-line text-center align-top text-[11px] leading-[1.55] ${
        anchor ? "cursor-pointer" : ""
      } ${has ? "bg-[#fff5e0]" : "bg-panel"}`}
    >
      {anchor && (
        <span className={has ? "text-star" : "text-accent opacity-0 transition-opacity group-hover:opacity-70"}>
          💬
        </span>
      )}
    </td>
  );
}

/** Renders the composer/staged-notes rows for a single inline line's anchor. */
function Extras({ anchor, composing, setComposing }: { anchor: Anchor | null } & Shared) {
  if (!anchor) return null;
  return <ExtrasGroup anchors={[anchor]} composing={composing} setComposing={setComposing} />;
}

/** Emits a full-width row under a diff row carrying composer + staged notes per anchor. */
function ExtrasGroup({
  anchors,
  composing,
  setComposing,
  children,
}: { anchors: (Anchor | null)[]; children?: React.ReactNode } & Shared) {
  const { selected, staged } = useStore();
  // Dedup by side:line — in split view a context row passes the same anchor for
  // both sides, which would otherwise render the note twice (and collide on key).
  const seen = new Set<string>();
  const extras = anchors
    .filter((a): a is Anchor => a !== null)
    .filter((a) => {
      const key = `${a.side}:${a.line}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .map((a) => ({
      anchor: a,
      notes: staged.filter((c) => c.file === selected && c.side === a.side && c.line === a.line),
      composing: composing?.side === a.side && composing?.line === a.line,
    }))
    .filter((x) => x.notes.length > 0 || x.composing);

  return (
    <>
      {children}
      {extras.map((x) => (
        <tr key={`${x.anchor.side}:${x.anchor.line}`}>
          <td colSpan={SPAN} className="border-y border-line bg-panel p-0">
            <div className="max-w-3xl space-y-2 py-2 pr-3 pl-12">
              {x.notes.map((n) => (
                <StagedNote key={n.id} note={n} />
              ))}
              {x.composing && <Composer anchor={x.anchor} onClose={() => setComposing(null)} />}
            </div>
          </td>
        </tr>
      ))}
    </>
  );
}

function Composer({ anchor, onClose }: { anchor: Anchor; onClose: () => void }) {
  const { selected, staged, stage } = useStore();
  const submit = (body: string) => {
    if (!selected) return;
    stage({
      id: `c${Date.now()}_${staged.length}`,
      file: selected,
      line: anchor.line,
      side: anchor.side,
      code: anchor.code,
      body,
    });
    onClose();
  };
  return (
    <div className="overflow-hidden rounded-md border border-accent bg-canvas shadow-sm">
      <div className="flex items-center gap-2 border-b border-line bg-panel px-3 py-1.5 text-[11px]">
        <CommentBadge />
        <span className="font-semibold text-fg">Add comment</span>
        <LineRef anchor={anchor} />
        <span className="ml-auto truncate font-mono text-[10px] text-dim">{selected}</span>
      </div>
      <CommentEditor initial="" saveLabel="Add comment" onSave={submit} onCancel={onClose} />
    </div>
  );
}

/** A markdown comment editor: textarea (cursor lands at the end) with a live
 *  rendered preview below. Used both to add a new comment and to edit one. */
function CommentEditor({
  initial,
  saveLabel,
  onSave,
  onCancel,
}: {
  initial: string;
  saveLabel: string;
  onSave: (body: string) => void;
  onCancel: () => void;
}) {
  const [body, setBody] = useState(initial);
  const ref = useRef<HTMLTextAreaElement>(null);

  // Focus on mount and place the caret at the very end of the existing text.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, []);

  const save = () => {
    if (body.trim()) onSave(body.trim());
  };

  return (
    <div className="p-2">
      <textarea
        ref={ref}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") save();
          else if (e.key === "Escape") onCancel();
        }}
        placeholder="Write a comment in markdown — ⌘/Ctrl+Enter to save, Esc to cancel"
        className="block min-h-[72px] w-full resize-y rounded-md border border-line bg-canvas p-2 font-mono text-[12.5px] leading-relaxed outline-none focus:border-accent focus:ring-2 focus:ring-accent/25"
      />
      {body.trim() && (
        <div className="mt-2 rounded-md border border-line bg-panel px-2.5 py-2">
          <div className="mb-1 text-[9.5px] font-semibold uppercase tracking-wide text-dim">Preview</div>
          <Markdown>{body}</Markdown>
        </div>
      )}
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="text-[10px] text-dim">Markdown supported</span>
        <div className="flex gap-2">
          <button
            onClick={onCancel}
            className="rounded-md px-2.5 py-1 text-[12px] font-medium text-dim hover:bg-panel2"
          >
            Cancel
          </button>
          <button
            onClick={save}
            disabled={!body.trim()}
            className="rounded-md bg-accent px-3 py-1 text-[12px] font-semibold text-white shadow-sm transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saveLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

/** A small round 💬 chip used in comment headers. */
function CommentBadge() {
  return (
    <span className="grid h-5 w-5 flex-none place-items-center rounded-full bg-[#ddf4ff] text-[10px] leading-none">
      💬
    </span>
  );
}

/** A compact side+line reference badge (``L`` = old/left, ``R`` = new/right). */
function LineRef({ anchor }: { anchor: Anchor }) {
  return (
    <span className="rounded bg-panel2 px-1.5 py-0.5 font-mono text-[10px] text-dim">
      {anchor.side === "old" ? "L" : "R"}
      {anchor.line}
    </span>
  );
}

function StagedNote({ note }: { note: StagedComment }) {
  const { unstage, editComment } = useStore();
  const [editing, setEditing] = useState(false);

  const startEdit = () => setEditing(true);

  return (
    <div className="group/c overflow-hidden rounded-md border border-line bg-canvas shadow-sm">
      <div className="flex items-center gap-2 border-b border-line bg-panel px-3 py-1.5 text-[11px]">
        <CommentBadge />
        <span className="font-semibold text-fg">Review note</span>
        <LineRef anchor={{ line: note.line, side: note.side, code: note.code }} />
        <span className="ml-auto rounded-full border border-[#e6d8a8] bg-[#fff8e6] px-1.5 py-0.5 text-[10px] font-medium text-mod">
          pending
        </span>
        {!editing && (
          <button
            onClick={startEdit}
            title="Edit comment"
            className="grid h-7 w-7 flex-none place-items-center rounded-md text-[15px] leading-none text-dim transition hover:bg-panel2 hover:text-accent"
          >
            ✎
          </button>
        )}
        <button
          onClick={() => unstage(note.id)}
          title="Delete comment"
          className="grid h-7 w-7 flex-none place-items-center rounded-md text-[15px] leading-none text-dim transition hover:bg-del-bg hover:text-del"
        >
          ✕
        </button>
      </div>
      {editing ? (
        <CommentEditor
          initial={note.body}
          saveLabel="Save"
          onSave={(body) => {
            editComment(note.id, body);
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <div
          onClick={startEdit}
          title="Click to edit"
          className="cursor-text px-3 py-2"
        >
          <Markdown>{note.body}</Markdown>
        </div>
      )}
    </div>
  );
}
