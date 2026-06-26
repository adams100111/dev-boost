# devboost (typed engine)

The strictly-typed Python engine for dev-boost. See
`specs/014-python-engine-core/` for the spec, plan, and tasks, and
`docs/superpowers/specs/2026-06-26-python-engine-migration-design.md` for the design.

```bash
uv sync
uv run devboost --help
uv run pytest
uv run mypy --strict
uv run ruff check
```
