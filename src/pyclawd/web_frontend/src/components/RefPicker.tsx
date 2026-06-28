// A ref picker popover: choose the working tree, HEAD, a branch, a tag, a recent
// commit, or type/paste any revision. Used for both the "Current" (right) and
// "compared with" (left) sides — identical choices on each.
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { RefInfo } from "@/types";
import { WORKING_TREE } from "@/types";

interface RefPickerProps {
  label: string;
  value: string;
  refs: RefInfo | undefined;
  onPick: (value: string) => void;
}

/** Render a ref's display label (the working-tree sentinel becomes friendly text). */
function refLabel(value: string): string {
  return value === WORKING_TREE ? "working tree" : value;
}

export function RefPicker({ label, value, refs, onPick }: RefPickerProps) {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");

  const pick = (v: string) => {
    onPick(v);
    setOpen(false);
    setFilter("");
  };

  const match = (s: string) => s.toLowerCase().includes(filter.toLowerCase());
  const branches = (refs?.branches ?? []).filter(match);
  const tags = (refs?.tags ?? []).filter(match);
  const commits = (refs?.commits ?? []).filter(
    (c) => match(c.sha) || match(c.subject),
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="default" className="font-mono">
          <span className="text-dim">{label}</span>
          <span className="max-w-[200px] truncate">{refLabel(value)}</span>
          <span className="text-[10px] text-dim">▾</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent>
        <input
          autoFocus
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && filter.trim()) pick(filter.trim());
          }}
          placeholder="branch, tag, or paste a SHA…"
          className="m-2 rounded-md border border-line px-2.5 py-1.5 text-[13px] outline-none"
        />
        <div className="overflow-auto">
          <Group title="Quick" />
          <Row selected={value === WORKING_TREE} onClick={() => pick(WORKING_TREE)} accent>
            ● Working tree (live)
          </Row>
          <Row selected={value === "HEAD"} onClick={() => pick("HEAD")} accent>
            HEAD — current branch tip
          </Row>

          {branches.length > 0 && <Group title="Branches" />}
          {branches.map((b) => (
            <Row key={b} selected={value === b} onClick={() => pick(b)}>
              {b}
            </Row>
          ))}

          {tags.length > 0 && <Group title="Tags" />}
          {tags.map((t) => (
            <Row key={t} selected={value === t} onClick={() => pick(t)}>
              {t}
            </Row>
          ))}

          {commits.length > 0 && <Group title="Recent commits" />}
          {commits.map((c) => (
            <button
              key={c.sha}
              onClick={() => pick(c.sha)}
              className={`flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-panel2 ${
                value === c.sha ? "bg-[#ddf4ff]" : ""
              }`}
            >
              <code className="font-mono text-mod">{c.sha}</code>
              <span className="flex-1 truncate">{c.subject}</span>
              <span className="font-mono text-[11px] text-dim">{c.date}</span>
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function Group({ title }: { title: string }) {
  return (
    <div className="sticky top-0 bg-panel px-3 pb-1 pt-1.5 text-[11px] uppercase tracking-wide text-dim">
      {title}
    </div>
  );
}

function Row({
  children,
  selected,
  accent,
  onClick,
}: {
  children: React.ReactNode;
  selected: boolean;
  accent?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center px-3 py-1.5 text-left hover:bg-panel2 ${
        accent ? "text-accent" : ""
      } ${selected ? "bg-[#ddf4ff]" : ""}`}
    >
      {children}
    </button>
  );
}
