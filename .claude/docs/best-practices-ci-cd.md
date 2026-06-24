# Python Best Practices: CI/CD & Dev Workflow

**Phase 4 — Verify.** Cross-checking key falsifiable claims across sources before synthesis:

- 8x speedup claim for uv vs pip — confirmed by Real Python benchmark cited in 3 independent articles (2.6s vs 21.4s for JupyterLab)
- `uv cache prune --ci` retains source-built wheels, drops pre-built ones — confirmed in uv official docs
- Dependabot does not support uv.lock natively — confirmed (only pip/Poetry/pipenv)
- `relative_files = true` required in coverage config for CI — confirmed in danielnouri.org and pydevtools
- 80% threshold as practical baseline — consistent across pydevtools and pytest-cov guides; not an authoritative standard, context-dependent
- semantic-release requires bypass actor (GitHub App) for protected branches — confirmed gonzalohirsch.com

All key claims verified. **Phase 5 — Synthesis.**

---

# Python CI/CD Best Practices 2024-2026

A multi-source synthesis covering GitHub Actions, pre-commit, test tiers, coverage, branch protection, dependency updates, release automation, and toolchain selection.

---

## 1. GitHub Actions: Matrix Testing

The canonical pattern for 2025 tests across the Python versions your project supports. Prefer `fail-fast: false` so a failure on 3.11 does not cancel the 3.13 job — you want to see the full picture.

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    name: Test (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false        # see ALL version failures, not just the first
      matrix:
        python-version: ["3.10", "3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v8.1.0
        with:
          python-version: ${{ matrix.python-version }}
          enable-cache: true           # built-in uv cache (see §9)

      - run: uv sync --locked --all-extras --dev
        # --locked fails the job if uv.lock is out of date

      - run: uv run pytest tests/ -m "not slow" -n auto
```

For cross-platform testing, add `os` to the matrix and use `exclude:` to skip unsupported combinations:

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
    python-version: ["3.11", "3.13"]
  exclude:
    - os: windows-latest
      python-version: "3.11"
```

**Source:** [GitHub Docs — Building and testing Python](https://docs.github.com/en/actions/guides/building-and-testing-python), [pydevtools — GitHub Actions with uv](https://pydevtools.com/handbook/tutorial/setting-up-github-actions-with-uv/)

---

## 2. uv vs pip vs conda in CI

### Speed

uv is the dominant choice for pure-Python projects in 2025. Real Python benchmarks show JupyterLab installs in 2.6 s with uv vs 21.4 s with pip (8x). With a warm cache, install time approaches zero — uv validates the existing `.venv` via hard-links rather than re-downloading.

| Tool | Cold install | Warm cache | Lockfile | Cross-platform lock |
|---|---|---|---|---|
| **uv** | 2–5 s | ~0 s | `uv.lock` (built-in) | Yes |
| **pip** | 10–60 s | 5–15 s | `requirements.txt` (via pip-compile) | No |
| **conda** | 30–120 s | 10–30 s | `conda-lock` (third-party) | Per-platform |

### Reproducibility

uv generates a `uv.lock` that captures every transitive dependency exactly. Pass `--locked` in CI so the job fails if someone forgot to commit an updated lockfile. This eliminates the "works locally, fails in CI" class of bugs.

pip with a bare `requirements.txt` (unpinned) is not reproducible. Pin with `pip-compile` (from `pip-tools`) and commit the compiled `requirements.txt`. Conda's `environment.yml` is a spec, not a lockfile — use [`conda-lock`](https://conda.github.io/conda-lock/) for real reproducibility.

### When NOT to use uv

- **C/Fortran/CUDA system packages:** conda is still the right tool for CUDA, cuDNN, ffmpeg, and HDF5. uv cannot manage non-Python system dependencies.
- **Air-gapped networks:** uv's offline mode is incomplete as of mid-2025.
- **Legacy Docker images:** if your base image already has pip and you're installing 3 packages, adding uv may not be worth the extra layer.
- **Dependabot users:** Dependabot does not yet recognize `uv.lock` — use Renovate if you need automated lockfile updates (see §7).

**Sources:** [uv Complete Guide (pydevtools)](https://pydevtools.com/handbook/explanation/uv-complete-guide/), [uv in 2026 — heyuan110](https://www.heyuan110.com/posts/python/2026-04-10-uv-python-package-manager/), [Real Python — uv vs pip](https://realpython.com/uv-vs-pip/)

---

## 3. Caching Strategies

### uv (recommended)

The `astral-sh/setup-uv` action's `enable-cache: true` handles everything automatically. Under the hood it:

1. Caches `~/.cache/uv` (PyPI wheels and tarballs)
2. Caches `~/.local/share/uv` (registry metadata — omitting this forces reinstalls even on cache hit)
3. Uses `hashFiles('uv.lock')` as the cache key
4. Runs `uv cache prune --ci` before saving (removes pre-built wheels and extracted sdists, keeps source-built wheels — keeps cache lean)

```yaml
- uses: astral-sh/setup-uv@v8.1.0
  with:
    python-version: "3.13"
    enable-cache: true
    # Cache invalidates automatically when uv.lock changes
```

For a single shared cache across all PRs (preventing fragmentation), build the cache on `main` only and restore it on PR branches:

```yaml
# Cache key strategy
key: uv-${{ runner.os }}-${{ hashFiles('uv.lock') }}
restore-keys: |
  uv-${{ runner.os }}-
```

**`uv cache prune --ci` explained:** It removes pre-built wheels and unzipped source distributions (large, re-downloadable), but retains any wheels built from source (expensive to rebuild). Use it before the `cache/save` step, never before `uv sync`.

### pip (legacy projects)

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
    cache: "pip"
    cache-dependency-path: "requirements*.txt"
```

### conda

```yaml
- uses: conda-incubator/setup-miniconda@v3
  with:
    python-version: "3.12"
    use-mamba: true          # mamba is significantly faster than conda resolver
    environment-file: environment.yml
    activate-environment: myenv
```

### When caching HURTS

| Scenario | Why it hurts |
|---|---|
| Tiny dependency set (<5 packages) | S3 round-trip (30 s) > cold install (5 s with uv) |
| `uv.lock` changes every commit | Cache always misses; restore overhead is pure waste |
| PyPy installs | Often faster cold than via cache restore |
| Self-hosted runners with full disk | Unbounded cache growth; prune with `uv cache clean` in post-job step |
| Stale caches causing mysterious failures | Force-clear with `actions/cache`'s eviction or change cache key prefix |

**Sources:** [uv Caching Concepts](https://docs.astral.sh/uv/concepts/cache/), [Optimizing uv in GitHub Actions](https://szeyusim.medium.com/optimizing-uv-in-github-actions-one-global-cache-to-rule-them-all-9c64b42aee7f), [uv GitHub Actions docs](https://docs.astral.sh/uv/guides/integration/github/)

---

## 4. Pre-commit Hooks

### Recommended hook set (ordered)

Order matters: fixers before checkers, fast before slow.

```yaml
# .pre-commit-config.yaml
repos:
  # 1. Universal file hygiene (fast, order-independent)
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-added-large-files
      - id: check-merge-conflict
      - id: debug-statements        # catches leftover breakpoint() calls

  # 2. Secret detection (fast, critical)
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.27.2
    hooks:
      - id: gitleaks

  # 3. Ruff: format first, then lint (fast; replaces black, isort, flake8, bandit)
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.11.0
    hooks:
      - id: ruff-format            # format first
      - id: ruff                   # lint second (can auto-fix imports etc.)
        args: [--fix]

  # 4. pyproject.toml validation
  - repo: https://github.com/abravalheri/validate-pyproject
    rev: v0.24
    hooks:
      - id: validate-pyproject

  # 5. Type checking — OPTIONAL, slow; consider moving to CI-only
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.16.0
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
        stages: [manual]           # only runs via `pre-commit run --hook-stage manual`
```

### CI vs local strategy

The key principle: **local hooks give instant feedback; CI is the safety net.**

- Run the full hook set in CI (`pre-commit run --all-files`) to catch contributors who bypassed with `--no-verify`.
- Slow hooks (mypy, full test suite) should use `stages: [manual]` locally but run in their own dedicated CI job — not as pre-commit in CI.
- Never skip pre-commit in CI. The overhead is minimal (seconds) and the catch rate is high.

```yaml
# In .github/workflows/ci.yml
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v8.1.0
      - run: uvx pre-commit run --all-files
```

**Sources:** [Pre-commit Hooks Guide 2025 (Medium)](https://gatlenculp.medium.com/effortless-code-quality-the-ultimate-pre-commit-hooks-guide-for-2025-57ca501d9835), [pydevtools — set up pre-commit](https://pydevtools.com/handbook/how-to/how-to-set-up-pre-commit-hooks-for-a-python-project/)

---

## 5. Test Tiers: Fast First, Fail Fast, Slow on Main

### Marker registration

```toml
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "slow: tests taking >1s (deselected by default)",
    "integration: tests requiring network/database/filesystem",
    "e2e: end-to-end tests",
]
addopts = "-m 'not slow and not integration and not e2e'"
```

With `addopts`, `pytest` by default skips slow/integration tests. Developers get fast feedback locally. Override with `pytest -m ''` or `pytest --run-all` (add a custom flag).

### CI pipeline structure

```yaml
jobs:
  # ---- Job 1: lint (no tests, fastest feedback) ----
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v8.1.0
      - run: uvx pre-commit run --all-files
      - run: uv run mypy src/

  # ---- Job 2: fast tests (every PR, every push) ----
  test-fast:
    runs-on: ubuntu-latest
    needs: lint                  # fail-fast at lint tier
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v8.1.0
        with:
          python-version: ${{ matrix.python-version }}
          enable-cache: true
      - run: uv sync --locked --all-extras --dev
      - run: |
          uv run pytest tests/ \
            -m "not slow and not integration" \
            -n auto \
            --cov=src/mypackage \
            --cov-report=xml \
            --cov-report=term-missing

  # ---- Job 3: slow/integration tests (main branch + releases only) ----
  test-slow:
    if: github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/')
    runs-on: ubuntu-latest
    needs: test-fast
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v8.1.0
        with:
          enable-cache: true
      - run: uv sync --locked --all-extras --dev
      - run: |
          uv run pytest tests/ \
            -m "slow or integration" \
            --timeout=300
```

**Why `needs: lint` before `test-fast`?** Lint is cheapest and fails fast on syntax errors. Spending matrix minutes on tests that will fail at import is wasteful.

**Sources:** [pytest markers guide](https://pytest-with-eric.com/pytest-best-practices/pytest-markers/), [How to Master Pytest CI/CD 2026](https://tech-insider.org/pytest-tutorial-python-testing-ci-cd-2026/)

---

## 6. Coverage: pytest-cov, Thresholds, Reporting

### Configuration in pyproject.toml

```toml
[tool.pytest.ini_options]
addopts = "--cov=src/mypackage --cov-report=term-missing --cov-report=xml"

[tool.coverage.run]
source = ["src/mypackage"]
branch = true              # more honest than line coverage alone
relative_files = true      # REQUIRED for CI — without this, paths break

[tool.coverage.report]
show_missing = true
fail_under = 80            # job exits non-zero below this
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "@overload",
]
```

### Key gotchas (from danielnouri.org)

1. **Use `pytest --cov`, never `coverage run -m pytest -n auto`** — the latter bypasses pytest-cov's xdist integration and reports 0% when parallelizing.
2. **`relative_files = true` is mandatory in CI** — absolute paths from CI machines break coverage merging and PR comments.
3. **Include hidden `.coverage` file in artifacts** — add `include-hidden-files: true` to `actions/upload-artifact`.
4. **Fork PRs have read-only tokens** — use the two-workflow pattern (see below).
5. **Branch coverage (`branch = true`)** — measures whether both sides of conditionals execute; always enable it.

### GitHub Actions: coverage upload + PR comments

**Option A — Codecov** (external service, free for open-source):

```yaml
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v5
        with:
          files: ./coverage.xml
          fail_ci_if_error: true
          token: ${{ secrets.CODECOV_TOKEN }}
```

**Option B — py-cov-action** (no external service, posts comments natively):

```yaml
      - name: Coverage comment
        uses: py-cov-action/python-coverage-comment-action@v3
        with:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          MINIMUM_GREEN: 85
          MINIMUM_ORANGE: 70
```

**Two-workflow pattern for fork PRs** (fork PRs have read-only `GITHUB_TOKEN`):

```yaml
# ci.yml — runs on PR, saves coverage artifact
- name: Store coverage report
  uses: actions/upload-artifact@v4
  with:
    name: coverage-report
    path: coverage.xml
    include-hidden-files: true   # catches .coverage

# post-coverage.yml — runs on workflow_run with write permissions
on:
  workflow_run:
    workflows: [CI]
    types: [completed]
```

### What threshold is reasonable?

- **70–75%**: acceptable floor for a new project or one with heavy E2E coverage that's not instrumented
- **80%**: common practical baseline (pydevtools recommendation, widely cited)
- **90%+**: appropriate for libraries with public APIs; achievable with disciplined TDD
- **100%**: usually counterproductive — forces meaningless tests for error paths and `__repr__`

The best pattern: **start with your current baseline**, commit it, then require that coverage never drops. Gradually ratchet it up.

**Sources:** [Modern Python CI with Coverage 2025](https://danielnouri.org/notes/2025/11/03/modern-python-ci-with-coverage-in-2025/), [pytest-cov guide (pydevtools)](https://pydevtools.com/handbook/how-to/how-to-measure-code-coverage-with-pytest-cov/), [pytest-cov 2026 guide](https://qaskills.sh/blog/pytest-coverage-pytest-cov-guide-2026)

---

## 7. Dependency Updates: Dependabot vs Renovate

### Feature comparison

| Feature | Dependabot | Renovate |
|---|---|---|
| Built into GitHub | Yes (zero setup) | No (app install or self-host) |
| Package managers | 30+ (pip, Poetry, pipenv) | 90+ (pip, uv, Poetry, conda, Docker, GHA) |
| uv.lock support | **No** (as of mid-2025) | **Yes** |
| PR grouping | Limited (manual config) | Advanced presets (e.g. group all patches) |
| Automerge | Requires separate GHA workflow | Built-in, configurable per update type |
| Scheduling | daily/weekly/monthly/quarterly | Full cron expressions + per-dependency |
| Monorepo | No | Yes (`group:monorepos` preset) |
| Dependency Dashboard | No | Yes (issue tracking all pending updates) |
| Merge confidence badges | Single compatibility score | Age / Adoption / Passing / Confidence |
| Self-hosting | No | Yes (npm, Docker, GitHub Actions) |

### 2025 recommendation

**Use Dependabot if:** GitHub-only, simple pure-Python project, `requirements.txt` or Poetry, you want zero configuration.

**Use Renovate if:** you use `uv.lock`, manage Docker + GitHub Actions versions + Python deps in one tool, work in a monorepo, or need automerge and PR grouping.

A real-world Renovate win: a team with a 50-project monorepo went from 200 Dependabot PRs/week to a manageable trickle after enabling Renovate's grouped patch updates with automerge — saving ~15 hours/month.

**Renovate minimal config for Python + uv:**

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended"],
  "packageRules": [
    {
      "matchUpdateTypes": ["patch", "pin"],
      "automerge": true
    },
    {
      "matchDepTypes": ["devDependencies"],
      "matchUpdateTypes": ["minor", "patch"],
      "automerge": true
    }
  ],
  "lockFileMaintenance": {
    "enabled": true,
    "schedule": ["before 6am on Monday"]
  }
}
```

**Sources:** [Renovate Bot Comparison](https://docs.renovatebot.com/bot-comparison/), [Dependabot vs Renovate (PullNotifier)](https://blog.pullnotifier.com/blog/dependabot-vs-renovate-dependency-update-tools), [Renovate vs Dependabot (TurboStarter)](https://www.turbostarter.dev/blog/renovate-vs-dependabot-whats-the-best-tool-to-automate-your-dependency-updates)

---

## 8. Release Automation: python-semantic-release + Changelog

### Conventional commits — the input

All automation depends on structured commits. Enforce with commitizen or commitlint in pre-commit:

```
feat: add OAuth2 support          → minor bump (0.x.0 → 0.x+1.0)
fix: handle empty response        → patch bump (0.0.x → 0.0.x+1)
feat!: redesign public API        → major bump (x.0.0 → x+1.0.0)
chore: update dependencies        → no release
```

### pyproject.toml configuration

```toml
[tool.semantic_release]
version_toml = ["pyproject.toml:project.version"]
version_variables = ["src/mypackage/__init__.py:__version__"]
major_on_zero = false          # stay in 0.x until you declare stability
branch = "main"
tag_format = "v{version}"

[tool.semantic_release.changelog]
changelog_file = "CHANGELOG.md"
mode = "update"                # prepend new entries; don't overwrite

[tool.semantic_release.publish]
upload_to_vcs_release = true
```

### GitHub Actions release workflow

The critical issue: `semantic-release` needs to push a tag and commit to a protected `main` branch. **Do not use `GITHUB_TOKEN` — it cannot bypass branch protection.** The right solution (2025 best practice) is a dedicated GitHub App:

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    branches: [main]

jobs:
  release:
    runs-on: ubuntu-latest
    concurrency: release          # prevent simultaneous releases
    permissions:
      id-token: write             # for PyPI trusted publishing
      contents: write

    steps:
      - name: Generate GitHub App token
        uses: actions/create-github-app-token@v2
        id: app-token
        with:
          app-id: ${{ secrets.RELEASE_APP_ID }}
          private-key: ${{ secrets.RELEASE_APP_PRIVATE_KEY }}

      - uses: actions/checkout@v4
        with:
          fetch-depth: 0             # full history — semantic-release needs all tags
          token: ${{ steps.app-token.outputs.token }}

      - uses: astral-sh/setup-uv@v8.1.0
      - run: uv sync --locked --dev

      - name: Semantic Release
        run: |
          uv run semantic-release version
          uv run semantic-release publish
        env:
          GH_TOKEN: ${{ steps.app-token.outputs.token }}

      # Publish to PyPI via OIDC trusted publishing (no PYPI_TOKEN secret needed)
      - name: Build
        run: uv build

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          environment-name: pypi     # must match PyPI trusted publisher config
```

**GitHub App setup for protected branches:**
1. Create a GitHub App (Settings → Developer Settings → GitHub Apps)
2. Grant: Contents (Read/Write), Pull Requests (Read/Write)
3. In branch protection / ruleset: enable "Allow force pushes" restricted to this App
4. Store App ID and private key as repository secrets

**Sources:** [Semantic Release + Branch Protection (gonzalohirsch.com)](https://gonzalohirsch.com/blog/semantic-release-and-branch-protection-rules/), [Semantic Release to PyPI (guicommits.com)](https://guicommits.com/semantic-release-to-automate-versioning-and-publishing-to-pypi-with-github-actions/), [uv PyPI publishing](https://docs.astral.sh/uv/guides/integration/github/)

---

## 9. Branch Protection: Required Checks

### Recommended main branch protection configuration

In GitHub repository Settings → Branches → Branch protection rules (or Rulesets for org-level):

```
[x] Require a pull request before merging
    Require approvals: 1
    Dismiss stale reviews when new commits are pushed

[x] Require status checks to pass before merging
    [x] Require branches to be up to date (strict mode)
    Required checks:
      - lint (or "Lint / pre-commit")
      - test-fast (Python 3.11)
      - test-fast (Python 3.12)
      - test-fast (Python 3.13)
      # Do NOT require test-slow here — it only runs on main

[x] Require conversation resolution before merging
[x] Require linear history  (squash or rebase — no merge commits)
[ ] Allow force pushes      (disabled for humans; enabled only for Release App)
[x] Do not allow bypassing the above settings
```

**Rulesets (new, preferred over classic branch protection rules):**

GitHub Rulesets (available at org level since 2024) replace the old single-rule-per-branch model. They support bypass actors cleanly (e.g. "only the Release GitHub App may force-push") and can target multiple branches with one rule.

```
Settings → Rules → Rulesets → New branch ruleset
  Target branches: main
  Bypass list: [your Release GitHub App]
  Rules:
    [x] Require a pull request
    [x] Require status checks: lint, test-fast/*
    [x] Block force pushes (bypassed by App)
    [x] Require linear history
```

**Important quirk:** GitHub only shows status checks as selectable if they have run on the target branch within the last 7 days. Ensure your workflow has `push: branches: [main]` so checks appear, then add them to the required list.

**Sources:** [About Protected Branches (GitHub Docs)](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches), [Available Rules for Rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets), [GitHub Status Checks and Branch Protection (DEV)](https://dev.to/bobbyg603/github-status-checks-and-branch-protection-made-easy-2cnf)

---

## 10. Complete Reference Workflow

Putting it all together — a single, production-ready CI workflow for a Python library using uv:

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true   # cancel stale PR runs when new commits arrive

jobs:

  # ─────────────── Lint (fastest, required check) ────────────────
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v8.1.0
        with:
          enable-cache: true
      - run: uvx pre-commit run --all-files
      - run: uv sync --locked --dev
      - run: uv run mypy src/

  # ─────────────── Fast tests (required check, matrix) ───────────
  test-fast:
    name: Test / Python ${{ matrix.python-version }}
    runs-on: ubuntu-latest
    needs: lint
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v8.1.0
        with:
          python-version: ${{ matrix.python-version }}
          enable-cache: true
      - run: uv sync --locked --all-extras --dev
      - run: |
          uv run pytest tests/ \
            -m "not slow and not integration" \
            -n auto \
            --cov=src/mypackage \
            --cov-branch \
            --cov-report=xml \
            --cov-report=term-missing \
            --cov-fail-under=80
      - name: Upload coverage
        uses: actions/upload-artifact@v4
        if: matrix.python-version == '3.13'   # upload once
        with:
          name: coverage-report
          path: coverage.xml
          include-hidden-files: true

  # ─────────────── Coverage comment (PR only) ────────────────────
  coverage:
    name: Coverage comment
    runs-on: ubuntu-latest
    needs: test-fast
    if: github.event_name == 'pull_request'
    permissions:
      pull-requests: write
      contents: read
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: coverage-report
      - uses: py-cov-action/python-coverage-comment-action@v3
        with:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          MINIMUM_GREEN: 80
          MINIMUM_ORANGE: 70

  # ─────────────── Slow/integration tests (main + tags only) ─────
  test-slow:
    name: Integration Tests
    runs-on: ubuntu-latest
    needs: test-fast
    if: github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/')
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v8.1.0
        with:
          enable-cache: true
      - run: uv sync --locked --all-extras --dev
      - run: uv run pytest tests/ -m "slow or integration" --timeout=300
```

---

## Summary: Decision Matrix

| Decision | 2025 Best Practice |
|---|---|
| Package manager in CI | **uv** (pure Python); conda for C/CUDA deps |
| Caching | `enable-cache: true` on `astral-sh/setup-uv`; key = `uv.lock` hash |
| Lock files | Commit `uv.lock`; use `--locked` in CI |
| Pre-commit in CI | `uvx pre-commit run --all-files` — always run, never skip |
| Test default | Fast tier only; `addopts = "-m 'not slow'"` |
| Test on main | Full suite including slow/integration |
| Coverage threshold | 80% line+branch as floor; ratchet upward over time |
| Coverage service | `py-cov-action` (no account needed) or Codecov |
| Dependency updates | Renovate (supports uv.lock); Dependabot for simple pip projects |
| Release automation | `python-semantic-release` + conventional commits + GitHub App token |
| Branch protection | Rulesets with bypass actor for Release App; require lint + fast tests |
| Required checks | lint, test-fast (all matrix versions) — NOT test-slow |

---

**Sources:**
- [Using uv in GitHub Actions (uv official docs)](https://docs.astral.sh/uv/guides/integration/github/)
- [uv Caching Concepts](https://docs.astral.sh/uv/concepts/cache/)
- [Building and Testing Python (GitHub Docs)](https://docs.github.com/en/actions/guides/building-and-testing-python)
- [Setting up GitHub Actions with uv (pydevtools)](https://pydevtools.com/handbook/tutorial/setting-up-github-actions-with-uv/)
- [Optimizing uv Cache in GitHub Actions](https://szeyusim.medium.com/optimizing-uv-in-github-actions-one-global-cache-to-rule-them-all-9c64b42aee7f)
- [Pre-commit Hooks Guide 2025](https://gatlenculp.medium.com/effortless-code-quality-the-ultimate-pre-commit-hooks-guide-for-2025-57ca501d9835)
- [How to Set Up pre-commit for a Python Project (pydevtools)](https://pydevtools.com/handbook/how-to/how-to-set-up-pre-commit-hooks-for-a-python-project/)
- [Modern Python CI with Coverage in 2025 (Daniel Nouri)](https://danielnouri.org/notes/2025/11/03/modern-python-ci-with-coverage-in-2025/)
- [pytest-cov Coverage Guide (pydevtools)](https://pydevtools.com/handbook/how-to/how-to-measure-code-coverage-with-pytest-cov/)
- [pytest-cov 2026 Guide](https://qaskills.sh/blog/pytest-coverage-pytest-cov-guide-2026)
- [uv vs pip (Real Python)](https://realpython.com/uv-vs-pip/)
- [uv in 2026 — Decision Framework](https://www.heyuan110.com/posts/python/2026-04-10-uv-python-package-manager/)
- [Renovate Bot Comparison (official)](https://docs.renovatebot.com/bot-comparison/)
- [Dependabot vs Renovate (PullNotifier)](https://blog.pullnotifier.com/blog/dependabot-vs-renovate-dependency-update-tools)
- [Renovate vs Dependabot (TurboStarter)](https://www.turbostarter.dev/blog/renovate-vs-dependabot-whats-the-best-tool-to-automate-your-dependency-updates)
- [Semantic Release + Branch Protection (Gonzalo Hirsch)](https://gonzalohirsch.com/blog/semantic-release-and-branch-protection-rules/)
- [Semantic Release to PyPI (guicommits.com)](https://guicommits.com/semantic-release-to-automate-versioning-and-publishing-to-pypi-with-github-actions/)
- [python-semantic-release docs](https://python-semantic-release.readthedocs.io/)
- [About Protected Branches (GitHub Docs)](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [Available Rulesets Rules (GitHub Docs)](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- [pytest Markers Guide](https://pytest-with-eric.com/pytest-best-practices/pytest-markers/)
