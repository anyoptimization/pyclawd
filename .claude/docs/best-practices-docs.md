# Python Best Practices: Documentation (Sphinx, Notebooks)

I have all the data I need. Running adversarial verification on key claims before synthesis.

**Claims to verify (3-vote check):**
1. Material for MkDocs entered maintenance mode in early 2026 → Confirmed by search result citing the team's announcement of Zensical successor.
2. RTD Addons enabled by default October 7, 2024, removing auto-injected Sphinx context → Confirmed by the RTD changelog GitHub issue.
3. PEP 727 was withdrawn → Confirmed by peps.python.org search result.
4. `nb_execution_mode = "cache"` is the key for jupyter-cache → Confirmed by myst-nb execution docs.
5. sphinx-autoapi v3.8.0 is current (March 2026) → Confirmed by search result.
6. llms.txt proposed by Jeremy Howard of Answer.AI → Confirmed by multiple sources.

All 6 key claims pass 2/3 verification. Now synthesizing.

---

# Python Documentation Best Practices: 2024–2026

*Research synthesized from Sphinx docs, MyST-NB docs, Read the Docs guides, sphinx-autoapi docs, napoleon docs, myst-nb execution docs, jupyter-cache docs, and llms.txt specification — June 2026.*

---

## 1. Sphinx vs MkDocs vs pdoc: Current Consensus

### The Landscape

| Tool | Sweet spot | Format | Strengths | Weaknesses |
|------|-----------|--------|-----------|------------|
| **Sphinx** | Large/complex libraries, scientific Python, anything needing PDF/ePub | RST + MyST Markdown | Multi-format output, doctest, autodoc/autoapi, mature ecosystem | Steeper learning curve, RST overhead unless using MyST |
| **MkDocs + Material** | Smaller libs, developer tools, REST APIs, projects where aesthetics matter | Markdown only | Beautiful out-of-box, YAML config, live reload, massive ecosystem | API docs less mature, no built-in doctest, Markdown-only |
| **pdoc** | Small libs, auto-only API reference | Python introspection | Zero config, one command | No narrative docs, no versioning, no notebooks |

### What the Community Is Doing in 2025–2026

The **FastAPI / Pydantic / Typer / SQLModel** ecosystem (Sebastián Ramírez's stack) standardized on MkDocs + Material, pulling a large swathe of the Python ecosystem with it. Meanwhile, the **NumPy / SciPy / Pandas / scikit-learn** ecosystem remains on Sphinx with the pydata-sphinx-theme.

A notable 2026 development: **Material for MkDocs entered maintenance mode in early 2026**, with critical bug and security fixes continuing but new feature work moved to **Zensical** — a successor project from the same team, designed to read existing `mkdocs.yml` configurations. For projects picking a stack today, Material is still the safe choice, but watch Zensical.

### Decision Tree

```
Does your project need:
  - PDF output, ePub, or LaTeX?           → Sphinx
  - Executable doctests in docstrings?    → Sphinx
  - Jupyter notebook integration?         → Sphinx (myst-nb) or Sphinx (nbsphinx)
  - Scientific Python ecosystem?          → Sphinx + pydata-sphinx-theme
  - Maximum aesthetics, minimal config?   → MkDocs + Material (or Zensical)
  - Auto-only, zero narrative docs?       → pdoc
  - REST API with Markdown narrative?     → MkDocs + mkdocstrings
```

**Bottom line:** Sphinx wins for library documentation where API reference + notebooks + doctests matter. MkDocs wins where developer experience and polish take priority over deep API features. Most serious Python libraries still ship Sphinx.

---

## 2. Docstring Style: Google vs NumPy vs reStructuredText

### The Three Styles Compared

**reStructuredText (reST) — native Sphinx:**
```python
def compute(x, n):
    """Raise x to the power of n.

    :param x: The base value.
    :type x: float
    :param n: The exponent.
    :type n: int
    :returns: x raised to the n.
    :rtype: float
    :raises ValueError: If n is negative.
    """
```
Dense, hard to read inline, requires `:type:` duplication when not using PEP 484 annotations. Avoid in new code.

**Google style (via Sphinx Napoleon):**
```python
def compute(x: float, n: int) -> float:
    """Raise x to the power of n.

    Args:
        x: The base value.
        n: The exponent.

    Returns:
        x raised to the n.

    Raises:
        ValueError: If n is negative.
    """
```
Clean, readable inline, good for most library code. Note: with PEP 484 annotations present, types are omitted from `Args`.

**NumPy style (via Sphinx Napoleon):**
```python
def compute(x: float, n: int) -> float:
    """Raise x to the power of n.

    Parameters
    ----------
    x : float
        The base value.
    n : int
        The exponent.

    Returns
    -------
    float
        x raised to the n.

    Raises
    ------
    ValueError
        If n is negative.
    """
```
More verbose, better for scientific code with complex multi-line parameter descriptions. Still lists types even with annotations (ecosystem convention).

### 2025 Consensus

- **Google style** is the most widely adopted choice for new general-purpose libraries.
- **NumPy style** remains the standard in scientific Python (numpy, scipy, pandas, sklearn — they will not change, and contributors should match).
- **reST style** is effectively obsolete for humans writing docstrings; it only appears in legacy code and auto-generated output.
- Pick based on **ecosystem alignment**: if your library lives in scientific Python, use NumPy. Otherwise, Google.
- **The most critical rule in 2025: be consistent within a project**. Mixing styles within a codebase is the #1 docstring mistake.

---

## 3. Type Annotations — The Modern Approach

**The rule is simple:** PEP 484 annotations in the function signature replace type information in docstrings. Do not duplicate.

### Before (legacy reST with types in docstring):
```python
def parse(data, strict=False):
    """Parse the input.

    :param data: Raw input string.
    :type data: str
    :param strict: Whether to raise on error.
    :type strict: bool
    :rtype: dict
    """
```

### After (modern — annotations only, Google docstring):
```python
def parse(data: str, strict: bool = False) -> dict:
    """Parse the input.

    Args:
        data: Raw input string.
        strict: Whether to raise on error.

    Returns:
        Parsed key-value mapping.
    """
```

### Tool Chain

Add `sphinx-autodoc-typehints` to pull PEP 484 annotations into rendered HTML:

```python
# conf.py
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints",   # pulls annotations → :type: in output
]

# Napoleon settings — suppress redundant type output when annotations exist
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = True   # convert type strings → cross-references
```

Both Google and NumPy styles allow omitting type fields from docstring sections when PEP 484 annotations are in the signature — Sphinx Napoleon respects this.

**PEP 727 note:** PEP 727 (documentation metadata in `Annotated`) was withdrawn. Do not plan around it.

---

## 4. Jupyter Notebooks as Docs: nbsphinx vs myst-nb vs jupytext

### The Contenders

| Feature | nbsphinx | myst-nb |
|---------|----------|---------|
| Extension | `nbsphinx` | `myst_nb` |
| Markdown flavor | Pandoc (CommonMark) | MyST (extended CommonMark) |
| Execution timing | During parse phase | Up-front; cache with jupyter-cache |
| jupyter-cache integration | No | Yes — core feature |
| Thumbnail galleries | Yes | No |
| Cell numbering | Shown by default | Hidden by default |
| "Glue" (embed outputs elsewhere) | No | Yes |
| Error reporting | Basic | Sophisticated |
| Text notebook support | Via jupytext | Native MyST + jupytext |
| RTD recommendation | Neither explicitly | Neither explicitly |
| pydata-sphinx-theme preference | myst-nb | myst-nb |

### The executablebooks Project Position (2024)

The [executablebooks organization discussion #1035](https://github.com/orgs/executablebooks/discussions/1035) (which maintains both myst-nb and jupyter-book) frames the choice as:
- **nbsphinx** if you need thumbnail galleries or prefer execution-during-parse semantics
- **myst-nb** if you want caching, the MyST feature set, or "glue" output embedding

**For new projects in 2025: prefer myst-nb.** It is the direction the Executable Books Project is investing in, and jupyter-cache integration is a significant build-time advantage for large doc sets.

### Jupytext's Role

Jupytext is not a docs tool — it is a **format converter**. It enables:
- Writing notebooks as plain `.md` or `.py` files (diff-friendly, git-friendly)
- Bidirectional conversion: `jupytext notebook.ipynb --to myst` / `jupytext mystfile.md --to ipynb`
- Opening `.md` notebooks in JupyterLab via the Jupytext extension

Both nbsphinx and myst-nb read jupytext-format files. The workflow is: **author in `.md` (MyST format) → myst-nb renders it in Sphinx → jupyter-cache caches execution**.

---

## 5. jupyter-cache: The Execute-Once Workflow

### How It Works

jupyter-cache executes notebooks and stores results in a local SQLite-backed cache. On subsequent builds, notebooks with **unchanged code cells** are served from cache — skipping execution entirely. Only modified notebooks re-execute.

### Setup with myst-nb (the primary integration)

**Installation:**
```bash
pip install myst-nb jupyter-cache
```

**`conf.py` configuration:**
```python
extensions = ["myst_nb"]

# Core: use cache mode (execute-once, reuse on unchanged code)
nb_execution_mode = "cache"

# Optional: custom cache location (default: _build/.jupyter_cache)
nb_execution_cache_path = "docs/_build/.jupyter_cache"

# Exclude notebooks that should not execute (e.g., require external services)
nb_execution_excludepatterns = ["*slow_demo*", "*external_api*"]

# Timeout per cell in seconds (default: 30)
nb_execution_timeout = 60

# Run notebooks in an isolated temp directory
nb_execution_in_temp = False

# Allow notebooks to have errors without failing the build
nb_execution_allow_errors = False

# Raise a build error if any notebook fails to execute
nb_execution_raise_on_error = True

# Kernel alias mapping (useful if notebooks use custom kernel names)
nb_kernel_rgx_aliases = {"myenv.*": "python3"}
```

### Execution Mode Summary

| `nb_execution_mode` | Behavior |
|---------------------|----------|
| `"off"` | Never execute; use pre-stored outputs |
| `"auto"` | Execute notebooks with missing outputs (default) |
| `"cache"` | Execute + cache; reuse cache on unchanged code |
| `"force"` | Always re-execute everything |
| `"inline"` | Execute during parse for variable interpolation |

### Inspecting the Cache

```bash
# List cached notebooks
jcache notebook -p docs/_build/.jupyter_cache list

# Show execution report
jcache project -p docs/_build/.jupyter_cache info
```

### Recommended Workflow

```
First build:  all notebooks execute → results stored in .jupyter_cache
Edit Markdown:  next build is instant (cached)
Edit code cell:  that notebook re-executes; others are cached
CI:             commit .jupyter_cache to skip re-execution, OR
                use "force" mode in CI for reproducibility guarantees
```

**Note:** Do not commit `.jupyter_cache` if notebooks fetch live data or have non-deterministic output. Use `nb_execution_mode = "force"` in CI and `"cache"` locally.

---

## 6. API Docs Auto-Generation

### The Options

**`sphinx.ext.autodoc`** (built-in, traditional):
- Imports the module at build time and extracts docstrings via introspection
- Requires the package to be installed and importable in the build environment
- Manual: you write `.rst` files with `.. automodule::` / `.. autoclass::` directives
- Still widely used; battle-tested

**`sphinx-apidoc`** (CLI tool, built-in):
- Generates `.rst` stub files that call `autodoc` directives
- Run once, check in the stubs, or regenerate on CI
- Still requires import at build time

**`sphinx-autoapi`** (recommended for new projects):
- Static analysis only — **never imports your code**
- Works in CI environments where the package isn't installed
- Auto-generates a complete `autoapi/` directory with one TOC entry per module
- Handles the long-standing Sphinx limitation where `autosummary` fails to generate TOC entries for nested API elements
- Current version: **3.8.0 (March 2026)**, maintained by Read the Docs

### sphinx-autoapi Setup

```bash
pip install sphinx-autoapi
```

```python
# conf.py
extensions = [
    "autoapi.extension",
    "sphinx.ext.napoleon",         # for Google/NumPy docstring rendering
    "sphinx_autodoc_typehints",    # for PEP 484 annotation rendering
]

# Point at your source tree (relative to docs/ source dir)
autoapi_dirs = ["../src"]

# What to document
autoapi_options = [
    "members",
    "undoc-members",
    "show-inheritance",
    "show-module-summary",
    "imported-members",
    # Remove "private-members" and "special-members" unless needed
]

# Ordering: alphabetical | bysource | groupwise
autoapi_member_order = "bysource"

# Which docstring to show for classes: class | init | both
autoapi_python_class_content = "both"

# Output directory (relative to docs source)
autoapi_root = "api"

# Keep generated .rst files for debugging
autoapi_keep_files = False

# How types from annotations appear in output
autodoc_typehints = "description"   # or "signature"
```

Then in `index.rst` or `index.md`, autoapi auto-inserts itself into the TOC (controlled by `autoapi_add_toctree_entry = True`).

### autodoc vs autoapi — When to Use Each

| Scenario | Recommendation |
|----------|---------------|
| Package always installable at build time | Either; autodoc is fine |
| Build in a clean CI environment | **autoapi** (no import needed) |
| Need to control exactly which symbols appear | autodoc (more granular directives) |
| Want zero-config, works out of box | **autoapi** |
| Documenting C extensions or compiled code | autodoc (autoapi's static analysis can't parse C) |

---

## 7. Versioned Docs: Read the Docs vs GitHub Pages

### Read the Docs

The dominant choice for OSS Python libraries. Key 2024 change: **RTD Addons were enabled by default on October 7, 2024**, which removed the auto-injected Sphinx context and stopped RTD from installing `readthedocs-sphinx-ext` automatically. Projects that relied on this needed to update their `conf.py` or `readthedocs.yaml`.

**What RTD gives you:**
- Automatic version detection from git tags and branches
- Version selector flyout (via Addons)
- PR preview builds
- Free hosting for open-source
- Search across versions
- PDF/ePub generation on the same build

**Minimal `.readthedocs.yaml`:**
```yaml
version: 2

build:
  os: ubuntu-22.04
  tools:
    python: "3.12"

sphinx:
  configuration: docs/conf.py

python:
  install:
    - method: pip
      path: .
      extra_requirements:
        - docs
```

### GitHub Pages

Better for: full control, private repos, custom domains, projects already deep in GitHub Actions.

**Basic GitHub Actions workflow for Sphinx → GitHub Pages:**
```yaml
# .github/workflows/docs.yml
name: Deploy Docs
on:
  push:
    branches: [main]
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # needed for versioned docs tools

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - run: pip install -e ".[docs]"

      - name: Build docs
        run: sphinx-build docs docs/_build/html

      - uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: docs/_build/html
```

For **versioned GitHub Pages**, use `sphinx-versioned-docs` or `sphinx-multiversion`, which build each tag/branch into a subdirectory (`docs/v1.0/`, `docs/v2.0/`) with a version switcher.

### RTD vs GitHub Pages Decision

| Need | RTD | GitHub Pages |
|------|-----|-------------|
| Zero-config versioning | ✓ | Requires extra tooling |
| PR preview builds | ✓ (built-in) | Requires GitHub Actions |
| Search | ✓ (built-in) | Requires Algolia or similar |
| PDF output | ✓ | Manual |
| Private docs | Paid | ✓ (free on private repos) |
| Custom domain | ✓ | ✓ |
| Full build control | Limited | ✓ |

**For OSS: use Read the Docs.** For internal or enterprise: GitHub Pages.

---

## 8. Examples as Tests: doctest vs Example Notebooks

### doctest

Python's `doctest` module finds `>>>` prompts in docstrings and executes them, verifying output matches. Integrates with pytest via `--doctest-modules`.

**Best for:**
- Simple, self-contained function examples
- Keeping examples in sync with implementation automatically
- API functions with deterministic, short output

```python
def add(a: int, b: int) -> int:
    """Add two integers.

    >>> add(1, 2)
    3
    >>> add(-1, 1)
    0
    """
    return a + b
```

Run via pytest:
```bash
pytest --doctest-modules src/
# or in pyproject.toml:
# [tool.pytest.ini_options]
# addopts = "--doctest-modules"
```

**Limitations:** No fixture management, fragile to output formatting changes (whitespace, floats), awkward for multi-step examples, no visualization.

### Example Notebooks

Jupyter notebooks as documentation that double as integration tests via **nbval** or **pytest-notebook**:

```bash
pip install nbval
pytest --nbval docs/examples/tutorial.ipynb
```

**Best for:**
- Complex end-to-end workflows
- Visualization-heavy tutorials
- Multi-step examples where intermediate state matters
- Demonstrating library integrations

**Limitations:** Slow, output can be non-deterministic (timestamps, IDs), requires full environment at test time, harder to run in lightweight CI.

### The 2025 Pattern: Both, Complementary

```
Simple API examples   → doctests in docstrings (fast, always current)
Complex tutorials     → Jupyter notebooks with nbval in CI (catches regression)
Scratch examples      → jupyter-cache in docs (execute-once, no test overhead)
```

The **MkDocs trap:** switching to MkDocs means losing `--doctest-modules` unless you maintain a parallel test step. Several teams (as documented in the switching-to-MkDocs article) keep a Sphinx config purely for testing.

---

## 9. What Documentation AI Agents Need vs What Humans Need

### The Human Needs

- Narrative explanation ("why does this exist?")
- Progressive disclosure (tutorial → how-to → reference → explanation)
- Searchable, beautiful rendered HTML
- Code examples with syntax highlighting
- Version context ("added in v2.0")

### The Agent Needs

AI coding agents (Claude Code, Copilot, Cursor) need:

1. **Machine-readable function signatures** with complete type annotations — autoapi-generated RST/JSON serves this well
2. **Explicit parameter constraints** (valid ranges, formats, required vs optional) — not just types
3. **Realistic examples** not placeholders (`"2024-01-15"` not `"string"`)
4. **Complete error schemas** — what exceptions, when, what to do about them
5. **Token-efficient flat text** — not paginated HTML with navigation chrome

### llms.txt — The Emerging Standard (2025–2026)

[llms.txt](https://llms-txt.io/) is a Markdown file placed at `/llms.txt` on your docs site, proposed by Jeremy Howard (Answer.AI). It acts as a structured index for AI tools — stripping navigation, CSS, and JS, leaving clean machine-readable content.

**Two variants:**
- `llms.txt`: summaries with links — token-efficient for large APIs
- `llms-full.txt`: full content embedded — better for context-window-sized APIs

Early adopters: Stripe, Cloudflare, Vercel, Hugging Face, Coinbase.

**Minimal `llms.txt` for a Python library:**
```markdown
# mylib

> A Python library for X. Install: `pip install mylib`.

## API Reference

- [Core module](https://mydocs.example.com/api/core): Primary public surface — Foo, Bar classes
- [Utils](https://mydocs.example.com/api/utils): Helper functions

## Guides

- [Quickstart](https://mydocs.example.com/guide/quickstart): 5-minute getting started
- [Authentication](https://mydocs.example.com/guide/auth): Token setup and rotation

## Changelog

- [v2.0 migration](https://mydocs.example.com/changelog/v2): Breaking changes from v1
```

### Structuring Docstrings for AI Consumption

The overlap between "good for humans" and "good for agents" is large. Key differences:

| Aspect | Human-optimal | Agent-optimal |
|--------|--------------|--------------|
| Parameter description | "The user's name" | "The user's name (1–100 chars, unicode safe)" |
| Return description | "The parsed result" | "Parsed Result object; `.data` is None on empty input" |
| Error section | "Raises ValueError" | "Raises ValueError if x < 0; raises TypeError if x is not numeric" |
| Examples | Single happy path | Happy path + at least one error path |
| Cross-references | Nice to have | Critical — enables agents to navigate the API graph |

**Concrete recommendation:** Write docstrings in Google style with full type annotations in the signature. Add an `Examples:` section for any function that isn't self-evident. The structured format (section headers, consistent indentation) is more parseable by both sphinx-napoleon and LLM tokenizers than freeform prose.

---

## Quick-Start Stack Recommendation (2025)

For a **new Python library** that wants best-of-breed documentation:

```python
# pyproject.toml — docs dependencies
[project.optional-dependencies]
docs = [
    "sphinx>=7",
    "pydata-sphinx-theme",       # or furo
    "myst-nb",                   # notebooks as docs
    "jupyter-cache",             # execute-once cache
    "sphinx-autoapi",            # API docs without import
    "sphinx-autodoc-typehints",  # PEP 484 annotations → rendered
    "sphinx-copybutton",         # copy button on code blocks
]
```

```python
# docs/conf.py — minimal working config
project = "mylib"
extensions = [
    "myst_nb",
    "autoapi.extension",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints",
    "sphinx.ext.intersphinx",
]

# Notebooks
nb_execution_mode = "cache"
nb_execution_cache_path = "docs/_build/.jupyter_cache"
nb_execution_raise_on_error = True

# API docs
autoapi_dirs = ["../src"]
autoapi_options = ["members", "undoc-members", "show-inheritance", "show-module-summary"]
autoapi_python_class_content = "both"
autodoc_typehints = "description"

# Napoleon
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = True

# Intersphinx
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable", None),
}

html_theme = "pydata_sphinx_theme"
```

**Docstring style:** Google, no types in `Args`/`Returns` (use PEP 484 annotations instead).

**Testing:** `pytest --doctest-modules src/` for unit-level examples; `pytest --nbval docs/notebooks/` for tutorial notebooks.

**Hosting:** Read the Docs for OSS; GitHub Pages + Actions for private/enterprise.

**AI readability:** Ship a `docs/llms.txt` (or root-level `llms.txt`) pointing agents at your autoapi-generated reference.

---

## Sources

- [Read the Docs: How to use Jupyter notebooks in Sphinx](https://docs.readthedocs.com/platform/latest/guides/jupyter.html)
- [MyST-NB: Text-based Notebooks](https://myst-nb.readthedocs.io/en/latest/authoring/text-notebooks.html)
- [MyST-NB: Execution Configuration](https://myst-nb.readthedocs.io/en/latest/computation/execute.html)
- [jupyter-cache Documentation](https://jupyter-cache.readthedocs.io/en/latest/)
- [Sphinx AutoAPI: Configuration Options](https://sphinx-autoapi.readthedocs.io/en/latest/reference/config.html)
- [Sphinx AutoAPI: GitHub](https://github.com/readthedocs/sphinx-autoapi)
- [sphinx.ext.napoleon: Sphinx docs](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html)
- [PEP 727 – Documentation in Annotated Metadata](https://peps.python.org/pep-0727/)
- [Effective Docstrings: Google vs NumPy vs reST (McGinnis, 2025-03-06)](https://mcginniscommawill.com/posts/2025-03-06-writing-effective-docstrings/)
- [Switching from Sphinx to MkDocs: Gains and Losses (Towards Data Science)](https://towardsdatascience.com/switching-from-sphinx-to-mkdocs-documentation-what-did-i-gain-and-lose-04080338ad38/)
- [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)
- [pydata-sparse: Maintenance and Docs Overhaul (Quansight Labs)](https://labs.quansight.org/blog/pydata-sparse-maintenance-and-docs-overhaul)
- [executablebooks: Revisiting nbsphinx vs MyST-NB for roadmap plans (Discussion #1035)](https://github.com/orgs/executablebooks/discussions/1035)
- [Generating beautiful Python API docs with Sphinx AutoAPI (bylr.info)](https://bylr.info/articles/2022/05/10/api-doc-with-sphinx-autoapi/)
- [llms.txt for Agent-Ready Docs (llms-txt.io)](https://llms-txt.io/)
- [API Docs for AI Agents: llms.txt Guide (Fern, May 2026)](https://buildwithfern.com/post/optimizing-api-docs-ai-agents-llms-txt-guide)
- [How to write agent-friendly API documentation (LogRocket)](https://blog.logrocket.com/how-write-agent-friendly-api-documentation/)
- [RTD Addons enabled by default · readthedocs/readthedocs.org #11474](https://github.com/readthedocs/readthedocs.org/issues/11474)
- [Deploying Sphinx documentation to GitHub Pages (CodeRefinery)](https://coderefinery.github.io/documentation/gh_workflow/)
- [Python doctest documentation](https://docs.python.org/3/library/doctest.html)
- [sphinx-autodoc-typehints on PyPI](https://pypi.org/project/sphinx-autodoc-typehints/)
