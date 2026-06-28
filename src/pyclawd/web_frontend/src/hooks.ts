// React Query hooks over the REST API, plus the SSE live-refresh subscription.
// Server state lives here; UI state lives in the store (store.tsx).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useState } from "react";

import { api } from "@/api";

/** A piece of state backed by localStorage — for layout prefs like panel sizes. */
export function usePersisted<T>(key: string, initial: T): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw !== null ? (JSON.parse(raw) as T) : initial;
    } catch {
      return initial;
    }
  });
  const set = useCallback(
    (next: T) => {
      setValue(next);
      try {
        localStorage.setItem(key, JSON.stringify(next));
      } catch {
        /* ignore quota/availability errors */
      }
    },
    [key],
  );
  return [value, set];
}

export function useProjects() {
  return useQuery({ queryKey: ["projects"], queryFn: api.projects });
}

export function useRefs(project: string | null) {
  return useQuery({
    queryKey: ["refs", project],
    queryFn: () => api.refs(project!),
    enabled: !!project,
  });
}

export function useChanges(
  project: string | null,
  base: string,
  target: string,
  all: boolean,
) {
  return useQuery({
    queryKey: ["changes", project, base, target, all],
    queryFn: () => api.changes(project!, base, target, all),
    enabled: !!project,
  });
}

export function useDiff(
  project: string | null,
  base: string,
  target: string,
  path: string | null,
  mode: string,
) {
  return useQuery({
    queryKey: ["diff", project, base, target, path, mode],
    queryFn: () => api.diff(project!, base, target, path!, mode),
    enabled: !!project && !!path,
  });
}

export function useSessions() {
  return useQuery({ queryKey: ["sessions"], queryFn: api.sessions });
}

export function useFiles(project: string | null) {
  return useQuery({
    queryKey: ["files", project],
    queryFn: () => api.files(project!),
    enabled: !!project,
  });
}

export function useAgentAvailable() {
  return useQuery({ queryKey: ["agent-available"], queryFn: api.agentAvailable });
}

export function useRunAvailable(project: string | null) {
  return useQuery({
    queryKey: ["run-available", project],
    queryFn: () => api.runAvailable(project!),
    enabled: !!project,
  });
}

/**
 * Subscribe to the server's SSE stream for the active comparison and invalidate the
 * changes/diff queries whenever the state token moves. Replaces interval polling:
 * the backend pushes only on real filesystem activity, and the content-aware token
 * fires even for repeated edits of one already-modified file.
 */
export function useLiveRefresh(
  project: string | null,
  base: string,
  target: string,
  enabled: boolean,
) {
  const qc = useQueryClient();
  useEffect(() => {
    if (!project || !enabled) return;
    const params = new URLSearchParams({ project, base, target });
    const es = new EventSource(`/api/events?${params.toString()}`);
    let last: string | null = null;
    es.onmessage = (ev) => {
      const { token } = JSON.parse(ev.data) as { token: string };
      if (last !== null && token !== last) {
        qc.invalidateQueries({ queryKey: ["changes", project] });
        qc.invalidateQueries({ queryKey: ["diff", project] });
        qc.invalidateQueries({ queryKey: ["projects"] });
      }
      last = token;
    };
    return () => es.close();
  }, [project, base, target, enabled, qc]);
}
