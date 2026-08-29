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

TYPE_RU: dict[str, str] = {
    "Garmin observation": "наблюдение Garmin",
    "bay": "бухта",
    "boat dive": "погружение с лодки",
    "boat or liveaboard dive": "погружение с лодки или сафари-бота",
    "boat or shore dive": "погружение с лодки или берега",
    "canyon": "каньон",
    "coral blocks": "коралловые блоки",
    "coral garden": "коралловый сад",
    "coral pinnacles": "коралловые башни",
    "coral slope": "коралловый склон",
    "deep canyon": "глубокий каньон",
    "drift dive": "дрейфовое погружение",
    "drift or mooring dive": "дрейфовое погружение или погружение со швартовки",
    "drop-off": "свальный склон",
    "garden eels": "садовые угри",
    "historic wreck": "исторический рэк",
    "mooring dive": "погружение со швартовки",
    "mooring or drift dive": "погружение со швартовки или по течению",
    "night dive": "ночное погружение",
    "old jetty": "старый причал",
    "open-water boat entry": "вход с лодки в открытой воде",
    "optional penetration": "возможное проникновение",
    "optional swim-throughs": "необязательные сквозные проходы",
    "plateau": "плато",
    "reef": "риф",
    "sand": "песок",
    "sandy alley": "песчаная аллея",
    "sandy area": "песчаный участок",
    "sandy bay": "песчаная бухта",
    "sandy plateau": "песчаное плато",
    "sandy slope": "песчаный склон",
    "shallow wreck": "мелководный рэк",
    "sheltered mooring": "защищённая швартовка",
    "shore or boat dive": "погружение с берега или лодки",
    "slope": "склон",
    "snorkelling site": "место для снорклинга",
    "tidal passage": "приливный проход",
    "unidentified dive": "неидентифицированное погружение",
    "user-defined location": "пользовательская точка",
    "wall": "стенка",
    "wildlife encounter": "встреча с морскими животными",
    "wreck": "рэк",
    "wreck cargo": "груз рэка",
}
PUBLIC_EXCLUDED_TYPES = {"Garmin observation"}


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


def public_types(site: dict) -> list[str]:
    return [value for value in site["classification"]["types"] if value not in PUBLIC_EXCLUDED_TYPES]


def add(parent: ET.Element, name: str, value: object) -> ET.Element:
    element = ET.SubElement(parent, f"{{{UDDF_NS}}}{name}")
    element.text = str(value)
    return element


def build_uddf(sites: list[dict], countries: dict, sources: dict, destination: pathlib.Path) -> None:
    root = ET.Element(f"{{{UDDF_NS}}}uddf", {"version": "3.2.3"})
    generator = ET.SubElement(root, f"{{{UDDF_NS}}}generator")
    add(generator, "name", "Dive Site Index publisher")
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
            f"Site ID: {site['id']}",
            f"Difficulty: {site['difficulty'] or 'not assigned'}",
            "Site types: " + ", ".join(public_types(site)),
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
        result.append({
            "id": site["id"],
            "name_en": localized_name(site, "en"),
            "name_ru": localized_name(site, "ru"),
            "latitude": site["geography"]["coordinates"]["latitude"],
            "longitude": site["geography"]["coordinates"]["longitude"],
            "types_en": ", ".join(public_types(site)),
            "types_ru": ", ".join(TYPE_RU.get(str(value), str(value)) for value in public_types(site)),
            "difficulty": site["difficulty"],
        })
    return result


def depth_label(site: dict) -> str:
    minimum, maximum = site["depth"]["minimum_m"], site["depth"]["maximum_m"]
    if minimum is None or maximum is None:
        return "Not assigned"
    return f"{minimum:g}–{maximum:g} m"


def en_ru(mapping: dict[str, str]) -> dict[str, str]:
    english = mapping.get("en") or next(iter(mapping.values()))
    return {"en": english, "ru": mapping.get("ru", english)}


def l10n_attrs(mapping: dict[str, str]) -> str:
    values = en_ru(mapping)
    return f'data-l10n data-en="{html.escape(values["en"], quote=True)}" data-ru="{html.escape(values["ru"], quote=True)}"'


def site_card(site: dict, prefix: str) -> str:
    names = en_ru({locale: localized_name(site, locale) for locale in site["content"]})
    summaries = en_ru({locale: block["summary"] for locale, block in site["content"].items()})
    visible_types = public_types(site)
    types = " ".join(html.escape(value) for value in visible_types[:3])
    tags = "".join(
        f'<span class="chip" {l10n_attrs({"en": str(value), "ru": TYPE_RU.get(str(value), str(value))})}>{html.escape(value)}</span>'
        for value in visible_types[:3]
    )
    search_text = " ".join([*names.values(), *summaries.values()]).casefold()
    return f'''<a class="site-card" href="{prefix}sites/{site['id']}/" data-site-id="{site['id']}" data-name="{html.escape(search_text, quote=True)}" data-types="{types.casefold()}" data-difficulty="{html.escape(site['difficulty'] or 'unassigned')}">
  <div class="card-top"><span class="depth" {l10n_attrs({"en": depth_label(site), "ru": "Не указана" if depth_label(site) == "Not assigned" else depth_label(site)})}>{depth_label(site)}</span></div>
  <h3 {l10n_attrs(names)}>{html.escape(names['en'])}</h3>
  <p {l10n_attrs(summaries)}>{html.escape(summaries['en'])}</p>
  <div class="chips">{tags}</div>
</a>'''


def layout(*, title: str | dict[str, str], body: str, prefix: str, uddf_href: str, site_data: list[dict] | None = None, description: str | dict[str, str] = "Open dive-site index", available_locales: list[str] | None = None) -> str:
    data = ""
    maplibre = ""
    titles = en_ru(title if isinstance(title, dict) else {"en": title})
    descriptions = en_ru(description if isinstance(description, dict) else {"en": description})
    locales = list(dict.fromkeys(available_locales or ["en", "ru"]))
    locale_labels = {"en": "English", "ru": "Русский"}
    language_options = "".join(
        f'<option value="{html.escape(locale, quote=True)}">{html.escape(locale_labels.get(locale, locale.upper()))}</option>'
        for locale in locales
    )
    if site_data is not None:
        data = f'<script id="site-data" type="application/json">{escape_json_for_script(site_data)}</script>'
        maplibre = '<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@5.6.1/dist/maplibre-gl.css" integrity="sha384-Nq6PQ+9vJPvw7U/VfDELyrWoGQMsy0gi6QShhaSrGzkpF5KkM40csg2leky+YMTd" crossorigin="anonymous"><script defer src="https://unpkg.com/maplibre-gl@5.6.1/dist/maplibre-gl.js" integrity="sha384-/L1njH4bbgNt9Uk3HwJ272N9fxJzRBQCxhtwGkZiqgl+Nxpq2ETUNZhNMNV1RgyW" crossorigin="anonymous"></script>'
    return f'''<!doctype html>
<html lang="en" data-theme="auto">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="{html.escape(descriptions['en'])}" data-l10n-content data-en="{html.escape(descriptions['en'], quote=True)}" data-ru="{html.escape(descriptions['ru'], quote=True)}">
  <title {l10n_attrs({'en': titles['en'] + ' · Dive Site Index', 'ru': titles['ru'] + ' · Индекс дайв-сайтов'})}>{html.escape(titles['en'])} · Dive Site Index</title>
  <script>try{{document.documentElement.dataset.theme=localStorage.getItem("theme")||"auto"}}catch(_){{}}</script>
  {maplibre}
  <link rel="stylesheet" href="{prefix}assets/styles.css">
  <script defer src="{prefix}assets/app.js"></script>
</head>
<body>
  <header class="topbar"><a class="brand" href="{prefix}"><span class="brand-mark">◉</span><span data-i18n="brand">Dive Site Index</span></a><nav><a href="{uddf_href}" data-i18n="download_uddf">UDDF</a><a href="https://github.com/kemsta/dive-site-index">GitHub</a></nav><div class="preference-controls"><label><span data-i18n="language">Language</span><select id="language-select" aria-label="Language" data-i18n-aria="language">{language_options}</select></label><label><span data-i18n="theme">Theme</span><select id="theme-select" aria-label="Theme" data-i18n-aria="theme"><option value="auto" data-i18n="theme_auto">Auto</option><option value="light" data-i18n="theme_light">Light</option><option value="dark" data-i18n="theme_dark">Dark</option></select></label></div></header>
  {body}
  <footer><span data-i18n="footer_source">Open dive-site data with cited sources.</span><nav aria-label="Project information" data-i18n-aria="project_information"><a href="https://github.com/kemsta/dive-site-index#readme" data-i18n="about">About</a><a href="https://github.com/kemsta/dive-site-index/blob/main/CONTRIBUTING.md" data-i18n="contribute">Contribute</a><a href="https://github.com/kemsta/dive-site-index/issues" data-i18n="report_problem">Report a problem</a><a href="https://github.com/kemsta/dive-site-index/blob/main/DATA_LICENSE.md" data-i18n="data_license">Data license</a></nav><span data-i18n="footer_map">Map © OpenStreetMap contributors.</span></footer>
  {data}
</body>
</html>
'''


def listing_controls(sites: list[dict]) -> str:
    difficulties = sorted({site["difficulty"] for site in sites if site["difficulty"]})
    options = "".join(f'<option value="{html.escape(value)}" data-i18n="difficulty_{html.escape(value)}">{html.escape(value.title())}</option>' for value in difficulties)
    return f'''<div class="controls">
  <label class="search"><span data-i18n="search">Search</span><input id="search" type="search" placeholder="Name, description or type" data-i18n-placeholder="search_placeholder" autocomplete="off"></label>
  <label><span data-i18n="difficulty">Difficulty</span><select id="difficulty-filter"><option value="" data-i18n="all_levels">All levels</option>{options}</select></label>
  <span id="result-count" class="result-count" data-count="{len(sites)}">{len(sites)} sites</span>
</div>'''


def map_panel() -> str:
    return '''<section class="map-panel"><div class="map-heading"><div><span class="eyebrow" data-i18n="geographic_index">Geographic index</span><h2 data-i18n="explore_map">Explore the map</h2></div><p data-i18n="map_intro">Browse dive-site locations.</p></div><div id="map" aria-label="Interactive dive-site map" data-i18n-aria="map_aria"></div></section>'''


def listing_page(title: dict[str, str], eyebrow_key: str, intro: dict[str, str], sites: list[dict], prefix: str, breadcrumbs: str, uddf_href: str, extra: str = "") -> str:
    cards = "\n".join(site_card(site, prefix) for site in sites)
    type_count = len({site_type for site in sites for site_type in public_types(site)})
    language_count = len({locale for site in sites for locale in site["content"]})
    body = f'''<main>
  <section class="hero compact">{breadcrumbs}<span class="eyebrow" data-i18n="{eyebrow_key}">{html.escape(eyebrow_key.replace('_', ' ').title())}</span><h1 {l10n_attrs(title)}>{html.escape(en_ru(title)['en'])}</h1><p {l10n_attrs(intro)}>{html.escape(en_ru(intro)['en'])}</p><div class="stat-row"><div><strong>{len(sites)}</strong><span data-i18n="sites">sites</span></div><div><strong>{type_count}</strong><span data-i18n="site_types">site types</span></div><div><strong>{language_count}</strong><span data-i18n="languages">languages</span></div></div></section>
  {extra}
  {map_panel()}
  <section class="directory"><div class="section-heading"><div><span class="eyebrow" data-i18n="directory">Directory</span><h2 data-i18n="site_cards">Site cards</h2></div></div>{listing_controls(sites)}<div id="site-list" class="site-grid">{cards}</div><p id="empty-state" class="empty" data-i18n="no_matches" hidden>No sites match these filters.</p></section>
</main>'''
    return layout(title=title, body=body, prefix=prefix, uddf_href=uddf_href, site_data=site_map_payload(sites), description=intro)


def build_site_page(site: dict, country: dict, region: dict, sources: dict, out: pathlib.Path) -> None:
    locales = [locale for locale in ("en", "ru") if locale in site["content"]]
    locales.extend(sorted(locale for locale in site["content"] if locale not in locales))
    sections = []
    for i, locale in enumerate(locales):
        block = site["content"][locale]
        sections.append(f'''<section class="locale-content" data-locale="{html.escape(locale)}"{" hidden" if i else ""}>
  <h1>{html.escape(localized_name(site, locale))}</h1>
  <p class="lede">{html.escape(block['summary'])}</p>
  <div class="detail-grid"><article><span class="eyebrow" data-i18n="access">Access</span><p>{html.escape(block['access'])}</p></article><article><span class="eyebrow" data-i18n="hazards">Hazards</span><p>{html.escape(block['hazards'])}</p></article><article><span class="eyebrow" data-i18n="marine_life">Marine life</span><p>{html.escape(block['marine_life'])}</p></article></div>
</section>''')
    source_links = "".join(
        f'<li><a rel="noreferrer" href="{html.escape(sources[ref]["url"])}">{html.escape(sources[ref]["url"])}</a></li>'
        for ref in site["source_refs"] if ref in sources
    ) or "<li>No external sources listed.</li>"
    types = "".join(
        f'<span class="chip" {l10n_attrs({"en": str(value), "ru": TYPE_RU.get(str(value), str(value))})}>{html.escape(value)}</span>'
        for value in public_types(site)
    )
    coordinates = site["geography"]["coordinates"]
    country_names = en_ru(country["names"])
    region_names = en_ru(region["names"])
    difficulty_key = f"difficulty_{site['difficulty']}" if site["difficulty"] else "not_assigned"
    site_uddf = f"../../exports/uddf/sites/{site['id']}.uddf"
    body = f'''<main>
  <section class="detail-hero"><div class="breadcrumbs"><a href="../../" data-i18n="index">Index</a><span>/</span><a href="../../countries/{country['id']}/" {l10n_attrs(country_names)}>{html.escape(country_names['en'])}</a><span>/</span><a href="../../countries/{country['id']}/regions/{region['id']}/" {l10n_attrs(region_names)}>{html.escape(region_names['en'])}</a></div><div class="detail-head"><div><span class="eyebrow" data-i18n="dive_site">Dive site</span>{''.join(sections)}</div><aside class="facts"><div><span data-i18n="depth">Depth</span><strong>{depth_label(site)}</strong></div><div><span data-i18n="difficulty">Difficulty</span><strong data-i18n="{difficulty_key}">{html.escape((site['difficulty'] or 'Not assigned').title())}</strong></div><div><span data-i18n="coordinates">Coordinates</span><strong>{coordinates['latitude']:.6f}, {coordinates['longitude']:.6f}</strong></div><div class="chips">{types}</div><a class="button" href="{site_uddf}" data-i18n="download_site_uddf">Download site UDDF</a><a class="button" href="https://www.openstreetmap.org/?mlat={coordinates['latitude']}&mlon={coordinates['longitude']}#map=14/{coordinates['latitude']}/{coordinates['longitude']}" data-i18n="open_osm">Open in OpenStreetMap</a></aside></div></section>
  <section class="sources"><span class="eyebrow" data-i18n="provenance">Provenance</span><h2 data-i18n="source_references">Source references</h2><ul>{source_links}</ul></section>
</main>'''
    destination = out / "sites" / site["id"] / "index.html"
    destination.parent.mkdir(parents=True, exist_ok=True)
    titles = en_ru({locale: localized_name(site, locale) for locale in locales})
    descriptions = en_ru({locale: site["content"][locale]["summary"] for locale in locales})
    destination.write_text(layout(title=titles, body=body, prefix="../../", uddf_href=site_uddf, description=descriptions, available_locales=locales), encoding="utf-8")


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
        country_names = en_ru(country["names"])
        country_sites = sorted(
            [site for region in country["regions"].values() for site in region["sites"]],
            key=lambda item: localized_name(item).casefold(),
        )
        build_uddf(country_sites, catalog["countries"], catalog["sources"], out / "exports" / "uddf" / "countries" / f"{country_id}.uddf")
        region_links = "".join(
            f'<a class="region-link" href="regions/{region_id}/"><span {l10n_attrs(region["names"])}>{html.escape(en_ru(region["names"])["en"])}</span><strong>{len(region["sites"])}</strong></a>'
            for region_id, region in sorted(country["regions"].items())
        )
        country_page = listing_page(
            country_names, "country_index", {
                "en": f"Dive sites grouped across {len(country['regions'])} region(s).",
                "ru": f"Дайв-сайты, сгруппированные по регионам: {len(country['regions'])}.",
            }, country_sites, "../../", '<div class="breadcrumbs"><a href="../../" data-i18n="index">Index</a><span>/</span><span data-i18n="country">Country</span></div>',
            f"../../exports/uddf/countries/{country_id}.uddf",
            f'<section class="region-strip"><div class="section-heading"><div><span class="eyebrow" data-i18n="regions">Regions</span><h2 data-i18n="browse_subdivisions">Browse subdivisions</h2></div></div><div class="region-links">{region_links}</div></section>',
        )
        country_destination = out / "countries" / country_id / "index.html"
        country_destination.parent.mkdir(parents=True, exist_ok=True)
        country_destination.write_text(country_page, encoding="utf-8")
        country_cards.append(f'<a class="country-card" href="countries/{country_id}/"><span class="eyebrow">{html.escape(country.get("iso_alpha2", country_id).upper())}</span><h2 {l10n_attrs(country_names)}>{html.escape(country_names["en"])}</h2><p>{len(country_sites)} <span data-i18n="sites">sites</span> · {len(country["regions"])} <span data-i18n="region">region</span></p><span class="arrow">↗</span></a>')

        for region_id, region in sorted(country["regions"].items()):
            region_names = en_ru(region["names"])
            region_sites = sorted(region["sites"], key=lambda item: localized_name(item).casefold())
            build_uddf(region_sites, catalog["countries"], catalog["sources"], out / "exports" / "uddf" / "countries" / country_id / "regions" / f"{region_id}.uddf")
            region_page = listing_page(
                region_names, "region_index", {
                    "en": f"Dive-site index for {region_names['en']}, {country_names['en']}.",
                    "ru": f"Индекс дайв-сайтов: {region_names['ru']}, {country_names['ru']}.",
                }, region_sites, "../../../../", f'<div class="breadcrumbs"><a href="../../../../" data-i18n="index">Index</a><span>/</span><a href="../../" {l10n_attrs(country_names)}>{html.escape(country_names["en"])}</a><span>/</span><span data-i18n="region">Region</span></div>',
                f"../../../../exports/uddf/countries/{country_id}/regions/{region_id}.uddf",
            )
            region_destination = out / "countries" / country_id / "regions" / region_id / "index.html"
            region_destination.parent.mkdir(parents=True, exist_ok=True)
            region_destination.write_text(region_page, encoding="utf-8")
            for site in region_sites:
                build_uddf([site], catalog["countries"], catalog["sources"], out / "exports" / "uddf" / "sites" / f"{site['id']}.uddf")
                build_site_page(site, country, region, catalog["sources"], out)

    home_body = f'''<main><section class="hero"><span class="eyebrow" data-i18n="home_eyebrow">Open dive-site catalog</span><h1><span data-i18n="hero_title">Dive-site catalog,</span><br><em data-i18n="hero_tagline">open to corrections and reuse in other applications.</em></h1><p data-i18n="hero_intro">Multilingual descriptions, maps, regional browsing and UDDF exports.</p><div class="stat-row"><div><strong>{len(sites)}</strong><span data-i18n="sites">sites</span></div><div><strong>{len(catalog['countries'])}</strong><span data-i18n="country">country</span></div><div><strong>{sum(len(c['regions']) for c in catalog['countries'].values())}</strong><span data-i18n="region">region</span></div></div></section><section class="about-panel"><div><span class="eyebrow" data-i18n="about">About</span><h2 data-i18n="about_title">About the catalog</h2><p data-i18n="about_body">Dive Site Index is a multilingual catalog of dive sites. Suggest new dive sites or corrections, or reuse the data in another application.</p></div><nav aria-label="Catalog actions" data-i18n-aria="catalog_actions"><a class="button" href="https://github.com/kemsta/dive-site-index/issues/new?template=new-site.yml" data-i18n="suggest_site">Suggest a dive site</a><a class="button" href="https://github.com/kemsta/dive-site-index/issues/new?template=data-correction.yml" data-i18n="correct_data">Correct data</a><a class="button" href="https://github.com/kemsta/dive-site-index/blob/main/DATA_LICENSE.md" data-i18n="data_terms">Data use terms</a></nav></section><section class="country-section"><div class="section-heading"><div><span class="eyebrow" data-i18n="geography">Geography</span><h2 data-i18n="browse_country">Browse by country</h2></div><a class="button" href="exports/uddf/all.uddf" data-i18n="download_global_uddf">Download global UDDF</a></div><div class="country-grid">{''.join(country_cards)}</div></section>{map_panel()}<section class="directory"><div class="section-heading"><div><span class="eyebrow" data-i18n="all_sites">All sites</span><h2 data-i18n="site_cards">Dive site cards</h2></div></div>{listing_controls(sites)}<div id="site-list" class="site-grid">{''.join(site_card(site, '') for site in sites)}</div><p id="empty-state" class="empty" data-i18n="no_matches" hidden>No sites match these filters.</p></section></main>'''
    home_titles = {"en": "Open dive-site catalog", "ru": "Открытый каталог дайв-сайтов"}
    home_descriptions = {
        "en": "A multilingual dive-site catalog open to corrections and reuse in other applications.",
        "ru": "Многоязычный каталог дайв-сайтов, открытый для правок и использования в других приложениях.",
    }
    (out / "index.html").write_text(layout(title=home_titles, body=home_body, prefix="", uddf_href="exports/uddf/all.uddf", site_data=site_map_payload(sites), description=home_descriptions), encoding="utf-8")
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
