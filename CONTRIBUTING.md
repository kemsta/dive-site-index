# Contributing

Dive Site Index is a public, multilingual catalog. Contributions may add sites, correct records, improve translations, or report problems. Published values are maintained in `catalog/`; source-specific research belongs in `claims/` until reviewed.

## Add a dive site

You may either [open a new-site issue](https://github.com/kemsta/dive-site-index/issues/new?template=new-site.yml) or submit a pull request.

For a pull request:

1. Find or add the country and region under `catalog/countries/<country-id>/regions/<region-id>/`.
2. Copy a nearby record from `sites/` and give the new file a stable ID such as `site_blue_hole.yaml`. IDs must not depend on a translated name or operator branding.
3. Provide coordinates, depth when known, classification, access, hazards, marine life, and at least one name and content locale. BCP-47 language tags such as `en`, `ru`, or `zh-Hant` are supported.
4. Cite reliable sources. Add each new source to `catalog/sources.yaml`, then reference its ID in `source_refs`.
5. Preserve uncertainty. Do not invent missing depth, difficulty, identity, access, or safety details.
6. Run the checks below and submit a focused pull request.

## Correct existing data

For a small correction, [open a data-correction issue](https://github.com/kemsta/dive-site-index/issues/new?template=data-correction.yml) with:

- the stable site page URL or site ID;
- the field that appears wrong;
- the proposed value;
- a supporting source or first-hand explanation;
- whether the issue could affect diver safety.

A pull request may edit the corresponding YAML record directly. Keep the stable `id` unchanged. Corrections to names or descriptions must not create a new URL. Add or update `source_refs` when the factual basis changes.

## Translations

Add a new BCP-47 locale beside existing entries. Translate meaning, not wording mechanically. Do not replace an existing language block, change factual values merely to simplify translation, or translate proper names without evidence that a localized name is established.

## Reports and complaints

- Wrong or missing catalog data: [GitHub Issues](https://github.com/kemsta/dive-site-index/issues) using the data templates.
- Website, map, export, or accessibility bug: use the bug-report template.
- Security vulnerability or accidental disclosure of private data: follow [`SECURITY.md`](SECURITY.md); do not publish exploit details in a public issue.
- Copyright, license, attribution, or other legal concern: open a GitHub issue with the affected URL and a way to contact you, but omit private or legally sensitive material. If private handling is needed, use GitHub’s private [Report a vulnerability](https://github.com/kemsta/dive-site-index/security/advisories/new) form.

Please be specific and civil. Reports can challenge any record; acceptance depends on verifiable evidence, licensing, scope, and review.

## Development checks

Requires Python 3.11+ and `uv`:

```bash
uv sync --frozen
uv run python -m unittest discover -s tests -v
uv run dive-site-build
node --check web/app.js
```

Do not commit `public/`; CI rebuilds and deploys it. Automated collectors must write normalized assertions under `claims/` and must never modify `catalog/` automatically.

## Contribution terms

By submitting a contribution, you represent that you have the right to provide it and agree that accepted code and documentation are available under MIT and accepted database contributions are available under ODC-By 1.0, as described in [`DATA_LICENSE.md`](DATA_LICENSE.md). Do not submit copied descriptions, images, or other material without permission.
