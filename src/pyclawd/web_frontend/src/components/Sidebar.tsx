// The left file tree: changed files (or all files) grouped into a collapsible
// directory tree, each with its add/delete counts and a status badge.
import { useMemo, useState } from "react";

import { statusBadge, statusColor } from "@/lib/status";
import { useStore } from "@/store";
import type { FileChange } from "@/types";

interface TreeNode {
  dirs: Map<string, TreeNode>;
  files: { name: string; change: FileChange }[];
}

function buildTree(files: FileChange[]): TreeNode {
  const root: TreeNode = { dirs: new Map(), files: [] };
  for (const change of files) {
    const parts = change.path.split("/");
    let node = root;
    for (let i = 0; i < parts.length - 1; i++) {
      const dir = parts[i];
      if (!node.dirs.has(dir)) node.dirs.set(dir, { dirs: new Map(), files: [] });
      node = node.dirs.get(dir)!;
    }
    node.files.push({ name: parts[parts.length - 1], change });
  }
  return root;
}

export function Sidebar({ files }: { files: FileChange[] }) {
  const tree = useMemo(() => buildTree(files), [files]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const toggle = (path: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });

  if (files.length === 0) {
    return <div className="p-12 text-center text-dim">No changes.</div>;
  }
  return (
    <div className="py-1.5">
      <TreeLevel node={tree} prefix="" depth={0} collapsed={collapsed} onToggle={toggle} />
    </div>
  );
}

interface TreeLevelProps {
  node: TreeNode;
  prefix: string;
  depth: number;
  collapsed: Set<string>;
  onToggle: (path: string) => void;
}

function TreeLevel({ node, prefix, depth, collapsed, onToggle }: TreeLevelProps) {
  const { selected, selectFile } = useStore();
  const pad = { paddingLeft: 8 + depth * 14 };
  const dirNames = [...node.dirs.keys()].sort();

  return (
    <>
      {dirNames.map((name) => {
        const path = prefix ? `${prefix}/${name}` : name;
        const isCollapsed = collapsed.has(path);
        return (
          <div key={path}>
            <div
              style={pad}
              onClick={() => onToggle(path)}
              className="flex cursor-pointer select-none items-center gap-1.5 py-1 pr-3 hover:bg-panel"
            >
              <span className="w-3 flex-none text-[10px] text-dim">{isCollapsed ? "▸" : "▾"}</span>
              <span>{name}</span>
            </div>
            {!isCollapsed && (
              <TreeLevel
                node={node.dirs.get(name)!}
                prefix={path}
                depth={depth + 1}
                collapsed={collapsed}
                onToggle={onToggle}
              />
            )}
          </div>
        );
      })}
      {node.files.map(({ name, change }) => (
        <div
          key={change.path}
          style={pad}
          title={change.path}
          onClick={() => selectFile(change.path)}
          className={`flex cursor-pointer select-none items-center gap-1.5 py-1 pr-3 hover:bg-panel ${
            change.path === selected ? "bg-[#ddf4ff]" : ""
          }`}
        >
          <span className={`h-[9px] w-[9px] flex-none rounded-[2px] ${statusBadge(change.status)}`} />
          <span
            className={`flex-1 truncate ${statusColor(change.status)} ${
              change.status === "D" ? "line-through decoration-del/40" : ""
            }`}
          >
            {name}
          </span>
          <span className="flex-none font-mono text-[11px] text-dim">
            {change.additions > 0 && <span className="text-add">+{change.additions}</span>}
            {change.deletions > 0 && <span className="text-del"> −{change.deletions}</span>}
          </span>
        </div>
      ))}
    </>
  );
}
