#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import shutil
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit
from xml.dom import minidom

import jsonschema
import langcodes
import yaml
from lxml import etree


ROOT = pathlib.Path(__file__).resolve().parents[1]
ID_RE = re.compile(r"^[a-z][a-z0-9_-]+$")
SCHEMA_DIR = ROOT / "schemas"
UDDF_XSD = SCHEMA_DIR / "vendor" / "uddf-3.2.3.xsd"
UDDF_NS = "http://www.streit.cc/uddf/3.2/"
ET.register_namespace("", UDDF_NS)


def schema_validator(name: str) -> jsonschema.Draft202012Validator:
    schema = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())


VALIDATORS = {
    "country": schema_validator("country.schema.json"),
    "region": schema_validator("region.schema.json"),
    "site": schema_validator("site.schema.json"),
    "sources": schema_validator("sources.schema.json"),
}


def validate_document(document: dict, kind: str, label: str) -> None:
    errors = sorted(VALIDATORS[kind].iter_errors(document), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        path = ".".join(str(part) for part in error.absolute_path)
        location = f".{path}" if path else ""
        raise ValueError(f"{label}{location}: {error.message}")


def validate_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError(f"{label}: invalid safe id {value!r}")
    return value


def validate_locale(locale: object, label: str) -> str:
    if not isinstance(locale, str) or not langcodes.tag_is_valid(locale):
        raise ValueError(f"{label}: invalid BCP-47 locale {locale!r}")
    return locale


def validate_source_url(url: object, label: str) -> str:
    if not isinstance(url, str):
        raise ValueError(f"{label}: source URL must be a string")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label}: source URL must use http or https")
    return url


def read_yaml(path: pathlib.Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a YAML mapping")
    return value


def load_catalog(catalog_dir: pathlib.Path) -> dict:
    catalog_dir = pathlib.Path(catalog_dir)
    sources_doc = read_yaml(catalog_dir / "sources.yaml")
    validate_document(sources_doc, "sources", "sources.yaml")
    sources: dict[str, dict] = {}
    for source in sources_doc["sources"]:
        source_id = validate_id(source["id"], "source id")
        if source_id in sources:
            raise ValueError(f"duplicate source id {source_id}")
        validate_source_url(source["url"], source_id)
        sources[source_id] = source
    countries: dict[str, dict] = {}
    countries_dir = catalog_dir / "countries"
    for country_path in sorted(countries_dir.glob("*/country.yaml")):
        country = read_yaml(country_path)
        validate_document(country, "country", str(country_path))
        country_id = validate_id(country["id"], str(country_path))
        if country_id != country_path.parent.name:
            raise ValueError(f"{country_path}: id must match directory name {country_path.parent.name!r}")
        if country_id in countries:
            raise ValueError(f"duplicate country id {country_id}")
        validate_localized_strings(country["names"], f"country.{country_id}.names")
        if country["default_locale"] not in country["names"]:
            raise ValueError(f"country.{country_id}: default_locale must exist in names")
        country["regions"] = {}
        region_root = country_path.parent / "regions"
        for region_path in sorted(region_root.glob("*/region.yaml")):
            region = read_yaml(region_path)
            validate_document(region, "region", str(region_path))
            region_id = validate_id(region["id"], str(region_path))
            if region_id != region_path.parent.name:
                raise ValueError(f"{region_path}: id must match directory name {region_path.parent.name!r}")
            if region_id in country["regions"]:
                raise ValueError(f"duplicate region id {country_id}/{region_id}")
            if region["country_id"] != country_id:
                raise ValueError(f"{region_path}: country_id hierarchy mismatch")
            validate_localized_strings(region["names"], f"region.{region_id}.names")
            validate_localized_strings(region["body_of_water"]["names"], f"region.{region_id}.body_of_water.names")
            if region["default_locale"] not in region["names"]:
                raise ValueError(f"region.{region_id}: default_locale must exist in names")
            sites = []
            for site_path in sorted((region_path.parent / "sites").glob("*.yaml")):
                site = read_yaml(site_path)
                validate_site(site, country_id, region_id, set(sources))
                if site["id"] != site_path.stem:
                    raise ValueError(f"{site_path}: id must match filename")
                sites.append(site)
            region["sites"] = sites
            country["regions"][region_id] = region
        countries[country_id] = country
    return {"countries": countries, "sources": sources}


def validate_localized_strings(value: object, field: str) -> None:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{field} must be a non-empty locale mapping")
    for locale, text in value.items():
        validate_locale(locale, field)
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{field}.{locale} must be a non-empty string")


def validate_site(site: dict, country_id: str, region_id: str, source_ids: set[str] | None = None) -> None:
    validate_document(site, "site", site.get("id", "site"))
    validate_id(site["id"], "site id")
    identity = site["identity"]
    if identity.get("kind") not in {"canonical", "user-defined"}:
        raise ValueError(f"{site['id']}: invalid identity kind")
    if identity.get("confidence") not in {"confirmed", "probable", "user-confirmed", "unresolved"}:
        raise ValueError(f"{site['id']}: invalid confidence")
    validate_localized_strings(site["names"], f"{site['id']}.names")
    content = site["content"]
    if not isinstance(content, dict) or not content:
        raise ValueError(f"{site['id']}.content must contain at least one locale")
    for locale, block in content.items():
        validate_locale(locale, f"{site['id']}.content")
        if not isinstance(block, dict):
            raise ValueError(f"{site['id']}.content.{locale} must be a mapping")
        for key in ("summary", "access", "hazards", "marine_life"):
            if not isinstance(block.get(key), str):
                raise ValueError(f"{site['id']}.content.{locale}.{key} must be a string")
        if not block["summary"].strip():
            raise ValueError(f"{site['id']}.content.{locale}.summary is required")
    geography = site["geography"]
    if geography.get("country_id") != country_id or geography.get("region_id") != region_id:
        raise ValueError(f"{site['id']}: geography hierarchy mismatch")
    coordinates = geography.get("coordinates", {})
    lat, lon = coordinates.get("latitude"), coordinates.get("longitude")
    if not isinstance(lat, (int, float)) or not -90 <= lat <= 90:
        raise ValueError(f"{site['id']}: invalid latitude")
    if not isinstance(lon, (int, float)) or not -180 <= lon <= 180:
        raise ValueError(f"{site['id']}: invalid longitude")
    depth = site["depth"]
    minimum, maximum = depth.get("minimum_m"), depth.get("maximum_m")
    if minimum is not None and (not isinstance(minimum, (int, float)) or minimum < 0):
        raise ValueError(f"{site['id']}: invalid minimum depth")
    if maximum is not None and (not isinstance(maximum, (int, float)) or maximum < 0):
        raise ValueError(f"{site['id']}: invalid maximum depth")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError(f"{site['id']}: minimum depth exceeds maximum")
    if source_ids is not None:
        unknown = set(site["source_refs"]) - source_ids
        if unknown:
            raise ValueError(f"{site['id']}: unknown source refs {sorted(unknown)}")


def validate_catalog(catalog: dict) -> None:
    if not catalog["countries"]:
        raise ValueError("catalog has no countries")
    seen_ids: set[str] = set()
    source_ids = set(catalog["sources"])
    for source_id, source in catalog["sources"].items():
        validate_id(source_id, "source id")
        validate_source_url(source.get("url"), source_id)
    for country_id, country in catalog["countries"].items():
        validate_id(country_id, "country id")
        if country_id != country.get("id") or not country.get("regions"):
            raise ValueError(f"invalid or empty country {country_id}")
        validate_localized_strings(country.get("names"), f"country.{country_id}.names")
        for region_id, region in country["regions"].items():
            validate_id(region_id, "region id")
            if region_id != region.get("id") or region.get("country_id") != country_id:
                raise ValueError(f"invalid region {country_id}/{region_id}")
            validate_localized_strings(region.get("names"), f"region.{region_id}.names")
            for site in region["sites"]:
                validate_site(site, country_id, region_id, source_ids)
                if site["id"] in seen_ids:
                    raise ValueError(f"duplicate site id {site['id']}")
                seen_ids.add(site["id"])


def preferred_locale(localized: dict, default: str = "en") -> str:
    return default if default in localized else sorted(localized)[0]


def localized_name(entity: dict, locale: str = "en") -> str:
    names = entity["names"]
    return names.get(locale) or names[preferred_locale(names)]


def all_sites(catalog: dict) -> list[dict]:
    result: list[dict] = []
    for country in catalog["countries"].values():
        for region in country["regions"].values():
            result.extend(region["sites"])
    return sorted(result, key=lambda item: localized_name(item).casefold())


def add(parent: ET.Element, name: str, value: object) -> ET.Element:
    element = ET.SubElement(parent, f"{{{UDDF_NS}}}{name}")
    element.text = str(value)
    return element


def build_uddf(sites: list[dict], countries: dict, sources: dict, destination: pathlib.Path) -> None:
    root = ET.Element(f"{{{UDDF_NS}}}uddf", {"version": "3.2.3"})
    generator = ET.SubElement(root, f"{{{UDDF_NS}}}generator")
    add(generator, "name", "Dive Site Index canonical publisher")
    add(generator, "type", "converter")
    add(generator, "version", "0.1.0")
    divesite = ET.SubElement(root, f"{{{UDDF_NS}}}divesite")
    for site in sorted(sites, key=lambda item: localized_name(item).casefold()):
        country = countries[site["geography"]["country_id"]]
        region = country["regions"][site["geography"]["region_id"]]
        locale = preferred_locale(site["content"])
        content = site["content"][locale]
        element = ET.SubElement(divesite, f"{{{UDDF_NS}}}site", {"id": site["id"]})
        add(element, "name", localized_name(site, locale))
        for alias in site["aliases"]:
            add(element, "aliasname", alias)
        add(element, "environment", "ocean-sea")
        geography = ET.SubElement(element, f"{{{UDDF_NS}}}geography")
        coordinates = site["geography"]["coordinates"]
        water_name = region["body_of_water"]["names"].get(
            locale,
            region["body_of_water"]["names"].get("en", region["body_of_water"]["id"]),
        )
        add(geography, "location", f"{water_name}, {localized_name(region, locale)}")
        address = ET.SubElement(geography, f"{{{UDDF_NS}}}address")
        add(address, "country", localized_name(country, locale))
        add(address, "province", localized_name(region, locale))
        add(geography, "latitude", f"{coordinates['latitude']:.6f}")
        add(geography, "longitude", f"{coordinates['longitude']:.6f}")

        sitedata = ET.SubElement(element, f"{{{UDDF_NS}}}sitedata")
        difficulty_values = {"beginner": 3, "intermediate": 5, "advanced": 7}
        if site["difficulty"]:
            add(sitedata, "difficulty", difficulty_values[site["difficulty"]])
        if site["depth"]["maximum_m"] is not None:
            add(sitedata, "maximumdepth", site["depth"]["maximum_m"])
        if site["depth"]["minimum_m"] is not None:
            add(sitedata, "minimumdepth", site["depth"]["minimum_m"])

        paragraphs = [
            content["summary"],
            f"Access: {content['access']}",
            f"Hazards: {content['hazards']}",
            f"Marine life: {content['marine_life']}",
            f"Canonical ID: {site['id']}",
            f"Identity: {site['identity']['kind']} ({site['identity']['confidence']})",
            f"Difficulty: {site['difficulty'] or 'not assigned'}",
            "Site types: " + ", ".join(site["classification"]["types"]),
        ]
        for other_locale in sorted(site["content"]):
            if other_locale == locale:
                continue
            block = site["content"][other_locale]
            paragraphs.extend([
                f"[{other_locale}] {localized_name(site, other_locale)}",
                block["summary"],
                f"Access: {block['access']}",
                f"Hazards: {block['hazards']}",
                f"Marine life: {block['marine_life']}",
            ])
        urls = [sources[ref]["url"] for ref in site["source_refs"] if ref in sources]
        if urls:
            paragraphs.append("Sources: " + " ; ".join(urls))
        notes = ET.SubElement(element, f"{{{UDDF_NS}}}notes")
        for paragraph in paragraphs:
            add(notes, "para", paragraph)
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding="UTF-8")
    destination.write_bytes(pretty)
    schema = etree.XMLSchema(etree.parse(str(UDDF_XSD)))
    document = etree.parse(str(destination))
    if not schema.validate(document):
        raise ValueError(f"Generated UDDF is invalid: {schema.error_log}")


def escape_json_for_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def site_map_payload(sites: list[dict]) -> list[dict]:
    result = []
    for site in sites:
        locale = preferred_locale(site["content"])
        result.append({
            "id": site["id"],
            "name": localized_name(site, locale),
            "latitude": site["geography"]["coordinates"]["latitude"],
            "longitude": site["geography"]["coordinates"]["longitude"],
            "types": site["classification"]["types"],
            "difficulty": site["difficulty"],
            "confidence": site["identity"]["confidence"],
        })
    return result


def depth_label(site: dict) -> str:
    minimum, maximum = site["depth"]["minimum_m"], site["depth"]["maximum_m"]
    if minimum is None or maximum is None:
        return "Not assigned"
    return f"{minimum:g}–{maximum:g} m"


def site_card(site: dict, prefix: str) -> str:
    locale = preferred_locale(site["content"])
    name = html.escape(localized_name(site, locale))
    summary = html.escape(site["content"][locale]["summary"])
    types = " ".join(html.escape(value) for value in site["classification"]["types"][:3])
    tags = "".join(f'<span class="chip">{html.escape(value)}</span>' for value in site["classification"]["types"][:3])
    return f'''<article class="site-card" data-name="{name.casefold()}" data-types="{types.casefold()}" data-difficulty="{html.escape(site['difficulty'] or 'unassigned')}">
  <div class="card-top"><span class="eyebrow">{html.escape(site['identity']['confidence'])}</span><span class="depth">{depth_label(site)}</span></div>
  <h3><a href="{prefix}sites/{site['id']}/">{name}</a></h3>
  <p>{summary}</p>
  <div class="chips">{tags}</div>
</article>'''


def layout(*, title: str, body: str, prefix: str, site_data: list[dict] | None = None, description: str = "Open canonical dive-site index", lang: str = "en") -> str:
    data = ""
    maplibre = ""
    if site_data is not None:
        data = f'<script id="site-data" type="application/json">{escape_json_for_script(site_data)}</script>'
        maplibre = '<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@5.6.1/dist/maplibre-gl.css" integrity="sha384-Nq6PQ+9vJPvw7U/VfDELyrWoGQMsy0gi6QShhaSrGzkpF5KkM40csg2leky+YMTd" crossorigin="anonymous"><script defer src="https://unpkg.com/maplibre-gl@5.6.1/dist/maplibre-gl.js" integrity="sha384-/L1njH4bbgNt9Uk3HwJ272N9fxJzRBQCxhtwGkZiqgl+Nxpq2ETUNZhNMNV1RgyW" crossorigin="anonymous"></script>'
    return f'''<!doctype html>
<html lang="{html.escape(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="{html.escape(description)}">
  <title>{html.escape(title)} · Dive Site Index</title>
  {maplibre}
  <link rel="stylesheet" href="{prefix}assets/styles.css">
  <script defer src="{prefix}assets/app.js"></script>
</head>
<body>
  <header class="topbar"><a class="brand" href="{prefix}"><span class="brand-mark">◉</span>Dive Site Index</a><nav><a href="{prefix}exports/uddf/all.uddf">UDDF</a><a href="https://github.com/kemsta/dive-site-index">GitHub</a></nav></header>
  {body}
  <footer><span>Canonical data, explicit provenance, reviewable changes.</span><span>Map © OpenStreetMap contributors.</span></footer>
  {data}
</body>
</html>
'''


def listing_controls(sites: list[dict]) -> str:
    difficulties = sorted({site["difficulty"] for site in sites if site["difficulty"]})
    options = "".join(f'<option value="{html.escape(value)}">{html.escape(value.title())}</option>' for value in difficulties)
    return f'''<div class="controls">
  <label class="search"><span>Search</span><input id="search" type="search" placeholder="Name, description or type" autocomplete="off"></label>
  <label><span>Difficulty</span><select id="difficulty-filter"><option value="">All levels</option>{options}</select></label>
  <span id="result-count" class="result-count">{len(sites)} sites</span>
</div>'''


def map_panel() -> str:
    return '''<section class="map-panel"><div class="map-heading"><div><span class="eyebrow">Geographic index</span><h2>Explore the map</h2></div><p>Canonical coordinates are distinct from personal observations.</p></div><div id="map" aria-label="Interactive dive-site map"></div></section>'''


def listing_page(title: str, eyebrow: str, intro: str, sites: list[dict], prefix: str, breadcrumbs: str, extra: str = "") -> str:
    cards = "\n".join(site_card(site, prefix) for site in sites)
    body = f'''<main>
  <section class="hero compact">{breadcrumbs}<span class="eyebrow">{html.escape(eyebrow)}</span><h1>{html.escape(title)}</h1><p>{html.escape(intro)}</p><div class="stat-row"><div><strong>{len(sites)}</strong><span>sites</span></div><div><strong>{len({s['identity']['confidence'] for s in sites})}</strong><span>confidence states</span></div><div><strong>{sum(len(s['observations']) for s in sites)}</strong><span>observations</span></div></div></section>
  {extra}
  {map_panel()}
  <section class="directory"><div class="section-heading"><div><span class="eyebrow">Directory</span><h2>Site cards</h2></div></div>{listing_controls(sites)}<div id="site-list" class="site-grid">{cards}</div><p id="empty-state" class="empty" hidden>No sites match these filters.</p></section>
</main>'''
    return layout(title=title, body=body, prefix=prefix, site_data=site_map_payload(sites), description=intro)


def build_site_page(site: dict, country: dict, region: dict, sources: dict, out: pathlib.Path) -> None:
    initial_locale = preferred_locale(site["content"])
    locales = [initial_locale, *sorted(locale for locale in site["content"] if locale != initial_locale)]
    locale_buttons = "".join(
        f'<button class="locale-button{" active" if i == 0 else ""}" data-locale-target="{html.escape(locale)}">{html.escape(locale.upper())}</button>'
        for i, locale in enumerate(locales)
    )
    sections = []
    for i, locale in enumerate(locales):
        block = site["content"][locale]
        sections.append(f'''<section class="locale-content" data-locale="{html.escape(locale)}"{" hidden" if i else ""}>
  <h1>{html.escape(localized_name(site, locale))}</h1>
  <p class="lede">{html.escape(block['summary'])}</p>
  <div class="detail-grid"><article><span class="eyebrow">Access</span><p>{html.escape(block['access'])}</p></article><article><span class="eyebrow">Hazards</span><p>{html.escape(block['hazards'])}</p></article><article><span class="eyebrow">Marine life</span><p>{html.escape(block['marine_life'])}</p></article></div>
</section>''')
    source_links = "".join(
        f'<li><a rel="noreferrer" href="{html.escape(sources[ref]["url"])}">{html.escape(sources[ref]["url"])}</a></li>'
        for ref in site["source_refs"] if ref in sources
    ) or "<li>No external source identity is claimed.</li>"
    types = "".join(f'<span class="chip">{html.escape(value)}</span>' for value in site["classification"]["types"])
    coordinates = site["geography"]["coordinates"]
    body = f'''<main>
  <section class="detail-hero"><div class="breadcrumbs"><a href="../../">Index</a><span>/</span><a href="../../countries/{country['id']}/">{html.escape(localized_name(country))}</a><span>/</span><a href="../../countries/{country['id']}/regions/{region['id']}/">{html.escape(localized_name(region))}</a></div><div class="detail-head"><div><span class="eyebrow">{html.escape(site['identity']['kind'])} · {html.escape(site['identity']['confidence'])}</span><div class="locale-switch" aria-label="Content language">{locale_buttons}</div>{''.join(sections)}</div><aside class="facts"><div><span>Depth</span><strong>{depth_label(site)}</strong></div><div><span>Difficulty</span><strong>{html.escape((site['difficulty'] or 'Not assigned').title())}</strong></div><div><span>Coordinates</span><strong>{coordinates['latitude']:.6f}, {coordinates['longitude']:.6f}</strong></div><div><span>Observations</span><strong>{len(site['observations'])}</strong></div><div class="chips">{types}</div><a class="button" href="https://www.openstreetmap.org/?mlat={coordinates['latitude']}&mlon={coordinates['longitude']}#map=14/{coordinates['latitude']}/{coordinates['longitude']}">Open in OpenStreetMap</a></aside></div></section>
  <section class="sources"><span class="eyebrow">Provenance</span><h2>Source references</h2><ul>{source_links}</ul></section>
</main>'''
    destination = out / "sites" / site["id"] / "index.html"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(layout(title=localized_name(site, initial_locale), body=body, prefix="../../", description=site["content"][initial_locale]["summary"], lang=initial_locale), encoding="utf-8")


def build_all(catalog_dir: pathlib.Path, out_dir: pathlib.Path) -> dict:
    catalog = load_catalog(pathlib.Path(catalog_dir))
    validate_catalog(catalog)
    out = pathlib.Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    assets = out / "assets"
    assets.mkdir()
    shutil.copy2(ROOT / "web" / "styles.css", assets / "styles.css")
    shutil.copy2(ROOT / "web" / "app.js", assets / "app.js")

    sites = all_sites(catalog)
    build_uddf(sites, catalog["countries"], catalog["sources"], out / "exports" / "uddf" / "all.uddf")

    country_cards = []
    for country_id, country in sorted(catalog["countries"].items()):
        country_sites = sorted(
            [site for region in country["regions"].values() for site in region["sites"]],
            key=lambda item: localized_name(item).casefold(),
        )
        build_uddf(country_sites, catalog["countries"], catalog["sources"], out / "exports" / "uddf" / "countries" / f"{country_id}.uddf")
        region_links = "".join(
            f'<a class="region-link" href="regions/{region_id}/"><span>{html.escape(localized_name(region))}</span><strong>{len(region["sites"])}</strong></a>'
            for region_id, region in sorted(country["regions"].items())
        )
        country_page = listing_page(
            localized_name(country), "Country index", f"Canonical dive sites grouped across {len(country['regions'])} region(s).",
            country_sites, "../../", '<div class="breadcrumbs"><a href="../../">Index</a><span>/</span><span>Country</span></div>',
            f'<section class="region-strip"><div class="section-heading"><div><span class="eyebrow">Regions</span><h2>Browse subdivisions</h2></div></div><div class="region-links">{region_links}</div></section>',
        )
        country_destination = out / "countries" / country_id / "index.html"
        country_destination.parent.mkdir(parents=True, exist_ok=True)
        country_destination.write_text(country_page, encoding="utf-8")
        country_cards.append(f'<a class="country-card" href="countries/{country_id}/"><span class="eyebrow">{html.escape(country.get("iso_alpha2", country_id).upper())}</span><h2>{html.escape(localized_name(country))}</h2><p>{len(country_sites)} canonical sites · {len(country["regions"])} region</p><span class="arrow">↗</span></a>')

        for region_id, region in sorted(country["regions"].items()):
            region_sites = sorted(region["sites"], key=lambda item: localized_name(item).casefold())
            build_uddf(region_sites, catalog["countries"], catalog["sources"], out / "exports" / "uddf" / "countries" / country_id / "regions" / f"{region_id}.uddf")
            region_page = listing_page(
                localized_name(region), localized_name(country), f"Canonical dive-site index for {localized_name(region)}, {localized_name(country)}.",
                region_sites, "../../../../", f'<div class="breadcrumbs"><a href="../../../../">Index</a><span>/</span><a href="../../">{html.escape(localized_name(country))}</a><span>/</span><span>Region</span></div>',
            )
            region_destination = out / "countries" / country_id / "regions" / region_id / "index.html"
            region_destination.parent.mkdir(parents=True, exist_ok=True)
            region_destination.write_text(region_page, encoding="utf-8")
            for site in region_sites:
                build_site_page(site, country, region, catalog["sources"], out)

    home_body = f'''<main><section class="hero"><span class="eyebrow">Open canonical registry</span><h1>Dive sites,<br><em>grounded and reviewable.</em></h1><p>A multilingual source model for hand-edited canonical records, mined claims and reproducible UDDF/HTML publication.</p><div class="stat-row"><div><strong>{len(sites)}</strong><span>canonical sites</span></div><div><strong>{len(catalog['countries'])}</strong><span>country</span></div><div><strong>{sum(len(c['regions']) for c in catalog['countries'].values())}</strong><span>region</span></div></div></section><section class="country-section"><div class="section-heading"><div><span class="eyebrow">Geography</span><h2>Browse by country</h2></div><a class="button" href="exports/uddf/all.uddf">Download global UDDF</a></div><div class="country-grid">{''.join(country_cards)}</div></section>{map_panel()}<section class="directory"><div class="section-heading"><div><span class="eyebrow">All records</span><h2>Canonical site cards</h2></div></div>{listing_controls(sites)}<div id="site-list" class="site-grid">{''.join(site_card(site, '') for site in sites)}</div><p id="empty-state" class="empty" hidden>No sites match these filters.</p></section></main>'''
    (out / "index.html").write_text(layout(title="Open canonical registry", body=home_body, prefix="", site_data=site_map_payload(sites)), encoding="utf-8")
    return {
        "site_count": len(sites),
        "country_count": len(catalog["countries"]),
        "region_count": sum(len(country["regions"]) for country in catalog["countries"].values()),
        "output": str(out),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the static Dive Site Index")
    parser.add_argument("--catalog", type=pathlib.Path, default=ROOT / "catalog")
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "public")
    args = parser.parse_args()
    print(json.dumps(build_all(args.catalog, args.output), indent=2))


if __name__ == "__main__":
    main()
