# Source claims

Collectors write normalized, source-specific claims here. Claims are evidence, not canonical truth.

Recommended layout:

```text
claims/<source-ref>/<claim-id>.yaml
```

Each file must conform to `schemas/source-claim.schema.json`. The publisher intentionally ignores this directory. A reviewer or future reconciliation command compares claims with `catalog/`, then writes accepted values into the canonical site YAML through a normal pull request.

This separation prevents a crawler refresh from silently overwriting reviewed names, coordinates, descriptions, confidence decisions, or user-defined locations.

Media claims and media URLs are outside the MVP scope.
