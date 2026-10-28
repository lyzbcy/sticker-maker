# Development source snapshot for cross-machine builds

This branch captures local desktop and sticker-engine source and tests on top of GitHub main. It is not a published release, installer, or update manifest. The existing main branch and public version manifest are unchanged. Local production data, build outputs and historical evidence are not included. Existing remote-only files have not been deleted. Local docs and one-off operational scripts were not fully synchronized.

## Version discrepancy to resolve before release

The local snapshot contains desktop/package.json and package-lock.json 0.6.10, sticker_engine/sticker_engine/cli.py VERSION 0.6.10, but sticker_engine/pyproject.toml project.version 0.6.11. These values were copied as found; determine the intended version and align all four fields before building release artifacts. Do not publish 0.6.11 solely because the Python package metadata says so.

## Initial verification

- Desktop: cd desktop; npm ci; npm test
- Engine: cd sticker_engine; python -m pip install -e ".[dev]"; python -m pytest tests -q --ignore=tests/agent
- Review existing platform-specific build scripts and release documentation before creating distributables. A frontend build alone is not a complete packaged application; the frozen Python engine, platform installer, version metadata and update manifests must be checked independently.