---
name: pyclawd-doctor
description: Diagnose a pyclawd dev environment when something looks misconfigured — wrong interpreter or conda env, missing dependency, uncompiled extensions, or test-collection import errors. Runs `pyclawd doctor` and interprets the OK/WARN/FAIL report. Use when tests fail to import or collect, when imports behave oddly, or when the user asks to check/verify/health-check their setup.
when_to_use: The environment looks broken — mass import failures, "module not found", a freshly cloned or switched repo, the wrong Python is being used, or before trusting any other workflow.
---

# pyclawd-doctor

Health-check the dev environment. `pyclawd doctor` validates the interpreter, conda env, core/dev deps, build artifacts, required tool files, and git state, then exits non-zero if anything is a FAIL. The exact checks come from the project's `.pyclawd/config.py` (`DoctorConfig`).

## Commands

| Task | Command |
|---|---|
| Run the full health-check | `pyclawd doctor` |
| Confirm the detected repo root | `pyclawd root` |
| Sanity-check the interpreter | `pyclawd python -c "import sys; print(sys.executable)"` |

## Reading the report

- **FAIL** — fatal; gates every dependent workflow. Fix before running tests/docs/build.
- **WARN** — non-fatal caveat (e.g. an optional dev dep absent). Note it, proceed if unrelated.
- **OK** — passing.

## Doctrine

- When ANY workflow misbehaves (import errors, odd behavior, fresh clone), run `pyclawd doctor` FIRST — it catches the common breakages before you chase ghosts.
- Fix FAILs top-down, re-running `pyclawd doctor` after each, until it exits 0.

## Common fixes

| Symptom | Fix |
|---|---|
| Wrong env / wrong interpreter | Activate the `conda_env` named in `.pyclawd/config.py`; always run code via `pyclawd python`, never bare `python`. |
| Missing core/dev dependency | Install it into the project env (`pip install <dep>`). |
| Uncompiled / stale extensions | `pyclawd compile` (then `pyclawd clean --ext` + `pyclawd compile` if stale). |
| Missing tool file / binary | Install the named binary or restore the file the WARN/FAIL points at. |
| Mass test-collection import errors | Almost always an env problem — `pyclawd doctor`, then fix the FAILs. |

## Where to go next

| Need | Where |
|---|---|
| Env is healthy — now run the tiered tests + fix-loop | the `pyclawd` skill's testing reference (`references/tests.md`) |
| Prove behavior is unchanged after a fix | **pyclawd-golden** |
| Config built on a different pyclawd (version drift) | **pyclawd-upgrade** |
| Onboarding an existing/legacy repo | **pyclawd-adopt** |
| Mental model + full doctrine | **pyclawd** (router) · `AGENTS.md` |
