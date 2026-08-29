# Architecture

## Three deliberately separate layers

### 1. Source claims

Collectors normalize one assertion at a time into `claims/<source-ref>/<claim-id>.yaml`. A claim identifies the source, retrieval time, subject hint, target field, optional locale, value, evidence, and review status.

Claims may conflict. They are not merged by recency and do not affect public exports merely because a collector wrote them. Raw snapshots can later be retained beside normalized claims when source licenses permit it.

### 2. Canonical catalog

Reviewed files under `catalog/` are hand-editable YAML and the sole publishing source. Stable IDs are independent of names and languages. Each site belongs to an explicit country and region and retains:

- canonical coordinates;
- localized names and content keyed by BCP-47 tags;
- identity kind and confidence;
- depth and classification;
- normal source references;
- separately recorded observations.

Canonical coordinates and observation coordinates are different concepts. User-defined or unresolved points are never silently promoted to recognized sites.

### 3. Generated publication

`scripts/build.py` validates the whole catalog before creating anything. JSON Schemas enforce each document shape, `langcodes` validates BCP-47 tags, hierarchy IDs must match their directories, source links are restricted to HTTP(S), and duplicate IDs are rejected before dictionary construction. It generates a complete index plus deterministic country and region subsets from the same in-memory graph. Generated files are disposable CI artifacts and are not manually edited.

Initial public adapters are:

- UDDF 3.2.3: global, country, and region files, validated against the vendored official schema;
- HTML: global map, country pages, region pages, and multilingual site cards.

Other formats can be added as adapters after the canonical schema stabilizes. They should never become parallel editable sources.

## Language fallback

A record may contain any valid BCP-47 locale. `en` is preferred when available; otherwise the lexically first available locale is the deterministic fallback. Each localized content block is complete (`summary`, `access`, `hazards`, and `marine_life`) so the UI never assembles a partially translated paragraph from unrelated languages.

UDDF has no general field-level localization mechanism. The publisher writes the preferred locale to the standard site fields and preserves additional locales as explicitly labeled `notes/para` entries.

## Reconciliation contract

A future reconciliation command should:

1. group claims by candidate identity;
2. calculate distance/name/source evidence without merging automatically;
3. report field-level conflicts;
4. propose a patch to canonical YAML;
5. require review through a pull request;
6. retain accepted claim IDs in the review record.

A mined assertion must retain its source and must not silently overwrite a hand-curated value.

## Media boundary

Media assets, image search, image licensing, and media-source references are intentionally excluded from schema version 1.0. They will be designed separately so licensing and exact-site identity can be enforced rather than retrofitted.
