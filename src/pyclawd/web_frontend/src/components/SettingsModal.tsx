// Settings modal (the ⚙ gear): edit the discovery roots (server-side), the diff
// tab width, and the tmux send defaults (paste-only vs paste+submit, focus window).
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "@/api";
import { Button } from "@/components/ui/button";
import { useStore } from "@/store";

export function SettingsModal({ onClose }: { onClose: () => void }) {
  const { settings, setSettings } = useStore();
  const qc = useQueryClient();
  const [roots, setRoots] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.config().then((c) => setRoots(c.roots.join("\n")));
  }, []);

  const save = async () => {
    setMsg("saving…");
    try {
      const cleaned = roots.split("\n").map((r) => r.trim()).filter(Boolean);
      await api.setConfig(cleaned);
      await qc.invalidateQueries({ queryKey: ["projects"] });
      setMsg("saved ✓");
      setTimeout(onClose, 400);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "save failed");
    }
  };

  return (
    <div
      className="fixed inset-0 z-[110] flex items-start justify-center bg-[rgba(20,24,28,0.3)] pt-[10vh]"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="w-[560px] max-w-[94vw] overflow-hidden rounded-xl border border-line bg-canvas shadow-[0_18px_54px_rgba(0,0,0,0.28)]">
        <div className="border-b border-line px-5 py-3 text-[15px] font-semibold">Settings</div>
        <div className="max-h-[60vh] overflow-auto px-5">
          <Row label="Workspace roots" hint="one per line — folders scanned for git repos">
            <textarea
              value={roots}
              onChange={(e) => setRoots(e.target.value)}
              rows={3}
              spellCheck={false}
              className="w-full resize-y rounded-md border border-line p-2 font-mono text-[13px]"
            />
          </Row>
          <Row label="Tab width" hint="how many spaces a tab renders as in diffs">
            <input
              type="number"
              min={1}
              max={8}
              value={settings.tabWidth}
              onChange={(e) =>
                setSettings({ tabWidth: Math.min(8, Math.max(1, parseInt(e.target.value) || 4)) })
              }
              className="w-[120px] rounded-md border border-line px-2.5 py-1.5 text-[13px]"
            />
          </Row>
          <Row label="Default send action" hint="what “Send → tmux” does">
            <select
              value={String(settings.sendSubmit)}
              onChange={(e) => setSettings({ sendSubmit: e.target.value === "true" })}
              className="rounded-md border border-line px-2.5 py-1.5 text-[13px]"
            >
              <option value="false">Paste only — you press Enter</option>
              <option value="true">Paste &amp; submit</option>
            </select>
          </Row>
          <label className="flex items-center gap-2 border-b border-panel2 py-3 text-[13px]">
            <input
              type="checkbox"
              checked={settings.sendFocus}
              onChange={(e) => setSettings({ sendFocus: e.target.checked })}
            />
            Focus the tmux window when sending
          </label>
        </div>
        <div className="flex items-center gap-2 border-t border-line px-5 py-3">
          <Button variant="accent" onClick={save}>
            Save
          </Button>
          <Button onClick={onClose}>Close</Button>
          <span className="text-xs text-add">{msg}</span>
        </div>
      </div>
    </div>
  );
}

function Row({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5 border-b border-panel2 py-3">
      <span className="font-semibold">
        {label}
        <small className="mt-0.5 block font-normal text-dim">{hint}</small>
      </span>
      {children}
    </label>
  );
}
