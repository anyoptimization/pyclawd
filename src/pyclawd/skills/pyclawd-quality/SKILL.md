---
name: pyclawd-quality
description: Run pyclawd's code-quality toolchain — lint, format, typecheck — and the aggregate `pyclawd check` gate that runs format-check → lint → typecheck → test fail-fast. Covers when to use `--fix` vs `--check` and the daily quality loop. Use when cleaning up code, before a commit or PR, or when asked "is this code good / ready".
when_to_use: Tidying or finishing code, before committing/opening a PR, or any "is this ready / is this clean" check. `pyclawd check` is the canonical "am I done" gate.
---

# pyclawd-quality

Lint / format / typecheck plus one aggregate gate. Every tool's argv comes from the project's `.pyclawd/config.py` (`QualityConfig`) — nothing about ruff/mypy is hardcoded. If quality is unconfigured, the affected command self-reports and exits 2 instead of crashing.

## Commands

| Task | Command |
|---|---|
| Lint (report only) | `pyclawd lint` |
| Lint and autofix | `pyclawd lint --fix` |
| Format files in place | `pyclawd format` |
| Format check (no writes, CI-style) | `pyclawd format --check` |
| Type-check | `pyclawd typecheck` |
| Aggregate gate (the "done" check) | `pyclawd check` |

## The daily loop

1. `pyclawd format` — normalize formatting.
2. `pyclawd lint --fix` — autofix what's mechanical; hand-fix the rest.
3. `pyclawd typecheck` — resolve type errors.
4. `pyclawd test run` — confirm behavior is green.

…or just run `pyclawd check`, which does **format-check → lint → typecheck → test** in order, **fail-fast**, and prints a per-step ✓/✗ summary plus a verdict. It's the CI-parity gate and the canonical "am I done?" command.

## `--fix` / `--check` doctrine

- Use mutating verbs (`format`, `lint --fix`) while iterating locally.
- Use non-mutating verbs (`format --check`, plain `lint`) as gates — they're what `pyclawd check` and CI run; they never rewrite files.
- Always finish with a clean `pyclawd check` before declaring work done or opening a PR.
