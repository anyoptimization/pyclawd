"""pyclawd — a project-generic developer-toolkit CLI.

pyclawd provides run/test/build/docs/doctor workflows driven by a per-project
configuration file (``.pyclawd/config.py``). The public API exposes the
configuration model and loader so adopting projects can describe themselves:

- :class:`Project` and the nested :class:`DocsConfig`, :class:`TestConfig`,
  :class:`DoctorConfig`, :class:`QualityConfig`, :class:`CoverageConfig`, and
  :class:`DescriptionConfig` config groups.
- :func:`load_project` / :func:`find_config_file` to discover and load a project.
- :class:`Check` and the :data:`OK` / :data:`WARN` / :data:`FAIL` status
  constants used by the ``doctor`` health-check hook.

A project's ``.pyclawd/config.py`` does ``from pyclawd import Project`` and defines a
module-level ``project = Project(...)``.
"""

from __future__ import annotations

from .discovery import ConfigError, find_config_file, load_project, set_config_override
from .project import (
    FAIL,
    OK,
    WARN,
    Check,
    CoverageConfig,
    DescriptionConfig,
    DocsConfig,
    DoctorConfig,
    GoldenConfig,
    Project,
    QualityConfig,
    TestConfig,
)

__version__ = "0.1.0"

__all__ = [
    "FAIL",
    "OK",
    "WARN",
    "Check",
    "ConfigError",
    "CoverageConfig",
    "DescriptionConfig",
    "DocsConfig",
    "DoctorConfig",
    "GoldenConfig",
    "Project",
    "QualityConfig",
    "TestConfig",
    "__version__",
    "find_config_file",
    "load_project",
    "set_config_override",
]
