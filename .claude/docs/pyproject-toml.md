# `pyproject.toml` best-practice defaults (2025–2026)

Researched June 2026 from authoritative sources — the PyPA packaging guide, the
relevant PEPs (517/518, 621, 639, 735, 751, 561), and the official tool docs
(Ruff, mypy, pytest, coverage.py, uv). Every non-obvious claim is cited inline.
This is a **research artifact** — what the ecosystem considers "best" — used to
shape pyclawd's scaffold defaults. Where the community is genuinely split, that is
flagged rather than papered over.

> **Library vs application.** The advice diverges in a few places. *Library* = code
> others `pip install` and import (published to an index). *Application* = a
> deployable end product (service, CLI, pipeline) that nothing depends on. Each
> divergence is marked **[lib]** / **[app]**.

---

## TL;DR — a modern reference `pyproject.toml`

```toml
[build-system]
requires = ["hatchling>=1.27", "hatch-vcs"]   # setuptools instead if you compile extensions
build-backend = "hatchling.build"

[project]
name = "spam-eggs"
dynamic = ["version"]                 # or a static version = "1.2.0"
description = "Lovely Spam! Wonderful Spam!"
readme = "README.md"
requires-python = ">=3.10"            # lowest you actually test
license = "MIT"                       # PEP 639 SPDX expression (string, not a table)
license-files = ["LICEN[CS]E*"]
authors = [{ name = "Jane Doe", email = "jane@example.com" }]
keywords = ["spam", "eggs"]
classifiers = [
  "Development Status :: 4 - Beta",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.10",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Operating System :: OS Independent",
  "Typing :: Typed",
]
dependencies = ["httpx>=0.27", "rich>=13"]   # floors only, NO upper caps (for libs)

[project.urls]
Homepage = "https://example.com"
Documentation = "https://example.readthedocs.io"
Repository = "https://github.com/me/spam"
Issues = "https://github.com/me/spam/issues"
Changelog = "https://github.com/me/spam/blob/main/CHANGELOG.md"

[project.scripts]
spam-cli = "spam.cli:main"

[project.optional-dependencies]       # user-facing optional features → extras
gui = ["PyQt5"]

[dependency-groups]                   # dev-only, NEVER published → PEP 735
test = ["pytest>=8.1", "coverage[toml]"]
typing = ["mypy"]
docs = ["sphinx>=7"]
dev = [{ include-group = "test" }, { include-group = "typing" }, { include-group = "docs" }]

[tool.hatch.version]
source = "vcs"

[tool.hatch.build.targets.wheel]
packages = ["src/spam"]

[tool.ruff]
line-length = 88                      # ecosystem default — see the line-length section
target-version = "py310"              # or omit and let Ruff read requires-python

[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP", "B", "C4", "SIM", "PIE", "RUF", "N", "D"]

[tool.ruff.lint.pydocstyle]
convention = "google"                 # google | numpy | pep257

[tool.ruff.lint.isort]
known-first-party = ["spam"]
combine-as-imports = true

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "D"]
"__init__.py" = ["F401"]

[tool.ruff.format]
docstring-code-format = true

[tool.mypy]
python_version = "3.10"
files = ["src", "tests"]
strict = true
warn_unused_configs = true
enable_error_codes = ["ignore-without-code", "redundant-expr", "truthy-bool", "possibly-undefined"]
mypy_path = "src"
explicit_package_bases = true

[[tool.mypy.overrides]]
module = ["untyped_dep.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
minversion = "8.0"
addopts = ["-ra", "--strict-markers", "--strict-config", "--import-mode=importlib"]
testpaths = ["tests"]
xfail_strict = true
filterwarnings = ["error"]
markers = [
  "slow: marks slow tests (deselect with '-m \"not slow\"')",
  "integration: needs live external services",
]

[tool.coverage.run]
branch = true
parallel = true
relative_files = true
source_pkgs = ["spam"]

[tool.coverage.paths]
source = ["src/spam", "*/site-packages/spam"]

[tool.coverage.report]
show_missing = true
skip_covered = true
fail_under = 85
exclude_also = [
  "if TYPE_CHECKING:",
  "raise NotImplementedError",
  "if __name__ == .__main__.:",
  "@(abc\\.)?abstractmethod",
  "\\.\\.\\.",
]
```

---

## 1. `[build-system]`

**Recommendation:** **hatchling** for pure-Python (the PyPA-blessed default, what `uv init`
scaffolds); **setuptools** if you build C/Cython/compiled extensions (hatchling is
metadata-only and does not compile).

```toml
[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"
```

- **hatchling** — modern, minimal, plugin system (`hatch-vcs`, `hatch-fancy-pypi-readme`), good `src/` defaults.
- **setuptools** — ubiquitous; **required for compiled extensions**. Floor today: `setuptools>=77.0.3` (full PEP 639 support). `wheel` no longer needs listing.
- **flit-core** — simplest, pure-Python only; great for tiny libs.
- **pdm-backend** — full-featured incl. dynamic versioning.
- **uv_build** — Astral's new backend; very fast but newest/least battle-tested; reasonable if you've committed to uv, else hatchling is more portable.

Pin **lower bounds only** (`>=`) in `requires`, never exact pins.

Split: hatchling (default) vs uv_build (fastest, newest) for greenfield uv projects.

Sources: [Writing your pyproject.toml (PyPA)](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/) · [Build backends in 2025](https://medium.com/@dynamicy/python-build-backends-in-2025-what-to-use-and-why-uv-build-vs-hatchling-vs-poetry-core-94dd6b92248f)

---

## 2. `[project]` metadata (PEP 621)

**Recommendation:** keep everything **static** except (optionally) `version`. Only `name`
is strictly required; in practice include name, version, description, readme,
requires-python, license, authors, classifiers, dependencies, urls.

- `requires-python` — lower bound only, **no upper cap** (an upper cap like `<4` causes
  spurious resolver conflicts — Brett Cannon). A reasonable 2025–2026 floor is `>=3.10`
  (wide) or `>=3.11` to align with Scientific-Python **SPEC 0** (drop versions ~3 years
  after release). Set it to the lowest version you actually test.
- `classifiers` — keep `Development Status`, per-minor `Programming Language :: Python ::
  3.x`, `Operating System`, `Intended Audience`, `Typing :: Typed`. **Drop all
  `License ::` classifiers** (deprecated by PEP 639 — see §3).
- `name` cannot be `dynamic`.

Sources: [PEP 621](https://peps.python.org/pep-0621/) · [pyproject.toml spec (PyPA)](https://packaging.python.org/en/latest/specifications/pyproject-toml/) · [SPEC 0](https://scientific-python.org/specs/spec-0000/)

---

## 3. License — PEP 639 (recent, important change)

**Recommendation:** declare the license as a **bare SPDX expression string** + a
`license-files` glob. PEP 639 is **Final**.

```toml
license = "MIT"                       # or "Apache-2.0", "GPL-3.0-or-later", "MIT AND BSD-2-Clause"
license-files = ["LICEN[CS]E*"]
```

**Deprecated — remove:** the table form `license = {text=...}` / `license = {file=...}`;
the `License ::` Trove classifiers; the legacy free-text License metadata field.

**Caveat:** needs `setuptools>=77.0.3` or `hatchling>=1.27` and recent pip/build.

Sources: [PEP 639](https://peps.python.org/pep-0639/) · [License expression spec (PyPA)](https://packaging.python.org/en/latest/specifications/license-expression/)

---

## 4. URLs, scripts, entry-points

`[project.urls]` (PyPI renders Homepage/Documentation/Repository/Issues/Changelog with
icons), `[project.scripts]` for console commands, `[project.gui-scripts]` for GUI apps
(matters on Windows — no console window), `[project.entry-points."group"]` for plugins.
Each value is `"importable.module:callable"`.

Source: [Writing your pyproject.toml (PyPA)](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)

---

## 5. Layout + dynamic version

**`src/` layout** is the recommendation for anything published — it forces tests to run
against the *installed* package, catching packaging mistakes (missing modules, bad
`package_data`) before release. Flat is fine for apps/scripts not installed as packages.
Tooling diverges: Poetry now prefers `src/` (Feb 2025); `uv init` still defaults flat
(`uv init --lib`/`--package` gives `src/`).

- hatchling: `[tool.hatch.build.targets.wheel] packages = ["src/mypkg"]` (auto-detects `src/<name>`).
- setuptools: `[tool.setuptools.packages.find] where = ["src"]`.

**Dynamic version** — single-source it: from a git tag (`hatch-vcs` / `setuptools-scm`,
release = `git tag`) or from a `__version__` attribute (`[tool.hatch.version] path =
"src/mypkg/__init__.py"`). A **static** `version = "1.2.0"` is also valid and "faster and
less error-prone" (PyPA) if you don't mind one edit per release.

Sources: [src vs flat layout (PyPA)](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/) · [Hynek — Testing & Packaging](https://hynek.me/articles/testing-packaging/) · [hatch-vcs](https://github.com/ofek/hatch-vcs) · [setuptools-scm](https://setuptools-scm.readthedocs.io/en/latest/usage/)

---

## 6. Dependencies

**Runtime — `[project.dependencies]`:**
- **[lib]** floors only, **no upper caps**, never Poetry's `^`. Python uses a *flat*
  dependency graph (one version per package, env-wide), so an over-tight cap in your
  library can make it uninstallable alongside others — and an over-constraint **cannot be
  fixed downstream** (a missing one can). Caps also block security updates.
- **[app]** same loose abstract deps + a committed **lock file** for reproducibility — not caps.
- Caps are defensible only narrowly: a known-broken release (temporarily), framework
  plugins tracking a major (pytest/Sphinx), tightly co-released packages.

**Dev/test/docs — `[dependency-groups]` (PEP 735, Final):** put developer-only deps here,
**not** in extras. Build backends MUST NOT publish dependency-group data, whereas
`[project.optional-dependencies]` (extras) *are* published so users can `pip install
pkg[extra]`. Compose with `include-group`. Decision rule: *could a consumer legitimately
want this at install time?* yes → extra; no → dependency-group. Install via `uv sync
--group dev` or `pip install --group dev`. uv's `tool.uv.dev-dependencies` is **legacy** —
prefer `[dependency-groups]`.

**Lock files:** **[app]** commit one (`uv.lock`/`pdm.lock`); **[lib]** do **not** ship one
(it would over-pin consumers). **PEP 751 `pylock.toml`** is Final (Mar 2025) — a
standardized, installer-facing lock; today treat it as an *export/interchange* format and
keep your tool's native lock as the day-to-day source of truth (pip `pip lock` and
`install -r pylock.toml` are experimental; uv/pdm can export it).

**Tooling 2025–2026:** **uv** is the momentum leader (Rust, ~5–8× faster than Poetry);
Poetry (mature, lags standards) and PDM (early standards adopter) remain fine if in use;
pip+venv is the zero-dependency baseline and now supports `[dependency-groups]`. Set
`[tool.uv] package = false` for an application that shouldn't be built/installed.

**`requires-python` ↔ resolution:** always set an explicit floor = lowest version tested;
resolvers must satisfy the *entire* declared range, so a too-low/absent floor forces
backtracking to ancient dependency releases.

Sources: [Should you use upper bound constraints? (Schreiner)](https://iscinumpy.dev/post/bound-version-constraints/) · [install_requires vs requirements (PyPA)](https://packaging.python.org/en/latest/discussions/install-requires-vs-requirements/) · [PEP 735](https://peps.python.org/pep-0735/) · [PEP 751](https://peps.python.org/pep-0751/) · [uv — dependencies](https://docs.astral.sh/uv/concepts/projects/dependencies/) · [uv — resolution](https://docs.astral.sh/uv/concepts/resolution/)

---

## 7. Ruff (lint + format)

### 7a. line-length — the contested one

**Research verdict: `line-length = 88` is the ecosystem default and the safe
recommendation.** It is the Black/Ruff default and is used by Django, NumPy, SciPy, and
pandas. Pick **99/100** only with explicit team agreement (PEP 8 sanctions up to 99);
**120 is the outlier** — it trades reviewability/diff-friendliness/accessibility for fewer
wraps.

The evidence:
- **88 (Black/Ruff):** empirically derived — "10% over 80"; Black found ~90 produces
  significantly shorter files than 79/80 with little benefit beyond, and explicitly warns
  *against* exceeding 100 (sight-disability accessibility + side-by-side diff review on
  typical screens).
- **79 (PEP 8 / stdlib):** the conservative baseline.
- **99/100:** PEP 8 explicitly allows a team to raise the limit "up to 99 characters,
  provided that comments and docstrings are still wrapped at 72." This is the formal basis
  for the 99/100 camp (Django historically 119 in the flake8 era, since moved off).
- **120:** rationale is wide monitors / fewer wraps; the outlier for general code.

| Project / tool | Code line length |
|---|---|
| Black (default) | 88 |
| Ruff (default) | 88 |
| PEP 8 / stdlib | 79 (teams may go to 99) |
| Django (code) | 88 (docs/docstrings 79) |
| NumPy / SciPy | 88 `.py` (120 for `.pyi` stubs) |
| Google style | 80 |

`line-length` is a formatter *target*, not a hard cap — formatted code may still exceed it
(long URLs/strings), so pairing with the `E501` lint rule is optional.

> **pyclawd note (decision point).** pyclawd currently **scaffolds `line-length = 120`**
> (an explicit owner preference) while its own repo uses `100`, and the research consensus
> is `88`. Three different numbers. Worth deciding: align the scaffold default to the
> consensus `88`, keep the deliberate `120`, or compromise at `99/100`. The research says
> `88`; the call is yours.

### 7b. the rest of Ruff

- **target-version:** prefer setting `[project] requires-python` and let Ruff infer it;
  only set `target-version` if there is no `[project]` table. It drives `UP`/`FA` rewrites.
- **`select`:** the Ruff default is only `["E4","E7","E9","F"]`. Use an explicit curated
  set (prefer `select` over `extend-select` for reproducibility). A strong-but-sane
  baseline: `["E","W","F","I","UP","B","C4","SIM","PIE","RUF","N"]` (+ `"D"` if you'll
  maintain docstrings). **Avoid `select = ["ALL"]`** — upgrades silently enable new rules
  and many families conflict.
- **pydocstyle:** enable `D` only if you'll maintain docstrings; ALWAYS pair `select=["D"]`
  with a `convention` (google/numpy/pep257) — selecting a convention disables the rules not
  in it, sparing you the full per-symbol D101/D102/D103 burden.
- **format:** accept defaults (double quotes, space indent, magic trailing comma honored);
  the one default worth flipping for doc-heavy code is `docstring-code-format = true`.
- **per-file-ignores:** `"tests/**" = ["S101", "D"]` (asserts + no docstrings),
  `"__init__.py" = ["F401"]` (re-exports).
- **isort** lives under Ruff's `I` rule (`[tool.ruff.lint.isort]` for `known-first-party`,
  `combine-as-imports`) — no separate isort tool needed.

Sources: [Ruff settings](https://docs.astral.sh/ruff/settings/) · [Ruff linter](https://docs.astral.sh/ruff/linter/) · [Ruff formatter](https://docs.astral.sh/ruff/formatter/) · [Black code style](https://black.readthedocs.io/en/stable/the_black_code_style/current_style.html) · [PEP 8](https://peps.python.org/pep-0008/)

---

## 8. mypy / typing

**Recommendation:** for **new** code turn on `strict = true` from day one and add the few
checks strict omits. For **existing** code do NOT flip strict globally — adopt module by
module via `[[tool.mypy.overrides]]`.

- `strict = true` bundles ~13 flags (disallow-untyped-defs, check-untyped-defs,
  warn-return-any, warn-unused-ignores, no-implicit-reexport, strict-equality, …). The
  exact set **changes between mypy versions**, so an upgrade can surface new errors.
- Add explicitly (not in strict): `warn_unused_configs = true`, and
  `enable_error_codes = ["ignore-without-code", "redundant-expr", "truthy-bool",
  "possibly-undefined"]` — `ignore-without-code` forces `# type: ignore[code]`.
- `no_implicit_optional` is on by default since mypy 0.980; `namespace_packages` defaults
  true.
- **`mypy_path = "src"` + `explicit_package_bases = true`** are needed for **src layout**
  and **single-file checking** (no `__init__.py` anchor) — exactly the pyclawd target-less
  `check <file>` case: mypy must reverse-map a file path to a dotted module, which needs a
  declared base dir, else it misnames the module / fails sibling imports.
- Third-party libs without stubs: prefer a `types-*` stub package; else scope
  `ignore_missing_imports = true` to that module via an override; **never** set it globally.
- **PEP 561 `py.typed`:** **[lib]** ship an (empty) `src/<pkg>/py.typed` so consumers'
  checkers see your annotations; **[app]** never needs it.
- **Landscape:** mypy (reference, richest plugins) or pyright (fast, great editor UX)
  remain the safe production default. Astral's **ty** is in **Beta (Dec 2025), pre-1.0**
  (10–60× faster) — adopt as a fast advisory/LSP checker, not yet a sole CI gate (Pydantic/
  Django stub support and full spec conformance still landing). (ty is **Astral's**, not
  OpenAI's — a common mis-citation.)

Sources: [mypy config](https://mypy.readthedocs.io/en/stable/config_file.html) · [mypy strict/command-line](https://mypy.readthedocs.io/en/stable/command_line.html) · [mypy existing code](https://mypy.readthedocs.io/en/stable/existing_code.html) · [typing spec — py.typed](https://typing.python.org/en/latest/spec/distributing.html) · [Astral — ty](https://astral.sh/blog/ty) · [Wolt — pro-grade mypy](https://careers.wolt.com/en/blog/tech/professional-grade-mypy-configuration)

---

## 9. pytest

**Recommendation:** `[tool.pytest.ini_options]` with list-form `addopts`:

```toml
[tool.pytest.ini_options]
minversion = "8.0"
addopts = ["-ra", "--strict-markers", "--strict-config", "--import-mode=importlib"]
testpaths = ["tests"]
xfail_strict = true
filterwarnings = ["error"]
markers = ["slow: ...", "integration: ..."]
```

- `--strict-markers` errors on unregistered markers (catches typos); `--strict-config`
  errors on unknown config keys; `-ra` summarizes all non-passing results; `xfail_strict`
  turns an unexpectedly-passing xfail into a failure.
- **`--import-mode=importlib`** is the modern recommendation (pytest "good practices") — it
  doesn't mutate `sys.path`/`sys.modules`. Pair with `src/` layout and **no `__init__.py`
  in `tests/`** (keep test basenames unique).
- **`filterwarnings = ["error"]`** (debated): recommended for dev/CI so you fix
  deprecations before users hit them — but a new third-party release can redden CI on a
  day you changed nothing, so pair it with targeted `"ignore::...:module.*"` escapes (last
  match wins; message is a case-insensitive regex on the start).

Sources: [pytest customize](https://docs.pytest.org/en/stable/reference/customize.html) · [pytest good practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html) · [capture warnings](https://docs.pytest.org/en/stable/how-to/capture-warnings.html) · [Scientific Python — pytest](https://learn.scientific-python.org/development/guides/pytest/)

---

## 10. coverage.py

```toml
[tool.coverage.run]
branch = true
parallel = true            # needed for pytest-xdist / multi-env; then `coverage combine`
relative_files = true
source_pkgs = ["mypkg"]    # by import name — resolves the installed package (src layout)

[tool.coverage.paths]
source = ["src/mypkg", "*/site-packages/mypkg"]   # fold env copies back onto src

[tool.coverage.report]
show_missing = true
skip_covered = true
fail_under = 85
exclude_also = ["if TYPE_CHECKING:", "raise NotImplementedError", "\\.\\.\\."]
```

- Prefer **`exclude_also`** over `exclude_lines` (the latter *replaces* the default
  patterns like `pragma: no cover`; `exclude_also` *adds*).
- `source_pkgs` (by import name) over `source` (directory) when testing the **installed**
  package; add `[tool.coverage.paths]` to combine cross-env runs.
- **`fail_under`:** no official norm — ratchet it to current coverage to prevent
  regressions; common band is **80–90%**.
- **Don't bake `--cov` into pytest `addopts`** (debated): coverage's `sys.settrace` breaks
  IDE breakpoints. Prefer explicit `coverage run -m pytest` then `coverage report`, or pass
  `--cov` only in CI; if you keep it, use `--no-cov` when debugging and always write
  `--cov=pkg` (the option eats the next arg if left bare).

Sources: [coverage config](https://coverage.readthedocs.io/en/latest/config.html) · [pytest-cov debuggers](https://pytest-cov.readthedocs.io/en/latest/debuggers.html) · [Scientific Python — coverage](https://learn.scientific-python.org/development/guides/coverage/) · [Hynek — Testing & Packaging](https://hynek.me/articles/testing-packaging/)

---

## Genuinely split decisions (decide per project)

1. **Build backend:** hatchling (PyPA default) vs uv_build (fastest, newest); setuptools is mandatory for compiled extensions.
2. **line-length:** 88 (consensus) vs 99/100 (team-agreed, PEP 8) vs 120 (outlier).
3. **Version source:** git-tag dynamic (hatch-vcs/setuptools-scm) vs static / `__version__`.
4. **Layout:** `src/` (published libs) vs flat (apps; uv's default).
5. **`filterwarnings = ["error"]`:** strict dev/CI vs flaky against third-party deprecations.
6. **`--cov` in `addopts`:** one-command convenience vs broken debuggers.
7. **Type checker:** mypy (standard) vs pyright (fast/UX) vs ty (fastest, pre-1.0).
8. **Dep caps [lib]:** PyPA/core consensus = no caps; Poetry-influenced camp defaults to `^`.

---

## Implications for pyclawd's scaffold

pyclawd scaffolds quality config in `scaffold/templates/pyproject.toml.tmpl`, the
`--scaffold-pyproject` adopt starter (`commands/new.py`), and dogfoods its own in
`pyproject.toml`. To match this research, candidate updates (each a deliberate choice):

- **line-length** — reconcile the three values (scaffold 120 / own 100 / consensus 88).
- **ruff `select`** — the scaffold uses `["E","F","I","D"]`; the researched baseline adds
  `W, UP, B, C4, SIM, PIE, RUF, N`.
- **mypy** — consider `strict = true` + `warn_unused_configs` + the extra error codes in
  the scaffolded `[tool.mypy]` (it already sets `files` + `explicit_package_bases`).
- **pytest** — add `--strict-markers --strict-config --import-mode=importlib`, `-ra`,
  `xfail_strict`, and register markers in the scaffolded `[tool.pytest.ini_options]`.
- **license** — scaffold the PEP 639 `license = "..."` + `license-files` form.
- **dependency-groups** — scaffold dev deps under `[dependency-groups]` (PEP 735) rather
  than extras.

None applied here — this file is research only.
