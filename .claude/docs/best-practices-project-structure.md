# Python Best Practices: Project Structure & Conventions

**Phase 3 — Adversarial verification complete.** Key findings:

- AGENTS.md / Agentic AI Foundation: **CONFIRMED** — Linux Foundation officially announced the AAIF in December 2025 with OpenAI, Anthropic, Block as co-founders; AGENTS.md donated to the foundation; 60,000+ project adoptions verified.
- src/ layout as PyPA recommendation: **CONFIRMED** — packaging.python.org explicitly recommends it.
- uv as modern package manager: **CONFIRMED widely** — though pip remains PSF's official tool, uv is the de facto community default for new projects.
- "Princeton study 28.6% runtime reduction from AGENTS.md": **NOT independently verified** — single-source claim from a vendor site (morphllm.com); treating as unverified.
- Ruff replacing Black/isort/flake8: **CONFIRMED** across all sources.

**Phase 4 — Synthesis.**

---

# Modern Python Project Conventions: 2024–2026 Research Summary

## 1. Canonical Project Skeleton

The community has converged on a stable, opinionated skeleton. Below is the recommended layout for a distributable Python package as of 2025–2026:

```
my-project/
├── .github/
│   ├── workflows/          # CI/CD (GitHub Actions)
│   └── copilot-instructions.md   # Copilot-specific instructions (optional)
├── .pyclawd/               # or any project-specific agent/task config
│   └── config.py
├── docs/
│   └── source/             # Sphinx / MyST / Jupyter-cache docs
├── src/
│   └── my_package/
│       ├── __init__.py
│       ├── core.py
│       └── utils.py
├── tests/
│   ├── pytest.ini          # or conftest.py at root
│   ├── test_core.py
│   └── test_utils.py
├── AGENTS.md               # machine-readable agent instructions (universal)
├── CLAUDE.md               # Claude Code specific (can be `@AGENTS.md`)
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── LICENSE
├── README.md
├── pyproject.toml          # single source of truth for metadata + tools
├── .gitignore
├── .env.example            # committed template; .env itself is gitignored
└── uv.lock                 # or poetry.lock / pdm.lock
```

Sources: [pyOpenSci Python Package Guide](https://www.pyopensci.org/python-package-guide/package-structure-code/python-package-structure.html), [PyPA src-layout vs flat-layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/), [Real Python Project Layout](https://realpython.com/ref/best-practices/project-layout/)

---

## 2. The src/ Layout — Now the Clear Standard

### Why src/ Wins

The `src/` layout has been the consensus recommendation since ~2020 and is now the unambiguous PyPA-endorsed default.

**Core rationale:** without `src/`, running `python` from the project root silently imports the local source tree rather than the installed package. This means tests and scripts may pass locally while failing for end users who install from PyPI. Placing package code inside `src/` forces an explicit `pip install -e .`, which ensures imports always resolve to the installed build artifact.

Secondary benefits:
- Tests and docs at the root are excluded from the wheel automatically — no need for `MANIFEST.in` tricks.
- Clean semantic separation: code lives in `src/`, artefacts live at root level.
- Tools like `hatch`, `flit`, and `setuptools` all support `src/` natively via `pyproject.toml`.

**The flat layout lives on** in large scientific packages (NumPy, SciPy, Matplotlib, scikit-learn) purely because migration cost outweighs the benefit for mature projects with complex build systems. New projects have no reason to follow this precedent.

### pyproject.toml is Mandatory

`setup.py`, `setup.cfg`, and `MANIFEST.in` are deprecated for new projects. `pyproject.toml` is the single configuration file for:
- Build backend declaration (`[build-system]`)
- Project metadata (`[project]`)
- Tool configurations: ruff, mypy, pytest, coverage — all in one file

Common build backends in 2025: **hatchling** (fast, featureful), **flit-core** (minimal), **setuptools** (legacy-compatible). uv defaults to hatchling for new projects.

Sources: [PyPA packaging.python.org](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/), [pyOpenSci guide](https://www.pyopensci.org/python-package-guide/package-structure-code/python-package-structure.html)

---

## 3. `__init__.py` — When to Use It, When to Avoid It

### Regular Packages (use `__init__.py`)

Every directory under `src/` that forms part of your importable package surface needs `__init__.py`. It signals to Python (and to tools like mypy, ruff, IDEs) that the directory is a regular package. Keep it minimal — typically just:

```python
"""my_package — short one-line description of what this package does."""

__version__ = "1.2.3"
```

Re-exporting submodule symbols from `__init__.py` is legitimate but should be done deliberately; an overly crowded `__init__.py` couples consumers to your internal layout.

### Namespace Packages (omit `__init__.py`)

Python 3.3+ supports implicit namespace packages (via PEP 420 lineage) — directories without `__init__.py` that span multiple distribution packages. Use this when:
- You maintain a plugin ecosystem where third parties contribute sub-packages (e.g., `myorg.plugin_a`, `myorg.plugin_b` from separate repos).
- You explicitly want namespace splitting.

**For normal single-distribution packages: always include `__init__.py`.** Without it, ruff's `INP001` rule fires, tools behave inconsistently, and the performance scan cost (Python must search more path entries before resolving the package) is unnecessary.

**Avoid `__init__.py` in `tests/`** — the test directory is not a package you distribute or import; a bare directory with a `conftest.py` (or a `pytest.ini` at root) is correct.

Source: [Ruff INP001 rule](https://docs.astral.sh/ruff/rules/implicit-namespace-package/), [PyPA namespace packages guide](https://packaging.python.org/en/latest/guides/packaging-namespace-packages/)

---

## 4. PEP 257 — Module Docstrings Done Right

[PEP 257](https://peps.python.org/pep-0257/) specifies three levels of docstrings:

### Module docstrings

Every `.py` file, including `__init__.py`, should open with a module-level docstring. **The first line must be a self-contained one-liner** — a complete sentence ending with a period, 72 characters or fewer:

```python
"""HTTP client utilities for the my_package API wrapper."""
```

For non-trivial modules, follow the one-liner with a blank line and an extended description listing the main public classes, functions, and exceptions:

```python
"""HTTP client utilities for the my_package API wrapper.

Classes:
    APIClient: Authenticated session with retry and backoff.
    RateLimiter: Token-bucket rate limiter for outbound requests.

Exceptions:
    APIError: Base exception for all API errors.
"""
```

### Package `__init__.py` docstrings

Per PEP 257: "The docstring for a package … should also list the modules and subpackages exported by the package." In practice, one concise line describing the package's purpose is sufficient for tools like `pyclawd ls` to build a navigable code map.

### What belongs in a module docstring (not elsewhere)

| Put in module docstring | Put in function/class docstring |
|---|---|
| High-level purpose of the module | What the function does, args, returns |
| Exported symbols (for packages) | Exceptions raised |
| Non-obvious side-effects on import | Examples (doctests) |
| Author/copyright notices (if required by policy) | — |

Do **not** put implementation details, internal helper descriptions, or version history in module docstrings. PEP 257 is deliberately minimal; Google, NumPy, and reST docstring styles fill in the blank for function/method-level conventions.

Source: [PEP 257](https://peps.python.org/pep-0257/)

---

## 5. AI-Agent-Friendly Repos: CLAUDE.md and AGENTS.md

### The Standard as of 2025–2026

In August 2025, OpenAI released `AGENTS.md` as an open standard for giving AI coding agents project-specific context. In December 2025, it was donated to the **Agentic AI Foundation** (under the Linux Foundation), co-founded by Anthropic, OpenAI, and Block, with support from Google, Microsoft, and AWS. As of early 2026, AGENTS.md is adopted by 60,000+ open source projects and supported by Claude Code, Codex CLI, Cursor, Gemini CLI, GitHub Copilot, Aider, and 25+ other agents.

Sources: [Linux Foundation announcement](https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation), [OpenAI AAIF](https://openai.com/index/agentic-ai-foundation/), [InfoQ](https://www.infoq.com/news/2025/12/agentic-ai-foundation/)

### File Roles

| File | Purpose | Scope | Who reads it |
|---|---|---|---|
| `AGENTS.md` | Universal agent instructions (build, test, conventions, boundaries) | Shared / committed | 30+ agent frameworks |
| `CLAUDE.md` | Claude Code-specific instructions (can `@`-import AGENTS.md) | Project-level or global | Claude Code only |
| `AGENTS.override.md` | Personal/machine-local overrides | Gitignored | Local agent only |
| `.github/copilot-instructions.md` | Copilot-specific | Committed | GitHub Copilot |
| `.cursor/rules/*.mdc` | Scoped Cursor rules | Committed | Cursor |

**Recommended strategy:** Write `AGENTS.md` as the single source of truth. Then `CLAUDE.md` contains only `@AGENTS.md` (the import directive) plus any Claude Code-specific extras (MCP server configs, skill references). This eliminates duplication.

### What to Include

Based on research across deployhq.com, morphllm.com, augmentcode.com, and humanlayer.dev, the highest-value sections are:

1. **Build and test commands** — exact commands with all flags. Not "run the tests" but `pyclawd test fast` or `python -m pytest tests -c tests/pytest.ini -x`. This is the single most valuable contribution.
2. **Tech stack and versions** — framework, Python version, database. "FastAPI 0.115, Python 3.12, PostgreSQL 16" beats "Python web framework."
3. **Critical conventions** — rules the agent would otherwise get wrong: export patterns, API response shapes, migration locations, environment variable validation patterns.
4. **Explicit boundaries** — a three-tier structure works well:
   - `Always:` — mandatory actions (run pyclawd check before marking done)
   - `Ask first:` — destructive operations, PRs, dependency changes
   - `Never:` — forbidden actions (commit secrets, edit generated files, weaken tests)
5. **Non-standard tooling** — tools underrepresented in training data (e.g., `pyclawd`, `pixi`, `mise`)

### What to Exclude

- Code style rules that linters enforce automatically
- Obvious statements ("write clean code")
- Full API documentation (link to external docs)
- Architectural overviews the agent can discover by reading the code
- Auto-generated content — research shows LLM-generated AGENTS.md files reduce task success slightly while increasing token costs ~20%

### Size and Format

- Optimal length: **20–150 lines** for the primary file. Under 200 is comfortable; over 300 starts losing context. "If your config file is over 500 lines, most of it is being ignored."
- Codex enforces a 32 KiB hard cap; content beyond is silently truncated.
- For monorepos: place an `AGENTS.md` in each package sub-directory — the nearest file wins and provides package-specific context without polluting the root.

Source: [deployhq.com CLAUDE.md guide](https://www.deployhq.com/blog/ai-coding-config-files-guide), [morphllm.com AGENTS.md spec](https://www.morphllm.com/agents-md-guide), [augmentcode.com guide](https://www.augmentcode.com/guides/how-to-build-agents-md)

---

## 6. Task Runners: The 2025 Landscape

### The Problem with Bare Makefiles

Makefiles are universal (pre-installed on Linux/macOS) but have serious ergonomic problems for Python projects: tab-sensitive syntax, mandatory `.PHONY` declarations, no built-in variable completion, and semantics built around file timestamps rather than commands. They remain in heavy use (Django, CPython itself) but are declining for greenfield Python projects.

### Current Contenders

| Tool | Language | Config file | Python integration | Cross-platform | Notes |
|---|---|---|---|---|---|
| **Makefile** | Make DSL | `Makefile` | Manual | Linux/macOS | Universal; tab hell |
| **just** | Rust | `Justfile` | Via shell | Yes (Win/Linux/macOS) | Fastest growing; tab-optional; `--list` discovery |
| **Poe the Poet** | Python | `pyproject.toml` | Native | Yes | Config inside pyproject.toml; zero extra file |
| **invoke** | Python | `tasks.py` | Native | Yes | Python DSL; explicit Python dependency |
| **Taskfile** | Go | `Taskfile.yml` | Via shell | Yes | YAML-based; strong IDE support |
| **uv run** | Rust | `pyproject.toml` | Native | Yes | Built into uv; best for uv-managed projects |
| **tox** | Python | `tox.ini` / `pyproject.toml` | Native | Yes | Multi-version CI matrix; overkill for single-version |
| **nox** | Python | `noxfile.py` | Native | Yes | Python DSL; preferred for library multi-version testing |

### Recommendation for 2025

**For new library projects using uv:** Use `uv run` for simple scripts and a `[tool.poe.tasks]` section in `pyproject.toml` for compound tasks. This keeps everything in one file with zero extra tooling.

**For teams that want a polyglot task file:** `just` is the fastest-growing alternative. No language lock-in, tab-optional, readable recipes with documentation via `##` comments, `just --list` built-in discovery. Written in Rust so it's fast and dependency-free.

**For CI matrices across Python versions:** `tox` (legacy-compatible) or `nox` (Pythonic DSL) remain the right tool — not Make.

**Avoid:** `invoke` unless you already depend on it; it's a Python import away from a circular-dependency problem and has seen slower maintenance.

Sources: [rdrn.me Postmodern Python](https://rdrn.me/postmodern-python/), [mylinux.work comparison](https://mylinux.work/guides/taskfile-vs-just-vs-make/), [justfile review](https://twdev.blog/2024/06/just/)

---

## 7. Secrets Handling: .env, python-dotenv, and Production

### The Pattern

```
.env              # ← gitignored, never committed
.env.example      # ← committed, empty values, documents required keys
```

`.env.example` serves as the authoritative list of environment variables the project needs. New contributors copy it to `.env` and fill in real values. This is non-negotiable: if `.env` is ever accidentally committed, use `git filter-repo` or BFG Repo-Cleaner to scrub history — it remains readable in git history even after deletion.

### python-dotenv

```python
from dotenv import load_dotenv
load_dotenv()   # reads .env into os.environ at process start
```

`python-dotenv` is the standard for local development. For multi-environment setups, name files `.env.development`, `.env.test`, `.env.production` and load the appropriate one.

### Production: Never .env Files

`.env` + python-dotenv is a **local development convenience only**. In production:
- Kubernetes / Docker: mount secrets via `docker secret` or Kubernetes Secret objects, not baked into images
- Cloud: AWS Secrets Manager, Azure Key Vault, GCP Secret Manager
- Self-hosted: HashiCorp Vault

### CI/CD

GitHub Actions, GitLab CI, and similar platforms have first-class secret storage (encrypted at rest, exposed only as env vars during job runs). Never pass secrets via environment variables in plain YAML — use repository or environment secrets.

### Automation

Add CI secret-scanning via [TruffleHog](https://github.com/trufflesecurity/trufflehog) or [Gitleaks](https://github.com/gitleaks/gitleaks) to block accidental secret commits before merge. GitHub's push protection (free for public repos) also helps.

Source: [GitGuardian Python Secrets](https://blog.gitguardian.com/how-to-handle-secrets-in-python/), [python-dotenv PyPI](https://pypi.org/project/python-dotenv/)

---

## 8. .gitignore Best Practices for Python

The [official GitHub Python.gitignore](https://github.com/github/gitignore/blob/main/Python.gitignore) is the canonical starting point. Key categories:

```gitignore
# Byte-compiled / optimized
__pycache__/
*.py[codz]
*$py.class

# Distribution / packaging
build/
dist/
*.egg-info/
*.egg
MANIFEST
.eggs/

# Virtual environments
.venv/
venv/
env/
ENV/

# Secrets (add to .gitignore immediately)
.env
.envrc
.streamlit/secrets.toml

# Test & coverage artefacts
.coverage
.coverage.*
htmlcov/
.pytest_cache/
.tox/
.nox/
.hypothesis/

# Type checker caches
.mypy_cache/
.pyre/
.pytype/

# Linter caches
.ruff_cache/

# Lockfiles (team choice: commit or not)
# uv.lock   ← commit for apps; gitignore for libraries
# poetry.lock ← same rule

# IDE
.idea/
.vscode/

# Jupyter
.ipynb_checkpoints

# uv / pixi
.pixi/*
!.pixi/config.toml
```

**Lockfile policy:** For **applications and services**, commit the lockfile (`uv.lock`, `poetry.lock`, `pdm.lock`) for reproducible deployments. For **libraries**, do not commit it — consumers manage their own resolution.

Source: [GitHub Python.gitignore](https://github.com/github/gitignore/blob/main/Python.gitignore)

---

## 9. README Conventions: What Humans and Agents Need

`README.md` remains the first thing both humans and agents see. In 2025, the field has split the audience explicitly:

- **`README.md`** — human onboarding: what the project does, quickstart, installation, basic usage, links to full docs
- **`AGENTS.md`** — agent onboarding: exact commands, conventions, boundaries, non-obvious tooling

This means README can stay high-level and friendly. The pyOpenSci guide recommends these sections:

1. **Project name + one-line description** (also appears as PyPI short description)
2. **Badges** — CI status, coverage, PyPI version, Python version, license
3. **What it does** — 2–3 sentences; what problem it solves
4. **Quickstart / Installation** — copy-pasteable `pip install my_package` or `uv add my_package`
5. **Basic usage example** — a minimal code snippet that works
6. **Documentation link** — "Full docs at https://..."
7. **Contributing** — link to CONTRIBUTING.md
8. **License**

For an **agent reading the README**, the most important elements are: project purpose (to orient context), installation command (to set up), and links to further documentation. The README should not try to be AGENTS.md — command flags, test procedures, and architectural constraints belong there.

Source: [pyOpenSci README guide](https://www.pyopensci.org/python-package-guide/documentation/repository-files/readme-file-best-practices.html), [AGENTS.md best practices gist](https://gist.github.com/0xfauzi/7c8f65572930a21efa62623557d83f6e)

---

## 10. Monorepo vs Multi-Repo for Python: Current Thinking

### 2025 Consensus: Monorepo First

The consensus in 2024–2025 leans toward monorepos for teams building related Python services or libraries. The key argument: "Python's monorepo support isn't great, but it's far better than repo-per-thing." Coordination overhead (synchronized releases, shared CI, cross-cutting refactors) increases non-linearly with the number of repositories.

### Tooling Options

| Tool | Best for | Notes |
|---|---|---|
| **uv workspaces** | Python-only monorepos | Single lockfile, shared root pyproject.toml, workspace members in `libs/` and `apps/`; best ergonomics for 2025 |
| **Pants** | Large Python monorepos | Rust-based build, automatic dependency inference, multi-version support; steep learning curve |
| **Bazel** | Polyglot (Python + Go + Java) | Maximum power, maximum complexity |
| **Plain subdirectories** | Small teams | Separate `pyproject.toml` per package, CI matrix; simple but loses lockfile coherence |

### uv Workspaces (Recommended Starting Point)

```toml
# Root pyproject.toml
[tool.uv.workspace]
members = ["libs/*", "apps/*"]
```

Each member has its own `pyproject.toml`. A single `uv.lock` at the root covers all members. Members can reference each other as `{ workspace = true }` dependencies.

### When Multi-Repo Makes Sense

- Packages with entirely independent release cadences and no shared code
- Teams with strong ownership boundaries (different on-call rotations)
- Open-source libraries that need separate issue trackers, contributor agreements, and governance

Source: [rdrn.me Postmodern Python](https://rdrn.me/postmodern-python/), [Python Packaging monorepo discussion](https://discuss.python.org/t/monorepo-approach-to-handle-multiple-projects/78349)

---

## Synthesis: The Minimal Opinionated Stack (2025)

| Concern | Tool | Notes |
|---|---|---|
| Package manager | **uv** | Replaces pip, virtualenv, pyenv, Poetry in one binary |
| Build backend | **hatchling** | uv default; flit-core for minimal packages |
| Config | **pyproject.toml** | Single file for everything |
| Linter + formatter | **ruff** | Replaces Black, isort, flake8 |
| Type checker | **pyright** (or mypy) | Pyright: faster, better LSP; mypy: more mature ecosystem |
| Testing | **pytest** | With pytest-xdist for parallel runs |
| Task runner | **just** or **Poe the Poet** | just: polyglot, dependency-free; Poe: stays inside pyproject.toml |
| Secrets | **.env + python-dotenv** | Local only; production uses cloud secret stores |
| Agent instructions | **AGENTS.md** | Committed; CLAUDE.md = `@AGENTS.md` + Claude-specific extras |
| Layout | **src/** | Non-negotiable for distributed packages |
| Docs | **MyST + Sphinx** or **MkDocs** | jupyter-cache for notebook-heavy projects |
| CI | **GitHub Actions** | uv-based steps; tox/nox for multi-version matrix |

---

## Sources

- [pyOpenSci Python Package Structure Guide](https://www.pyopensci.org/python-package-guide/package-structure-code/python-package-structure.html)
- [PyPA: src layout vs flat layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
- [PEP 257 — Docstring Conventions](https://peps.python.org/pep-0257/)
- [Linux Foundation — Agentic AI Foundation announcement](https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation)
- [OpenAI — Co-founds AAIF](https://openai.com/index/agentic-ai-foundation/)
- [InfoQ — OpenAI and Anthropic donate AGENTS.md to AAIF](https://www.infoq.com/news/2025/12/agentic-ai-foundation/)
- [deployhq.com — CLAUDE.md, AGENTS.md, Copilot Instructions guide](https://www.deployhq.com/blog/ai-coding-config-files-guide)
- [morphllm.com — AGENTS.md Spec 2026](https://www.morphllm.com/agents-md-guide)
- [augmentcode.com — How to build AGENTS.md](https://www.augmentcode.com/guides/how-to-build-agents-md)
- [rdrn.me — Beyond Hypermodern / Postmodern Python](https://rdrn.me/postmodern-python/)
- [GitHub Python.gitignore template](https://github.com/github/gitignore/blob/main/Python.gitignore)
- [GitGuardian — Secrets in Python](https://blog.gitguardian.com/how-to-handle-secrets-in-python/)
- [python-dotenv on PyPI](https://pypi.org/project/python-dotenv/)
- [uv — GitHub](https://github.com/astral-sh/uv)
- [Ruff INP001 — implicit namespace package rule](https://docs.astral.sh/ruff/rules/implicit-namespace-package/)
- [twdev.blog — just task runner review](https://twdev.blog/2024/06/just/)
- [pyOpenSci README best practices](https://www.pyopensci.org/python-package-guide/documentation/repository-files/readme-file-best-practices.html)
- [Python Discuss — monorepo approach](https://discuss.python.org/t/monorepo-approach-to-handle-multiple-projects/78349)
- [Mr-Pepe — Setting Your Python Project Up for Success in 2024](https://medium.com/@Mr_Pepe/setting-your-python-project-up-for-success-in-2024-365e53f7f31e)

result: Delivered a 3,000-word fact-checked research report covering all 9 requested Python project convention topics (src/ layout, __init__.py, PEP 257, AGENTS.md/CLAUDE.md, task runners, secrets, gitignore, README, monorepo) with sources from PyPA, Linux Foundation, Astral, and 15+ additional authoritative references, across 5 parallel search angles and adversarial verification of key claims.
