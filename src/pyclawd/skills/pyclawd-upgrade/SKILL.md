---
name: pyclawd-upgrade
description: Migrate a project after pyclawd itself was upgraded — when `pyclawd version` or `pyclawd doctor` shows the config was built on an older pyclawd. Reads `pyclawd changelog --since <config-version>`, updates `.pyclawd/config.py` for any config-model changes, re-stamps `pyclawd_version`, refreshes the bundled skills, and verifies with `pyclawd check` + `pyclawd doctor`. Use after `pip install -U pyclawd` or whenever a version-drift WARN appears.
when_to_use: `pyclawd version`/`pyclawd doctor` reports the config was built on a different pyclawd (version drift), or right after upgrading/installing a newer pyclawd. The agent-driven migration path.
---

# pyclawd-upgrade

Bring a project back in sync after **pyclawd itself** was upgraded. pyclawd is
agent-native by design: the toolkit detects drift and tells you what changed; **you
(the agent) apply the migration.** Nothing here is automatic guesswork — it is a
deterministic read-changelog → edit-config → verify loop.

## When this applies

After `pip install -U pyclawd` (or any pyclawd version change), a project's
`.pyclawd/config.py` records the pyclawd it was authored against
(`Project.pyclawd_version`). When that drifts from the installed pyclawd:

- `pyclawd version` shows `config built on X ! drift from Y`
- `pyclawd doctor` shows a **pyclawd compat** WARN

A `major.minor` bump may include breaking changes to the config model (`Project`
and the nested `*Config`s). That is what you are migrating.

## The migration loop

1. **See the drift.**
   ```bash
   pyclawd version --json     # installed pyclawd vs config_version, match: false
   ```

2. **Read exactly what changed** since the config was authored:
   ```bash
   pyclawd changelog          # defaults to --since the config's pyclawd_version
   ```
   Focus on **Changed** / **Removed** / **Added** entries that touch the config
   model (new required fields, renamed/removed `*Config` fields, changed defaults).

3. **Edit `.pyclawd/config.py`** to match the current model:
   - Add any newly required fields; rename/remove changed ones.
   - Read the installed model if unsure — `pyclawd python -c "import pyclawd, inspect; print(inspect.getsource(pyclawd.Project))"` (or read `src/pyclawd/project.py`).
   - **Re-stamp the version** to the installed pyclawd:
     ```python
     pyclawd_version="<the version pyclawd version reports>",
     ```
     Do this **last** — it is what clears the drift signal, so only stamp once the
     config actually matches the new model.

4. **Refresh the bundled skills** (they are copied into `~/.claude/skills`, so an
   upgrade does not propagate them automatically):
   ```bash
   pyclawd skills install     # auto-refreshes drifted skills; identical ones skipped
   pyclawd skills prune       # remove orphans — skills DROPPED from the new bundle
   ```
   (`pyclawd skills install --prune` does both — refresh + prune — in one step.
   `pyclawd doctor` also WARNs when orphaned skills linger in `~/.claude/skills`.)

5. **Verify green.**
   ```bash
   pyclawd version            # config now ✓ matches
   pyclawd doctor             # no pyclawd-compat / skills WARN
   pyclawd check              # format-check → lint → typecheck → descriptions → test all ✓
   ```

## Boundaries

- **Ask before** changing `.pyclawd/config.py` if the project owner is around — config
  is the public contract for how the repo is driven.
- **Don't blindly overwrite `AGENTS.md`.** If a pyclawd upgrade improved the scaff, you
  may reconcile the repo's `AGENTS.md` against the current template, but it is a
  committed, possibly hand-edited file — diff and propose, don't clobber.
- **Migrate the cause, not the symptom.** If a field was removed, remove it; don't
  silence the WARN by re-stamping the version while the config still uses the old model.

## How you know the upgrade is done

- `pyclawd version` → `config built on <new> ✓ matches`
- `pyclawd doctor` → no pyclawd-compat WARN, no stale-skills WARN
- `pyclawd check` is green

## Where to go next

| Need | Where |
|---|---|
| Onboarding an existing repo for the **first** time (not an upgrade) | **pyclawd-adopt** |
| Env looks broken after the upgrade | **pyclawd-doctor** |
| Prove the upgrade didn't change behavior | **pyclawd-golden** |
| Mental model + full doctrine | **pyclawd** (router) · `AGENTS.md` |
