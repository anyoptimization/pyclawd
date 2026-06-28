// Client UI state: the active project, the two comparison sides, view controls,
// the selected file, the tmux target, and staged review comments. Server data is
// React Query's job (hooks.ts); this is everything that is purely local, persisted
// to localStorage so a reload restores where you were — per project.
import { createContext, useContext, useMemo, useReducer, type ReactNode } from "react";

import type { DiffLayout, DiffMode, StagedComment } from "@/types";
import { WORKING_TREE } from "@/types";

const STORAGE_KEY = "pyclawd.web";

interface PerProject {
  base: string;
  target: string;
  mode: DiffMode;
  layout: DiffLayout;
  all: boolean;
}

interface Persisted {
  project: string | null;
  session: string | null;
  pp: Record<string, PerProject>;
  staged: Record<string, StagedComment[]>;
  settings: Settings;
}

/** Global (not per-project) preferences edited in the settings panel. */
export interface Settings {
  tabWidth: number;
  sendSubmit: boolean;
  sendFocus: boolean;
}

const DEFAULTS: PerProject = {
  base: "HEAD",
  target: WORKING_TREE,
  mode: "diff",
  layout: "inline",
  all: false,
};

const SETTINGS_DEFAULTS: Settings = { tabWidth: 4, sendSubmit: false, sendFocus: false };

function load(): Persisted {
  const base: Persisted = { project: null, session: null, pp: {}, staged: {}, settings: SETTINGS_DEFAULTS };
  try {
    const saved = JSON.parse(localStorage[STORAGE_KEY] ?? "{}");
    return { ...base, ...saved, settings: { ...SETTINGS_DEFAULTS, ...(saved.settings ?? {}) } };
  } catch {
    return base;
  }
}

interface State extends PerProject {
  project: string | null;
  selected: string | null;
  session: string | null;
  staged: StagedComment[];
  settings: Settings;
}

type Action =
  | { type: "selectProject"; name: string }
  | { type: "setBase"; value: string }
  | { type: "setTarget"; value: string }
  | { type: "setMode"; value: DiffMode }
  | { type: "setLayout"; value: DiffLayout }
  | { type: "setAll"; value: boolean }
  | { type: "selectFile"; path: string | null }
  | { type: "setSession"; target: string | null }
  | { type: "stage"; comment: StagedComment }
  | { type: "unstage"; id: string }
  | { type: "clearStaged" }
  | { type: "setSettings"; value: Partial<Settings> };

function persist(state: State): void {
  const prev = load();
  const next: Persisted = {
    project: state.project,
    session: state.session,
    settings: state.settings,
    pp: state.project
      ? {
          ...prev.pp,
          [state.project]: {
            base: state.base,
            target: state.target,
            mode: state.mode,
            layout: state.layout,
            all: state.all,
          },
        }
      : prev.pp,
    staged: state.project ? { ...prev.staged, [state.project]: state.staged } : prev.staged,
  };
  localStorage[STORAGE_KEY] = JSON.stringify(next);
}

function reducer(state: State, action: Action): State {
  let next: State;
  switch (action.type) {
    case "selectProject": {
      const saved = load();
      const pp = saved.pp[action.name] ?? DEFAULTS;
      next = {
        ...state,
        ...pp,
        project: action.name,
        selected: null,
        staged: saved.staged[action.name] ?? [],
      };
      break;
    }
    case "setBase":
      next = { ...state, base: action.value };
      break;
    case "setTarget":
      next = { ...state, target: action.value };
      break;
    case "setMode":
      next = { ...state, mode: action.value };
      break;
    case "setLayout":
      next = { ...state, layout: action.value };
      break;
    case "setAll":
      next = { ...state, all: action.value };
      break;
    case "selectFile":
      next = { ...state, selected: action.path };
      break;
    case "setSession":
      next = { ...state, session: action.target };
      break;
    case "stage":
      next = { ...state, staged: [...state.staged, action.comment] };
      break;
    case "unstage":
      next = { ...state, staged: state.staged.filter((c) => c.id !== action.id) };
      break;
    case "clearStaged":
      next = { ...state, staged: [] };
      break;
    case "setSettings":
      next = { ...state, settings: { ...state.settings, ...action.value } };
      break;
  }
  persist(next);
  return next;
}

function initialState(): State {
  const saved = load();
  return {
    ...DEFAULTS,
    project: null,
    selected: null,
    session: saved.session,
    staged: [],
    settings: saved.settings,
  };
}

interface Store extends State {
  selectProject: (name: string) => void;
  setBase: (value: string) => void;
  setTarget: (value: string) => void;
  setMode: (value: DiffMode) => void;
  setLayout: (value: DiffLayout) => void;
  setAll: (value: boolean) => void;
  selectFile: (path: string | null) => void;
  setSession: (target: string | null) => void;
  stage: (comment: StagedComment) => void;
  unstage: (id: string) => void;
  clearStaged: () => void;
  setSettings: (value: Partial<Settings>) => void;
}

const StoreContext = createContext<Store | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, initialState);
  const store = useMemo<Store>(
    () => ({
      ...state,
      selectProject: (name) => dispatch({ type: "selectProject", name }),
      setBase: (value) => dispatch({ type: "setBase", value }),
      setTarget: (value) => dispatch({ type: "setTarget", value }),
      setMode: (value) => dispatch({ type: "setMode", value }),
      setLayout: (value) => dispatch({ type: "setLayout", value }),
      setAll: (value) => dispatch({ type: "setAll", value }),
      selectFile: (path) => dispatch({ type: "selectFile", path }),
      setSession: (target) => dispatch({ type: "setSession", target }),
      stage: (comment) => dispatch({ type: "stage", comment }),
      unstage: (id) => dispatch({ type: "unstage", id }),
      clearStaged: () => dispatch({ type: "clearStaged" }),
      setSettings: (value) => dispatch({ type: "setSettings", value }),
    }),
    [state],
  );
  return <StoreContext.Provider value={store}>{children}</StoreContext.Provider>;
}

/** Access the app store; must be used under a StoreProvider. */
export function useStore(): Store {
  const store = useContext(StoreContext);
  if (!store) throw new Error("useStore must be used within StoreProvider");
  return store;
}

/** The default initial per-project prefs (for the initial selection bootstrap). */
export { DEFAULTS };
