// The project switcher popover: pick a project, star/unstar, or register a new
// repo by path. Starred projects float to the top.
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "@/api";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useProjects } from "@/hooks";
import { useStore } from "@/store";

export function ProjectSwitcher() {
  const { project, selectProject } = useStore();
  const { data } = useProjects();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [addPath, setAddPath] = useState("");

  const projects = data?.projects ?? [];
  const active = projects.find((p) => p.name === project);
  const shown = projects.filter((p) => p.name.toLowerCase().includes(filter.toLowerCase()));
  const starred = shown.filter((p) => p.starred);
  const rest = shown.filter((p) => !p.starred);

  const toggleStar = async (name: string, starred: boolean) => {
    await api.star(name, !starred);
    qc.invalidateQueries({ queryKey: ["projects"] });
  };

  const remove = async (name: string) => {
    await api.removeProject(name);
    qc.invalidateQueries({ queryKey: ["projects"] });
  };

  const add = async () => {
    const path = addPath.trim();
    if (!path) return;
    try {
      const { name } = await api.addProject(path);
      await qc.invalidateQueries({ queryKey: ["projects"] });
      setAddPath("");
      setOpen(false);
      selectProject(name);
    } catch (err) {
      alert(err instanceof Error ? err.message : "add failed");
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="default" className="font-semibold">
          <span>{active ? (active.starred ? "★ " : "") + active.name : project ?? "(no project)"}</span>
          {active && (
            <span className="font-mono text-[11.5px] text-dim">
              ⎇ {active.branch}
              {active.dirty > 0 ? ` ●${active.dirty}` : ""}
            </span>
          )}
          <span className="text-[10px] text-dim">▾</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent>
        <input
          autoFocus
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="filter projects…"
          className="m-2 rounded-md border border-line px-2.5 py-1.5 text-[13px] outline-none"
        />
        <div className="overflow-auto">
          {starred.length > 0 && <Group title="★ Starred" />}
          {starred.map((p) => (
            <ProjectRow
              key={p.name}
              name={p.name}
              branch={p.branch}
              dirty={p.dirty}
              starred={p.starred}
              selected={p.name === project}
              onPick={() => {
                selectProject(p.name);
                setOpen(false);
              }}
              onStar={() => toggleStar(p.name, p.starred)}
              discovered={p.discovered}
              onRemove={() => remove(p.name)}
            />
          ))}
          <Group title={starred.length ? "All projects" : "Projects"} />
          {rest.map((p) => (
            <ProjectRow
              key={p.name}
              name={p.name}
              branch={p.branch}
              dirty={p.dirty}
              starred={p.starred}
              selected={p.name === project}
              onPick={() => {
                selectProject(p.name);
                setOpen(false);
              }}
              onStar={() => toggleStar(p.name, p.starred)}
              discovered={p.discovered}
              onRemove={() => remove(p.name)}
            />
          ))}
        </div>
        <div className="flex gap-1.5 border-t border-line p-2">
          <input
            value={addPath}
            onChange={(e) => setAddPath(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder="/path/to/repo to add…"
            className="flex-1 rounded-md border border-line px-2.5 py-1.5 text-[13px] outline-none"
          />
          <Button onClick={add}>Add</Button>
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

interface ProjectRowProps {
  name: string;
  branch: string;
  dirty: number;
  starred: boolean;
  selected: boolean;
  discovered: boolean;
  onPick: () => void;
  onStar: () => void;
  onRemove: () => void;
}

function ProjectRow({
  name,
  branch,
  dirty,
  starred,
  selected,
  discovered,
  onPick,
  onStar,
  onRemove,
}: ProjectRowProps) {
  return (
    <div
      className={`group flex items-center gap-2 px-3 py-1.5 hover:bg-panel2 ${selected ? "bg-[#ddf4ff]" : ""}`}
    >
      <button
        onClick={(e) => {
          e.stopPropagation();
          onStar();
        }}
        className="w-3.5 flex-none text-center text-star"
        title={starred ? "unstar" : "star"}
      >
        {starred ? "★" : "☆"}
      </button>
      <button onClick={onPick} className="flex flex-1 items-center gap-2 overflow-hidden text-left">
        <span className="flex-1 truncate font-semibold">{name}</span>
        <span className="flex-none font-mono text-[11px] text-dim">
          ⎇ {branch}
          {dirty > 0 ? ` ●${dirty}` : ""}
        </span>
      </button>
      {!discovered && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="flex-none text-base leading-none text-dim opacity-0 group-hover:opacity-100 hover:text-del"
          title="unregister this project"
        >
          ×
        </button>
      )}
    </div>
  );
}
