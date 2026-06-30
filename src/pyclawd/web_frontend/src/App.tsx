// Top-level composition: bootstraps the selected project, wires the live-refresh
// subscription, and lays out the header, file tree, and diff view.
import { useEffect, useRef, useState } from "react";

import { CommandPalette } from "@/components/CommandPalette";
import { DiffView } from "@/components/DiffView";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { useChanges, useDiff, useLiveRefresh, usePersisted, useProjects, useRefs } from "@/hooks";
import { useStore } from "@/store";

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

  // Bootstrap once projects load: the active project lives in the URL *path*
  // (``/<project>``), so a reload or shared link lands back in the same project.
  // Everything else (refs, mode, layout, selected file) is restored from that
  // project's localStorage prefs by selectProject — the URL stays clean.
  useEffect(() => {
    if (booted.current || !projects) return;
    booted.current = true;
    const pathProject = decodeURIComponent(location.pathname.replace(/^\/+|\/+$/g, ""));
    const initial =
      pathProject && projects.projects.some((p) => p.name === pathProject)
        ? pathProject
        : (projects.default ?? projects.projects[0]?.name);
    if (initial) store.selectProject(initial);
  }, [projects, store]);

  // Keep the URL path mapped to the active project (clean, shareable, reload-safe).
  useEffect(() => {
    if (!store.project) return;
    const path = `/${encodeURIComponent(store.project)}`;
    if (location.pathname !== path) history.replaceState(null, "", path);
  }, [store.project]);

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
