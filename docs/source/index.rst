pyclawd docs example
====================

This is a tiny, **real** documentation pipeline that exercises the full
``pyclawd docs`` flow: a markdown source is compiled to a notebook, executed
(and cached), and rendered to HTML. See :doc:`example` for a page with a live
code cell.

Build it from the repo root with::

    pyclawd docs build        # compile -> run -> render
    pyclawd docs serve        # view the result

.. toctree::
   :maxdepth: 1

   example
