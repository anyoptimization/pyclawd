// ⌘P / Ctrl+P quick-open palette (files + commands + projects), built on cmdk —
// shadcn's Command primitive. cmdk handles the fuzzy filtering and keyboard nav; we
// supply our own overlay so the backdrop and centering behave predictably.
import { Command } from "cmdk";
import { useEffect, useState } from "react";

import { useFiles, useProjects } from "@/hooks";
import { useStore } from "@/store";

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const store = useStore();
  const { data: files } = useFiles(store.project);
  const { data: projects } = useProjects();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "p" || e.key === "P")) {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  if (!open) return null;

  const run = (fn: () => void) => {
    fn();
    setOpen(false);
  };

  return (
    <div
      className="fixed inset-0 z-[100] bg-[rgba(20,24,28,0.22)]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) setOpen(false);
      }}
    >
      <div className="mx-auto mt-16 w-[660px] max-w-[92vw] overflow-hidden rounded-xl border border-line bg-canvas shadow-[0_18px_54px_rgba(0,0,0,0.28)]">
        <Command label="Command palette" loop>
          <Command.Input
            autoFocus
            placeholder="Go to file, run a command, switch project…"
            className="w-full border-b border-line px-4 py-3.5 text-[15px] outline-none"
          />
          <Command.List className="max-h-[52vh] overflow-auto p-1">
            <Command.Empty className="p-5 text-center text-dim">No matches.</Command.Empty>

            <Command.Group heading="Commands" className="px-2 text-[11px] uppercase text-dim">
              <Item onSelect={() => run(() => store.setMode(store.mode === "diff" ? "full" : "diff"))}>
                Toggle Diff / Full file
              </Item>
              <Item
                onSelect={() => run(() => store.setLayout(store.layout === "split" ? "inline" : "split"))}
              >
                Toggle Inline / Split
              </Item>
              <Item onSelect={() => run(() => store.setAll(!store.all))}>
                Show {store.all ? "Changed only" : "All files"}
              </Item>
            </Command.Group>

            {files?.files?.length ? (
              <Command.Group heading="Files" className="px-2 text-[11px] uppercase text-dim">
                {files.files.map((f) => (
                  <Item key={f} value={`file ${f}`} onSelect={() => run(() => store.selectFile(f))}>
                    {f}
                  </Item>
                ))}
              </Command.Group>
            ) : null}

            {projects?.projects?.length ? (
              <Command.Group heading="Projects" className="px-2 text-[11px] uppercase text-dim">
                {projects.projects.map((p) => (
                  <Item
                    key={p.name}
                    value={`project ${p.name}`}
                    onSelect={() => run(() => store.selectProject(p.name))}
                  >
                    {p.name}
                  </Item>
                ))}
              </Command.Group>
            ) : null}
          </Command.List>
        </Command>
      </div>
    </div>
  );
}

function Item({
  children,
  value,
  onSelect,
}: {
  children: React.ReactNode;
  value?: string;
  onSelect: () => void;
}) {
  return (
    <Command.Item
      value={value}
      onSelect={onSelect}
      className="flex cursor-pointer items-center gap-2 rounded-md px-3 py-1.5 text-[13px] text-fg data-[selected=true]:bg-[#ddf4ff]"
    >
      {children}
    </Command.Item>
  );
}
