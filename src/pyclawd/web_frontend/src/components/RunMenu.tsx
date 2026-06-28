// The "Run ▾" control: a menu of pyclawd verbs (check/test/golden/…) that each
// open a streaming RunPanel. Disabled when pyclawd isn't installed or the project
// has no .pyclawd/config.py.
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { RunPanel } from "@/components/RunPanel";
import { useRunAvailable } from "@/hooks";
import { useStore } from "@/store";

/** The verbs offered, with friendly labels. Keys match the backend allowlist. */
const VERBS: { verb: string; label: string }[] = [
  { verb: "check", label: "check — full quality gate" },
  { verb: "test", label: "test — default tier" },
  { verb: "test-fast", label: "test fast — smoke (<30s)" },
  { verb: "golden", label: "golden — behavior oracle" },
  { verb: "lint", label: "lint" },
  { verb: "typecheck", label: "typecheck" },
  { verb: "format-check", label: "format --check" },
  { verb: "doctor", label: "doctor — env health" },
];

export function RunMenu() {
  const { project } = useStore();
  const { data } = useRunAvailable(project);
  const [open, setOpen] = useState(false);
  const [run, setRun] = useState<string | null>(null);

  const ready = !!data?.pyclawd && !!data?.configured;
  const why = !data?.pyclawd
    ? "the 'pyclawd' CLI is not on PATH"
    : !data?.configured
      ? "this project has no .pyclawd/config.py"
      : "Run a pyclawd verb in this project";

  return (
    <>
      {run !== null && project && (
        <RunPanel project={project} verb={run} onClose={() => setRun(null)} />
      )}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button variant="default" disabled={!ready} title={why}>
            ⚙ Run<span className="text-[10px] text-dim">▾</span>
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[300px]">
          <div className="overflow-auto py-1">
            {VERBS.map((v) => (
              <button
                key={v.verb}
                onClick={() => {
                  setRun(v.verb);
                  setOpen(false);
                }}
                className="flex w-full items-center px-3 py-1.5 text-left font-mono text-[12px] hover:bg-panel2"
              >
                {v.label}
              </button>
            ))}
          </div>
        </PopoverContent>
      </Popover>
    </>
  );
}
