---
name: pyclawd
description: Start-here overview AND the doctrine index for working in a pyclawd project — the router over the focused references and the standalone golden/doctor/upgrade/adopt skills. pyclawd is a config-driven dev-task CLI where one file (.pyclawd/config.py) describes the project and `pyclawd <verb>` is the single contract for every task (run code, test, lint/format/typecheck, docs, health-check). Read this to orient, understand the mental model, or pick which deep reference to open. It routes; it does not duplicate AGENTS.md's command tables or the situational golden/doctor/upgrade/adopt skills.
when_to_use: Orienting in a pyclawd repo, understanding the mental model, or deciding which doctrine reference (mental-model / tests / quality / docs / packaging) or standalone skill to consult before starting work. The router, not a magnet for every situation.
---

# pyclawd — orient + doctrine index

pyclawd is **a config-driven dev-task CLI for Python projects**. One file —
`.pyclawd/config.py` — describes the project; `pyclawd <verb>` is the single stable
contract for every task. Humans and AI agents drive the project the same way.

Two ideas carry everything:

- **The CLI verbs are the contract.** `pyclawd test`, `pyclawd check`,
  `pyclawd python`, … keep the same shape across every project.
- **The tools are the opinion.** *Which* linter / type checker / test runner / build
  backend a verb runs is named in `.pyclawd/config.py` — swap a tool by editing one
  field; the verb stays identical.

**Two non-negotiables to remember now:** always run Python via `pyclawd python`
(never bare `python`); and `.pyclawd/config.py` (or `pyclawd config`) is the source
of truth for how *this* project is wired — read it before assuming.

> **This skill routes. It does not restate.** `AGENTS.md` (always in your context)
> owns the **command tables and operational contract** — *what to run*. The
> `references/*.md` below own the **doctrine** — *why and how*. Read AGENTS.md for
> exact commands; open a reference for the reasoning behind a verb.

## References — open on demand

Each is a plain-markdown deep-dive loaded only when you open it (zero cost until
then). Open the one that matches your task:

| Reference | What's in it | Open when |
|---|---|---|
| [references/mental-model.md](references/mental-model.md) | The full mental model + agent doctrine: CLI-is-contract, exit codes, config-as-truth (+ env knobs, uncommitted config), agent-vs-human rules, the code map / one-line-description gate, "how you know you're done". | Orienting, explaining what pyclawd is, or any "what are the rules" question. |
| [references/tests.md](references/tests.md) | Test tiers (fast/run/all), marker rules (never mark a test `fast`; slow/integration/golden), the fix-loop, and the failure taxonomy. | Running tests, a test fails, adding/changing tests or markers. |
| [references/quality.md](references/quality.md) | `pyclawd check` (proves *clean*, not *unchanged*), the format→lint→typecheck→descriptions→test sequence, ruff/mypy roles, Google-style docstrings, single-file scoping + `--changed`/`--json`/`--fix`/`--skip`/`--log`. | Cleaning up code, before a commit/PR, "is this ready", parallel per-file checks. |
| [references/docs.md](references/docs.md) | Execute-vs-render split, notebook caching, the runner contract, the doc-page debug loop. **Gated on `DocsConfig` — often N/A.** | Building docs or a doc page fails — and the project configures docs. |
| [references/packaging.md](references/packaging.md) | hatchling + `src/` layout opinion, and the build/dist/clean verbs driven by `BuildConfig` (`pyclawd clean --ext` is destructive). | Packaging, building wheels/extensions, or cleaning artifacts. |

## Where to go next — standalone skills

These are separate skills with their own sharp situational triggers. Reach for
them directly when the situation matches:

| Skill | Use it to | Trigger |
|---|---|---|
| **pyclawd-golden** | Prove behavior is **unchanged** across a refactor/migration (tag a test `@pytest.mark.golden` + `return` a value vs a committed baseline). The complement to quality: quality proves *clean*, golden proves *unchanged*. | "did this change any numbers?", refactoring, verifying a fleet of edits. |
| **pyclawd-doctor** | Diagnose a **broken env** — runs `pyclawd doctor`, interprets OK/WARN/FAIL. | Mass import/collection errors, wrong interpreter, fresh clone, "module not found". |
| **pyclawd-upgrade** | Migrate the project's `.pyclawd/config.py` after **pyclawd itself was upgraded** (config version drift). | `pyclawd version`/`doctor` reports config built on a different pyclawd; right after `pip install -U pyclawd`. |
| **pyclawd-adopt** | Onboard an **existing/legacy repo** to pyclawd — bootstrap the config, then drive a red codebase to a green `pyclawd check` with zero behavior regression. The first-time-onboarding counterpart to pyclawd-upgrade. | "adopt pyclawd here", "get this existing repo ready", "make this red codebase pass check". |

## The command contract

For the exact verbs, flags, tiers, and boundaries, the repo-root **`AGENTS.md`** is
the operational contract (always in your context), and **`pyclawd config`** shows
what each verb resolves to *for this project*. This skill deliberately keeps no
command table of its own so it can't drift from those.
