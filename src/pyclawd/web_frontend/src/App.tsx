// Top-level composition: bootstraps the selected project, wires the live-refresh
// subscription, and lays out the header, file tree, and diff view.
import { useEffect, useRef, useState } from "react";

import { CommandPalette } from "@/components/CommandPalette";
import { DiffView } from "@/components/DiffView";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { useChanges, useDiff, useLiveRefresh, usePersisted, useProjects, useRefs } from "@/hooks";
import { useStore } from "@/store";
import type { DiffLayout, DiffMode } from "@/types";

export function App() {
  const store = useStore();
  const [live, setLive] = useState(true);
  const [sidebarWidth, setSidebarWidth] = usePersisted("pyclawd.web.sidebarW", 320);
  const draggingSidebar = useRef(false);
  const booted = useRef(false);

  useEffect(() => {
    const move = (e: MouseEvent) => {
      if (draggingSidebar.current) setSidebarWidth(Math.max(160, Math.min(720, e.clientX)));
    };
    const up = () => {
      if (draggingSidebar.current) {
        draggingSidebar.current = false;
        document.body.style.userSelect = "";
      }
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, [setSidebarWidth]);

  const { data: projects } = useProjects();
  const { data: refs } = useRefs(store.project);
  const { data: changes } = useChanges(store.project, store.base, store.target, store.all);
  const { data: view } = useDiff(
    store.project,
    store.base,
    store.target,
    store.selected,
    store.mode,
  );
  useLiveRefresh(store.project, store.base, store.target, live);

  // Bootstrap once projects load: restore from the URL hash if present (deep link),
  // else select the server's default project. Hash values are applied after
  // selectProject so a shared link wins over the per-project saved prefs.
  useEffect(() => {
    if (booted.current || !projects) return;
    booted.current = true;
    const h = new URLSearchParams(location.hash.slice(1));
    const hashProject = h.get("project");
    const initial =
      hashProject && projects.projects.some((p) => p.name === hashProject)
        ? hashProject
        : (projects.default ?? projects.projects[0]?.name);
    if (!initial) return;
    store.selectProject(initial);
    if (h.has("base")) store.setBase(h.get("base")!);
    if (h.has("target")) store.setTarget(h.get("target")!);
    if (h.get("mode")) store.setMode(h.get("mode") as DiffMode);
    if (h.get("layout")) store.setLayout(h.get("layout") as DiffLayout);
    if (h.get("all")) store.setAll(true);
    if (h.get("file")) store.selectFile(h.get("file"));
  }, [projects, store]);

  // Keep the URL hash in sync so the current view is a shareable deep link.
  useEffect(() => {
    if (!store.project) return;
    const p = new URLSearchParams({
      project: store.project,
      base: store.base,
      target: store.target,
      mode: store.mode,
      layout: store.layout,
    });
    if (store.all) p.set("all", "1");
    if (store.selected) p.set("file", store.selected);
    const hash = `#${p.toString()}`;
    if (location.hash !== hash) history.replaceState(null, "", hash);
  }, [store.project, store.base, store.target, store.mode, store.layout, store.all, store.selected]);

  // Apply the tab-width preference to the diff tables via a CSS variable.
  useEffect(() => {
    document.documentElement.style.setProperty("--tab", String(store.settings.tabWidth));
  }, [store.settings.tabWidth]);

  const files = changes?.files ?? [];

  return (
    <div className="flex h-full flex-col">
      <TopBar refs={refs} files={files} live={live} onToggleLive={setLive} />
      <main className="flex min-h-0 flex-1">
        <aside
          style={{ width: sidebarWidth }}
          className="flex-none overflow-auto border-r border-line"
        >
          <Sidebar files={files} />
        </aside>
        <div
          onMouseDown={(e) => {
            draggingSidebar.current = true;
            document.body.style.userSelect = "none";
            e.preventDefault();
          }}
          className="w-[5px] flex-none cursor-col-resize bg-transparent hover:bg-accent"
          title="Drag to resize"
        />
        <section className="flex-1 overflow-auto">
          {view ? (
            <DiffView view={view} />
          ) : (
            <div className="p-12 text-center text-dim">
              {store.selected ? "Loading…" : "Select a file to view its changes."}
            </div>
          )}
        </section>
      </main>
      <CommandPalette />
    </div>
  );
}
