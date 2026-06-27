# pyclawd skills

These skills ship with **pyclawd** as agent-facing slash commands. Each is a
directory `<name>/SKILL.md` with YAML frontmatter (`name`, `description`,
`when_to_use`) plus a short body. They are thin wrappers over the real CLI — the
logic lives in `pyclawd`, the skills just say *what to run and when*.

The tree is **one router + four standalone skills**:

| Skill | Purpose |
|---|---|
| `pyclawd` | **Start here** — the router: a lean mental-model TL;DR, an index of on-demand `references/*.md` doctrine files, and pointers to the standalone skills and `AGENTS.md`. |
| `pyclawd-adopt` | Adopt pyclawd into an existing/legacy repo — bootstrap the config with `pyclawd new` (adopt mode), then drive a red codebase to a green `pyclawd check` with zero behavior regression (curate the gate, pick the docstring convention, lay golden baselines first, fix in small verified batches). The first-time-onboarding counterpart to `pyclawd-upgrade`. |
| `pyclawd-golden` | Prove behavior *unchanged* across a refactor/migration with the golden behavior-regression oracle. |
| `pyclawd-doctor` | Diagnose a broken dev env; interpret `pyclawd doctor`'s FAIL/WARN; common fixes. |
| `pyclawd-upgrade` | Migrate a project's `.pyclawd/config.py` *after* pyclawd itself was upgraded (config drift) — the version-bump counterpart to `pyclawd-adopt`'s first-time onboarding. |

## The `pyclawd` router and its references

The `pyclawd` skill uses **progressive disclosure**: a lean `SKILL.md` (loaded on
trigger) that routes to deeper `references/*.md` files (plain markdown, no
frontmatter — not skills themselves, zero token cost until opened):

| Reference | Doctrine |
|---|---|
| `references/mental-model.md` | What pyclawd is, config-as-truth, exit codes, agent-vs-human rules, the code-map / one-line-description gate, "how you know you're done". |
| `references/tests.md` | Test tiers, marker rules, the fix-loop, the failure taxonomy. |
| `references/quality.md` | The `pyclawd check` gate, ruff/mypy, Google-style docstrings, single-file scoping + `--changed`/`--json`. |
| `references/docs.md` | The docs execute-vs-render split, caching, and debug loop (when docs are configured). |
| `references/packaging.md` | hatchling + `src/` layout, and the build/dist/clean verbs driven by `BuildConfig`. |

The focused tests / quality / docs skills that previously existed have been folded
into those reference files — same knowledge, fewer always-loaded descriptions. The
repo-root `AGENTS.md` remains the always-in-context command contract; the skills
carry the doctrine behind it.

All skills are generic: nothing here is project-specific — those details live in
each project's `.pyclawd/config.py`.

These skills are **packaged with pyclawd** (they ship inside the wheel under
`pyclawd/skills/`) and are discovered at runtime via
`importlib.resources.files("pyclawd.skills")` — so they work the same whether
pyclawd runs from a source checkout or an installed wheel. The repo-root `skills/`
is a symlink to this directory, kept only for visibility (single source of truth).

## Installing into a project

Skills are discovered by your agent under `.claude/skills/`. The supported way to
land them is the built-in command:

```bash
pyclawd skills list                  # show the bundled skills + descriptions
pyclawd skills install               # copy them into ~/.claude/skills/ (user scope, default)
pyclawd skills install --target DIR  # …into a custom directory (e.g. a project's .claude/skills/)
pyclawd skills install --symlink     # symlink instead of copy (track pyclawd updates)
pyclawd skills install --force       # overwrite existing skill dirs
pyclawd skills install --prune       # also remove orphans (skills dropped from the bundle)
pyclawd skills prune                 # remove orphans only (`--dry-run` to preview)
```

These skills are **generic** — nothing in them is project-specific — so by default
they install to **user scope** (`~/.claude/skills/`), shared across every pyclawd
project rather than vendored and committed into each repo. Use `--target` to
install into a specific project's `.claude/skills/` if you prefer.

`pyclawd new <name>` and `pyclawd new` (adopt mode) install these skills
automatically (user scope), so a project is agent-ready from commit zero. The
directory name (`pyclawd-doctor`, …) becomes the slash command.
