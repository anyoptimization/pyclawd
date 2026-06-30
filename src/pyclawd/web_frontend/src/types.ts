// TypeScript mirrors of the backend's git-layer value objects (pyclawd.web.git).
// Kept in lock-step with the Python dataclasses/enums so the API contract is typed
// end to end.

/** Sentinel ref meaning the live working tree (matches WORKING_TREE in git.py). */
export const WORKING_TREE = "WORKING_TREE";

/** How a file changed between two sides — values match ChangeStatus in git.py. */
export type ChangeStatus = "A" | "M" | "D" | "R";

/** Role of a diff line — values match LineKind in git.py. */
export type LineKind = "add" | "del" | "ctx";

export interface FileChange {
  path: string;
  status: ChangeStatus | null;
  old_path: string | null;
  additions: number;
  deletions: number;
  untracked: boolean;
}

export interface DiffLine {
  kind: LineKind;
  old: number | null;
  new: number | null;
  content: string;
  /** Syntax-highlighted HTML for `content` (Pygments); null → render plain text. */
  html?: string | null;
}

export interface Hunk {
  header: string;
  lines: DiffLine[];
}

export interface FileView {
  path: string;
  status: ChangeStatus | null;
  mode: "diff" | "full";
  binary: boolean;
  unchanged: boolean;
  hunks: Hunk[];
  lines: DiffLine[];
}

export interface Commit {
  sha: string;
  subject: string;
  author: string;
  date: string;
}

export interface RefInfo {
  branches: string[];
  tags: string[];
  commits: Commit[];
  current: string;
}

/** A project row: registry entry fields merged with its live repo status. */
export interface Project {
  name: string;
  path: string;
  starred: boolean;
  discovered: boolean;
  branch: string;
  dirty: number;
  ahead: number;
  behind: number;
}

export interface ProjectsResponse {
  projects: Project[];
  default: string | null;
}

export interface ChangesResponse {
  project: string | null;
  base: string;
  target: string;
  all: boolean;
  files: FileChange[];
  token: string;
}

export interface Session {
  target: string;
  window: string;
  cwd: string;
  project: string;
  name: string;
  active: boolean;
}

/** A staged line comment, assembled into a review and sent to a tmux pane. */
export interface StagedComment {
  id: string;
  file: string;
  line: number;
  side: "old" | "new";
  code: string;
  body: string;
}

/** View mode + layout controls. */
export type DiffMode = "diff" | "full";
export type DiffLayout = "inline" | "split";
