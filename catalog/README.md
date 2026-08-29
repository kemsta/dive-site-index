# Canonical catalog

The catalog is the only source used for public exports.

```text
catalog/
├── sources.yaml
└── countries/<country-id>/
    ├── country.yaml
    └── regions/<region-id>/
        ├── region.yaml
        └── sites/<site-id>.yaml
```

## Editing a site

- Keep `id` stable after publication.
- Use BCP-47 locale keys under `names` and `content`, for example `en`, `ru`, or `de-DE`.
- Every locale block is independent and contains `summary`, `access`, `hazards`, and `marine_life`.
- Preserve uncertainty through `identity.kind` and `identity.confidence`.
- Reference normal web sources by ID from `catalog/sources.yaml`.
- Keep mined claims in `claims/`; reconcile them through review instead of editing generated claims into place automatically.

Media is intentionally not modeled in version 1.0.
