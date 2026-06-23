---
jupytext:
  text_representation:
    format_name: markdown
kernelspec:
  display_name: Python 3
  name: python3
---

# An executed example page

This `.md` file is the **source**. `pyclawd docs compile` converts it to
`example.ipynb` via jupytext, `pyclawd docs run` executes and caches it, and
nbsphinx renders the result — including the output of the code cell below.

```python
import sys

print("executed by the docs pipeline on Python", sys.version.split()[0])
squares = [n * n for n in range(6)]
squares
```

Because execution is cached (jupyter-cache), re-running `pyclawd docs build`
skips this cell unless the source changes. `pyclawd docs timings` shows how long
it took; `pyclawd docs failures` would flag it if the cell raised.
