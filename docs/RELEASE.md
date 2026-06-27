# Release Checklist

Marqflow is early-stage, but releases should still be repeatable.

## Local Verification

Run:

```bash
npm ci
npm run build
npm run typecheck
uv sync --group dev
uv run ruff check src tests
uv run pytest -q
uv build
```

The browser serves compiled JavaScript from
`src/marqflow/static/gallery.js`. Edit `gallery.ts`, then run
`npm run build` before committing.

## Optional Irregular Nesting Backend

The default install uses the deterministic Shapely shelf fallback. For the
external libnest2d backend on supported platforms:

```bash
uv sync --extra nesting
```

`python-libnest2d` currently publishes wheels for Linux and Windows, not macOS.
On unsupported platforms, Marqflow automatically falls back to
`shapely-polygon-shelf-rotating`.

Pack manifests record:

- `preferred_backend`
- `packing_backend`
- `fallback_backend`

This makes backend behavior explicit in exported artifacts.

## Versioning

Before tagging:

1. Update `version` in `pyproject.toml`.
2. Run the full local verification checklist.
3. Confirm `git status --short` is clean.
4. Tag the release:

   ```bash
   git tag vX.Y.Z
   git push origin main --tags
   ```

## CI

GitHub Actions runs:

- browser build
- TypeScript typecheck
- Ruff
- pytest

The CI path intentionally uses the default dependency set so it remains
portable. Add a separate Linux-only optional-nesting job when the external
backend becomes required rather than opportunistic.

