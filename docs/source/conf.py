# Minimal Sphinx config for the pyclawd docs example (nbsphinx renders notebooks).
import os

project = "pyclawd docs example"
author = "pyclawd"

# nbsphinx renders the .ipynb produced by `pyclawd-docs compile`. Execution is done
# separately by `pyclawd-docs run` (jupyter-cache), so Sphinx never executes.
extensions = ["nbsphinx"]
nbsphinx_execute = "never"

master_doc = "index"
html_theme = "alabaster"

# .md files are jupytext *sources* (compiled to .ipynb); exclude the raw .md so
# Sphinx renders the notebooks, not the markdown.
exclude_patterns = ["build", "**.ipynb_checkpoints", "**/*.md"]

# `pyclawd docs build --fast` sets this to drop notebooks for a seconds-fast
# render of the Sphinx pipeline (toctree warnings for the excluded pages expected).
if os.environ.get("PYCLAWD_DOCS_FAST"):
    exclude_patterns.append("**/*.ipynb")
