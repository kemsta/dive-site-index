# Contributing

## Canonical edits

1. Edit or add YAML under the correct `catalog/countries/<country>/regions/<region>/sites/` directory.
2. Keep published IDs stable.
3. Add normal reference metadata to `catalog/sources.yaml`, then use its ID in `source_refs`.
4. Add complete locale blocks; do not overwrite another language to create a translation.
5. Preserve uncertainty in `identity.kind` and `identity.confidence`.
6. Run `uv run python -m unittest tests.test_build -v` and `uv run dive-site-build`.
7. Submit the change through a pull request.

## Mined data

Collectors must write normalized claims under `claims/`, not canonical records. A collector refresh must never mutate `catalog/` directly. Review and reconciliation are separate steps.

## Generated output

Do not commit `public/`. GitHub Actions rebuilds and deploys it from canonical source files.
