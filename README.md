# Dive Site Index

An open, source-grounded dive-site catalog with a canonical multilingual source model, deterministic UDDF exports, and a static map/card interface for GitHub Pages.

## Data flow

```text
external sources → normalized claims → human reconciliation → canonical catalog
                                                        ↓
                                      global/country/region UDDF + HTML
```

- `claims/` stores mined, source-specific assertions. The publisher never treats them as canonical automatically.
- `catalog/` stores reviewed YAML and is the only publishing source of truth.
- `public/` is generated, ignored by Git, and rebuilt by CI.
- `schemas/` defines canonical sites and normalized claims.

## Canonical hierarchy

```text
catalog/countries/<country-id>/
├── country.yaml
└── regions/<region-id>/
    ├── region.yaml
    └── sites/<stable-site-id>.yaml
```

Names and descriptive content are keyed by BCP-47 language tags:

```yaml
names:
  en: Jackson Reef
  ru: Риф Джексон
content:
  en:
    summary: ...
    access: ...
    hazards: ...
    marine_life: ...
  ru:
    summary: ...
    access: ...
    hazards: ...
    marine_life: ...
```

A site may start with one locale and gain reviewed translations incrementally. Stable identity never depends on a translated or operator-specific name.

## Build

Requires Python 3.11+.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python -m unittest tests.test_build -v
dive-site-build
```

With `uv`:

```bash
uv run python -m unittest tests.test_build -v
uv run dive-site-build
```

Generated artifacts:

```text
public/
├── index.html
├── countries/<country>/index.html
├── countries/<country>/regions/<region>/index.html
├── sites/<site-id>/index.html
├── exports/uddf/all.uddf
├── exports/uddf/countries/<country>.uddf
└── exports/uddf/countries/<country>/regions/<region>.uddf
```

The HTML includes an OpenStreetMap-backed MapLibre map, search, filters, country and region pages, and multilingual site cards. No media model or media URLs are included in this MVP.

Every build applies the repository JSON Schemas, validates BCP-47 locale tags, rejects unsafe IDs and non-HTTP(S) source URLs, and validates each generated UDDF document against the vendored UDDF 3.2.3 XSD.

## Seed catalog

The initial catalog contains 21 reviewed records in Egypt / South Sinai reconstructed from source research and Garmin FIT observations. Canonical site coordinates remain separate from observation coordinates. Probable and user-defined identities remain explicit.

## Licensing

- Code: MIT, see `LICENSE`.
- Catalog compilation: ODbL 1.0. Individual source rights and attribution still apply; source references are retained in `catalog/sources.yaml` and each canonical site record.
- OpenStreetMap tiles/data: © OpenStreetMap contributors, ODbL.
