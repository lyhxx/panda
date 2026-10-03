"""Single source of truth for the package version.

panda_cli, panda_pack and panda_infer re-export it, and pyproject.toml reads
it through setuptools' dynamic version, so a release only ever edits this one
file.
"""

__version__ = "1.0.0"
