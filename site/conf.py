"""Sphinx configuration for the magshield-env user documentation site."""

from __future__ import annotations

import os

project = "magshield-env"
author = "Vox Gu"
release = "0.1.0"
copyright = "2026, Vox Gu"

extensions = [
    "myst_parser",
    "sphinx.ext.duration",
    "sphinx.ext.githubpages",
]

source_suffix = {".md": "markdown"}
root_doc = "index"

# Chinese is the source of truth; English switches via READTHEDOCS_LANGUAGE.
language = os.environ.get("READTHEDOCS_LANGUAGE", "zh_CN")
locale_dirs = ["locales"]
gettext_compact = False

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "README.md"]

html_theme = "furo"
html_title = (
    "magshield-env 用户文档" if language == "zh_CN" else "magshield-env Documentation"
)
html_show_sourcelink = True

myst_enable_extensions = ["colon_fence"]
myst_heading_anchors = 3

linkcheck_ignore = [
    r"https://github.com/voxServalG/magshield-env/blob/main/",
]
