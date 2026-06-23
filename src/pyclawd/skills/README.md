# pyclawd skills

These skills ship with **pyclawd** as agent-facing slash commands. Each is a directory `<name>/SKILL.md` (the umbrella `pyclawd`, plus the focused `pyclawd-<name>`) with YAML frontmatter (`name`, `description`, `when_to_use`) plus a short body. They are thin wrappers over the real CLI — the logic lives in `pyclawd`, the skills just say *what to run and when*.

| Skill | Purpose |
|---|---|
| `pyclawd` | **Start here** — the mental model and the full command surface; umbrella over the focused skills. |
| `pyclawd-doctor` | Health-check the dev env; interpret FAIL/WARN; common fixes. |
| `pyclawd-tests` | Tiered tests + the `--lf` fix-loop and failure taxonomy. |
| `pyclawd-quality` | Lint / format / typecheck and the aggregate `pyclawd check` gate. |
| `pyclawd-docs` | The docs execute-vs-render split, caching, and debug loop (when docs are configured). |

All skills are generic: nothing here is project-specific — those details live in each project's `.pyclawd/config.py`.

These skills are **packaged with pyclawd** (they ship inside the wheel under `pyclawd/skills/`) and are discovered at runtime via `importlib.resources.files("pyclawd.skills")` — so they work the same whether pyclawd runs from a source checkout or an installed wheel. The repo-root `skills/` is a symlink to this directory, kept only for visibility (single source of truth).

## Installing into a project

Skills are discovered by your agent under `.claude/skills/`. The supported way to land them is the built-in command:

```bash
pyclawd skills list                  # show the bundled skills + descriptions
pyclawd skills install               # copy them into <project-root>/.claude/skills/
pyclawd skills install --target DIR  # …into a custom directory
pyclawd skills install --symlink     # symlink instead of copy (track pyclawd updates)
pyclawd skills install --force       # overwrite existing skill dirs
```

`pyclawd new <name>` and `pyclawd new` (adopt mode) install these skills automatically, so a project is agent-ready from commit zero. The directory name (`pyclawd-doctor`, …) becomes the slash command.
