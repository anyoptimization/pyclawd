// The header: brand, project switcher, the two ref pickers, view controls
// (diff/full · inline/split · changed/all), change counts, session picker, review
// tray, and the live-refresh toggle.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ProjectSwitcher } from "@/components/ProjectSwitcher";
import { RefPicker } from "@/components/RefPicker";
import { ReviewTray } from "@/components/ReviewTray";
import { RunMenu } from "@/components/RunMenu";
import { SessionPicker } from "@/components/SessionPicker";
import { SettingsModal } from "@/components/SettingsModal";
import { Button } from "@/components/ui/button";
import { useStore } from "@/store";
import type { FileChange, RefInfo } from "@/types";

interface TopBarProps {
  refs: RefInfo | undefined;
  files: FileChange[];
  live: boolean;
  onToggleLive: (on: boolean) => void;
}

export function TopBar({ refs, files, live, onToggleLive }: TopBarProps) {
  const store = useStore();
  const qc = useQueryClient();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const counts = {
    added: files.filter((f) => f.status === "A").length,
    modified: files.filter((f) => f.status === "M").length,
    deleted: files.filter((f) => f.status === "D").length,
    renamed: files.filter((f) => f.status === "R").length,
  };

  return (
    <header className="border-b border-line bg-panel">
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2">
        <span className="font-bold tracking-tight">pyclawd web</span>
        <ProjectSwitcher />
        <span className="mx-0.5 self-stretch w-px bg-line" />
        <RefPicker label="Current" value={store.target} refs={refs} onPick={store.setTarget} />
        <span className="text-xs text-dim">compared with</span>
        <RefPicker label="" value={store.base} refs={refs} onPick={store.setBase} />
      </div>

      <div className="flex flex-wrap items-center gap-3 px-4 py-2">
        <Segmented
          value={store.mode}
          options={[
            { v: "diff", label: "Diff" },
            { v: "full", label: "Full file" },
          ]}
          onChange={(v) => store.setMode(v as "diff" | "full")}
        />
        <Segmented
          value={store.layout}
          disabled={store.mode === "full"}
          options={[
            { v: "inline", label: "Inline" },
            { v: "split", label: "Split" },
          ]}
          onChange={(v) => store.setLayout(v as "inline" | "split")}
        />
        <Segmented
          value={store.all ? "all" : "changed"}
          options={[
            { v: "changed", label: "Changed" },
            { v: "all", label: "All files" },
          ]}
          onChange={(v) => store.setAll(v === "all")}
        />
        <span className="mx-0.5 self-stretch w-px bg-line" />
        <RunMenu />
        <SessionPicker />
        <ReviewTray />

        <span className="flex-1" />
        <div className="flex gap-3 font-mono text-xs">
          <span className="text-add">● {counts.added} new</span>
          <span className="text-mod">● {counts.modified} changed</span>
          <span className="text-del">● {counts.deleted} deleted</span>
          {counts.renamed > 0 && <span className="text-ren">● {counts.renamed} renamed</span>}
        </div>
        <label className="flex items-center gap-1.5 text-xs text-dim">
          <input type="checkbox" checked={live} onChange={(e) => onToggleLive(e.target.checked)} />
          auto
          <span
            className={`inline-block h-2 w-2 rounded-full transition ${
              live ? "bg-add shadow-[0_0_6px_var(--color-add)]" : "bg-[#bbb]"
            }`}
          />
        </label>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => qc.invalidateQueries()}
          title="Refresh"
        >
          ↻
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setSettingsOpen(true)} title="Settings">
          ⚙
        </Button>
      </div>
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </header>
  );
}

interface SegmentedProps {
  value: string;
  options: { v: string; label: string }[];
  disabled?: boolean;
  onChange: (v: string) => void;
}

function Segmented({ value, options, disabled, onChange }: SegmentedProps) {
  return (
    <div className="inline-flex">
      {options.map((o, i) => (
        <button
          key={o.v}
          disabled={disabled}
          onClick={() => onChange(o.v)}
          className={`h-[30px] border border-line px-2.5 text-[13px] ${i > 0 ? "border-l-0" : "rounded-l-md"} ${
            i === options.length - 1 ? "rounded-r-md" : ""
          } ${value === o.v ? "bg-accent text-white" : "bg-canvas hover:bg-panel2"} ${
            disabled ? "cursor-not-allowed opacity-40" : "cursor-pointer"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
