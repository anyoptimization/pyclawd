// Picks which local claude tmux pane the review tray sends to.
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useSessions } from "@/hooks";
import { useStore } from "@/store";

export function SessionPicker() {
  const { session, setSession } = useStore();
  const { data } = useSessions();
  const [open, setOpen] = useState(false);
  const sessions = data?.sessions ?? [];
  const active = sessions.find((s) => s.target === session);
  const label = active
    ? `${active.window} · ${active.project}`
    : sessions.length
      ? "select session"
      : "no tmux sessions";

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="default">
          <span>{label}</span>
          <span className="text-[10px] text-dim">▾</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent>
        {sessions.length === 0 ? (
          <div className="p-6 text-center text-dim">
            No running <code className="font-mono">claude</code> sessions in tmux.
          </div>
        ) : (
          <div className="overflow-auto">
            {sessions.map((s) => (
              <button
                key={s.target}
                onClick={() => {
                  setSession(s.target);
                  setOpen(false);
                }}
                className={`flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-panel2 ${
                  s.target === session ? "bg-[#ddf4ff]" : ""
                }`}
              >
                <span className="flex-1 font-semibold">
                  {s.window} · {s.project}
                </span>
                <span className="font-mono text-[11px] text-dim">
                  {s.active ? "● " : ""}
                  {s.name}
                </span>
              </button>
            ))}
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
