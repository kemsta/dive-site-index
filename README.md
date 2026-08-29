# Dive Site Index

An open, source-grounded dive-site catalog with a multilingual data model, deterministic UDDF exports, and a static map/card interface for GitHub Pages.

[Browse the catalog](https://kemsta.github.io/dive-site-index/) · [Suggest or correct data](https://github.com/kemsta/dive-site-index/issues) · [Contribute](CONTRIBUTING.md) · [Data license](DATA_LICENSE.md)

## What this is

Dive Site Index is a community-editable catalog of dive sites. It gives sites stable identifiers, multilingual names and descriptions, coordinates, depth and difficulty fields, access and hazard notes, source references, and downloadable UDDF records. The same data can be browsed on the website or reused in other applications.

The catalog is informational. It is not a dive briefing and does not replace training, a qualified local guide, current weather/current/tide checks, local regulations, or site-specific risk assessment.

## Use, contribute, or report a problem

- **Add a site or translation:** follow [`CONTRIBUTING.md`](CONTRIBUTING.md) or use the new-site issue template.
- **Correct a record:** edit its YAML in a pull request or open [GitHub Issues](https://github.com/kemsta/dive-site-index/issues) with the site URL, proposed correction, and supporting source.
- **Report a website/export bug:** use the bug-report issue template.
- **Report a security problem privately:** follow [`SECURITY.md`](SECURITY.md).
- **Reuse the data commercially:** allowed under ODC-By 1.0 with attribution; see [`DATA_LICENSE.md`](DATA_LICENSE.md) for required wording and scope.

## Data flow

```text
external sources → normalized claims → human reconciliation → canonical catalog
                                                        ↓
                                  global/country/region/site UDDF + HTML
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
├── exports/uddf/countries/<country>/regions/<region>.uddf
└── exports/uddf/sites/<site-id>.uddf
```

The HTML includes an OpenStreetMap-backed MapLibre map, search, filters, country and region pages, and multilingual site cards. Every catalog level links to its own UDDF export. English and Russian interface/content are available throughout; the initial language follows the browser's ordered language preferences until the reader chooses one explicitly. The top theme control defaults to `auto` and can be changed to light or dark. No media model or media URLs are included in this MVP.

Every build applies the repository JSON Schemas, validates BCP-47 locale tags, rejects unsafe IDs and non-HTTP(S) source URLs, and validates each generated UDDF document against the vendored UDDF 3.2.3 XSD.

## Seed catalog

The initial catalog contains 21 reviewed records in Egypt / South Sinai reconstructed from source research and Garmin FIT observations. Canonical site coordinates remain separate from observation coordinates. Probable and user-defined identities remain explicit.

## Licensing

- Catalog database: ODC-By 1.0, including commercial use with required attribution; see [`DATA_LICENSE.md`](DATA_LICENSE.md) and [`LICENSE-DATA`](LICENSE-DATA).
- Code and repository documentation: MIT, see [`LICENSE`](LICENSE).
- Third-party sources, libraries, MapLibre, UDDF, and OpenStreetMap retain their own rights and terms. OpenStreetMap tiles/data are © OpenStreetMap contributors and subject to the applicable OpenStreetMap terms and ODbL.
