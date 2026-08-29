import copy
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest
from html.parser import HTMLParser
from urllib.parse import urlsplit

import yaml
from lxml import etree

from scripts.build import build_all, load_catalog, validate_catalog, validate_site


ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog"
UDDF_XSD = ROOT / "schemas" / "vendor" / "uddf-3.2.3.xsd"
NODE = shutil.which("node")


class LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []
        self.site_cards = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if "site-card" in classes:
            self.site_cards.append((tag, attributes))
        for key in ("href", "src"):
            if key in attributes:
                self.references.append(attributes[key])


class CanonicalCatalogTests(unittest.TestCase):
    def test_country_region_and_every_site_have_en_ru_content(self):
        catalog = load_catalog(CATALOG)
        for country in catalog["countries"].values():
            self.assertTrue({"en", "ru"} <= set(country["names"]))
            for region in country["regions"].values():
                self.assertTrue({"en", "ru"} <= set(region["names"]))
                self.assertTrue({"en", "ru"} <= set(region["body_of_water"]["names"]))
                for site in region["sites"]:
                    self.assertTrue({"en", "ru"} <= set(site["content"]), site["id"])
                    for locale in ("en", "ru"):
                        self.assertEqual(
                            set(site["content"][locale]),
                            {"summary", "access", "hazards", "marine_life"},
                            (site["id"], locale),
                        )

    def test_catalog_is_partitioned_by_country_and_region(self):
        catalog = load_catalog(CATALOG)
        validate_catalog(catalog)
        self.assertEqual(set(catalog["countries"]), {"eg"})
        self.assertEqual(set(catalog["countries"]["eg"]["regions"]), {"south-sinai"})
        sites = catalog["countries"]["eg"]["regions"]["south-sinai"]["sites"]
        self.assertEqual(len(sites), 21)
        self.assertEqual(len({site["id"] for site in sites}), 21)

    def test_site_descriptions_are_locale_keyed_and_extensible(self):
        catalog = load_catalog(CATALOG)
        site = catalog["countries"]["eg"]["regions"]["south-sinai"]["sites"][0]
        self.assertIn("en", site["content"])
        self.assertIn("summary", site["content"]["en"])
        translated = dict(site)
        translated["content"] = dict(site["content"])
        translated["content"]["ru"] = {
            "summary": "Описание",
            "access": "Доступ",
            "hazards": "Опасности",
            "marine_life": "Морская жизнь",
        }
        validate_site(translated, country_id="eg", region_id="south-sinai")

    def test_user_defined_and_probable_identity_remain_explicit(self):
        catalog = load_catalog(CATALOG)
        sites = {
            site["id"]: site
            for site in catalog["countries"]["eg"]["regions"]["south-sinai"]["sites"]
        }
        self.assertEqual(sites["site_old_quay"]["identity"]["confidence"], "probable")
        self.assertEqual(sites["site_sharm_el_maya_unidentified"]["identity"]["kind"], "user-defined")
        self.assertEqual(sites["site_shaab_ali_dolphin_drop"]["identity"]["kind"], "user-defined")

    def test_extended_bcp47_locale_is_accepted(self):
        catalog = load_catalog(CATALOG)
        site = copy.deepcopy(catalog["countries"]["eg"]["regions"]["south-sinai"]["sites"][0])
        site["names"]["en-US-u-ca-gregory"] = "Localized name"
        site["content"]["en-US-u-ca-gregory"] = copy.deepcopy(site["content"]["en"])
        validate_site(site, country_id="eg", region_id="south-sinai")

    def test_structurally_invalid_bcp47_locale_is_rejected(self):
        catalog = load_catalog(CATALOG)
        site = copy.deepcopy(catalog["countries"]["eg"]["regions"]["south-sinai"]["sites"][0])
        site["names"]["en-US-GB"] = "Invalid locale"
        with self.assertRaisesRegex(ValueError, "locale"):
            validate_site(site, country_id="eg", region_id="south-sinai")

    def test_schema_rejects_unknown_site_fields(self):
        catalog = load_catalog(CATALOG)
        site = copy.deepcopy(catalog["countries"]["eg"]["regions"]["south-sinai"]["sites"][0])
        site["unexpected"] = "must not be published"
        with self.assertRaises(ValueError):
            validate_site(site, country_id="eg", region_id="south-sinai")

    def test_country_id_must_be_safe_and_match_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog_dir = pathlib.Path(tmp) / "catalog"
            shutil.copytree(CATALOG, catalog_dir)
            path = catalog_dir / "countries" / "eg" / "country.yaml"
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            document["id"] = "../escape"
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_catalog(catalog_dir)

    def test_duplicate_source_ids_are_rejected_before_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog_dir = pathlib.Path(tmp) / "catalog"
            shutil.copytree(CATALOG, catalog_dir)
            path = catalog_dir / "sources.yaml"
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            document["sources"].append(copy.deepcopy(document["sources"][0]))
            path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate source"):
                load_catalog(catalog_dir)

    def test_source_urls_are_limited_to_http_and_https(self):
        catalog = load_catalog(CATALOG)
        source = next(iter(catalog["sources"].values()))
        source["url"] = "javascript:alert(1)"
        with self.assertRaisesRegex(ValueError, "source URL"):
            validate_catalog(catalog)


class PublishingTests(unittest.TestCase):
    def test_repository_explains_contribution_reporting_and_commercial_use(self):
        expected = [
            ROOT / "CONTRIBUTING.md",
            ROOT / "DATA_LICENSE.md",
            ROOT / "SECURITY.md",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "new-site.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "data-correction.yml",
            ROOT / ".github" / "ISSUE_TEMPLATE" / "bug-report.yml",
        ]
        for path in expected:
            self.assertTrue(path.is_file(), path)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("CONTRIBUTING.md", readme)
        self.assertIn("DATA_LICENSE.md", readme)
        self.assertIn("GitHub Issues", readme)
        self.assertIn("ODC-By 1.0", readme)

        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn("Add a dive site", contributing)
        self.assertIn("Correct existing data", contributing)
        self.assertIn("source_refs", contributing)
        self.assertIn("uv run python -m unittest", contributing)

        licensing = (ROOT / "DATA_LICENSE.md").read_text(encoding="utf-8").casefold()
        self.assertIn("commercial", licensing)
        self.assertIn("odc-by 1.0", licensing)
        self.assertIn("attribution", licensing)
        self.assertIn("does **not** impose the odbl share-alike", licensing)

        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            build_all(CATALOG, out)
            pages = sorted(out.rglob("*.html"))
            self.assertEqual(len(pages), 24)
            for page in pages:
                html = page.read_text(encoding="utf-8")
                self.assertIn("DATA_LICENSE.md", html, page)
                self.assertIn("CONTRIBUTING.md", html, page)
                self.assertIn('data-i18n="report_problem"', html, page)
                self.assertIn('data-i18n-aria="project_information"', html, page)
            app = (out / "assets" / "app.js").read_text(encoding="utf-8")
            self.assertIn('data_license: "Лицензия данных"', app)

    def test_each_scope_has_its_own_uddf_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            build_all(CATALOG, out)
            home = (out / "index.html").read_text(encoding="utf-8")
            country = (out / "countries" / "eg" / "index.html").read_text(encoding="utf-8")
            region = (out / "countries" / "eg" / "regions" / "south-sinai" / "index.html").read_text(encoding="utf-8")
            self.assertIn('href="exports/uddf/all.uddf"', home)
            self.assertIn('href="../../exports/uddf/countries/eg.uddf"', country)
            self.assertIn(
                'href="../../../../exports/uddf/countries/eg/regions/south-sinai.uddf"',
                region,
            )
            for page in (out / "sites").glob("*/index.html"):
                site_id = page.parent.name
                document = page.read_text(encoding="utf-8")
                self.assertIn(
                    f'href="../../exports/uddf/sites/{site_id}.uddf"', document
                )
                export = out / "exports" / "uddf" / "sites" / f"{site_id}.uddf"
                self.assertTrue(export.is_file(), export)
                xml = etree.parse(str(export))
                self.assertEqual(
                    len(xml.findall(".//{http://www.streit.cc/uddf/3.2/}site")), 1
                )

    def test_every_page_has_top_language_and_auto_theme_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            build_all(CATALOG, out)
            pages = list(out.rglob("*.html"))
            self.assertEqual(len(pages), 24)
            for page in pages:
                document = page.read_text(encoding="utf-8")
                self.assertIn('id="language-select"', document, page)
                self.assertIn('id="theme-select"', document, page)
                self.assertIn('id="language-select" aria-label="Language" data-i18n-aria="language"', document, page)
                self.assertIn('id="theme-select" aria-label="Theme" data-i18n-aria="theme"', document, page)
                self.assertIn('data-theme="auto"', document, page)

    def test_frontend_uses_browser_language_and_bilingual_interface(self):
        source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("navigator.languages", source)
        self.assertIn('localStorage.getItem("language")', source)
        self.assertIn('localStorage.getItem("theme")', source)
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("prefers-color-scheme", styles)
        self.assertIn("--link-hover: #111827", styles)
        self.assertIn("a:hover { color: var(--link-hover); }", styles)
        self.assertIn("Русский", source)
        self.assertIn("Dive sites", source)
        self.assertNotIn("site.types.join", source)
        self.assertIn("types_en: site.types_en", source)
        self.assertIn('feature.properties[`types_${activeLanguage}`]', source)
        self.assertIn("difficulty_not_assigned", source)

    def test_home_copy_describes_contributions_and_app_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            build_all(CATALOG, out)
            home = (out / "index.html").read_text(encoding="utf-8")
            app = (out / "assets" / "app.js").read_text(encoding="utf-8")
            public_copy = home + app
            self.assertNotIn("переносим", public_copy.casefold())
            self.assertIn("открытые для правок и интеграций.", public_copy)
            self.assertIn("экспортом UDDF для использования в других приложениях", public_copy)
            self.assertIn("open to contributions and reuse.", public_copy)

    @unittest.skipUnless(NODE, "Node.js is required for browser preference smoke testing")
    def test_browser_preferences_select_russian_and_auto_theme(self):
        for browser_languages, expected in (("ru-RU,en-US", "ru"), ("en-US,ru-RU", "en"), ("ar,en-US", "ar"), ("zh-Hant,en-US", "zh-Hant")):
            with self.subTest(browser_languages=browser_languages):
                subprocess.run(
                    [
                        NODE or "node",
                        str(ROOT / "tests" / "browser_preferences_smoke.js"),
                        str(ROOT / "web" / "app.js"),
                        browser_languages,
                        expected,
                    ],
                    check=True,
                )

    def test_publication_omits_internal_review_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            build_all(CATALOG, out)
            html_output = "\n".join(
                page.read_text(encoding="utf-8") for page in out.rglob("*.html")
            )
            app_js = (out / "assets" / "app.js").read_text(encoding="utf-8")

            self.assertNotIn("confidence states", html_output)
            self.assertNotIn("<span>observations</span>", html_output)
            self.assertNotIn("<span>Observations</span>", html_output)
            self.assertNotIn("personal observations", html_output)
            self.assertNotIn("canonical · confirmed", html_output)
            self.assertNotIn(">confirmed<", html_output)
            public_copy = html_output.casefold()
            self.assertNotIn("reviewed", public_copy)
            self.assertNotIn("reviewable", public_copy)
            self.assertNotIn("canonical", public_copy)
            self.assertNotIn("garmin observation", public_copy)
            self.assertNotIn("personal observation", public_copy)
            self.assertNotIn("observation only", public_copy)
            self.assertNotIn("marine-life observation", public_copy)
            public_js = app_js.casefold()
            self.assertNotIn("reviewed", public_js)
            self.assertNotIn("reviewable", public_js)
            self.assertNotIn("canonical", public_js)
            self.assertNotIn("confidence", app_js)
            forbidden_payload_keys = {"identity", "confidence", "observations", "observation_count"}
            for page in out.rglob("*.html"):
                document = etree.HTML(page.read_text(encoding="utf-8"))
                for script in document.xpath('//script[@id="site-data"]'):
                    payload = json.loads(script.text or "[]")
                    keys = {key for site in payload for key in site}
                    self.assertTrue(forbidden_payload_keys.isdisjoint(keys), (page, keys))

            for export in out.rglob("*.uddf"):
                public_uddf = export.read_text(encoding="utf-8").casefold()
                self.assertNotIn("identity:", public_uddf, export)
                self.assertNotIn("confidence", public_uddf, export)
                self.assertNotIn("confirmed", public_uddf, export)
                self.assertNotIn("observations:", public_uddf, export)

            for public_file in [*out.rglob("*.html"), *out.rglob("*.uddf")]:
                self.assertNotRegex(
                    public_file.read_text(encoding="utf-8").casefold(),
                    r"\bobservations?\b",
                    public_file,
                )

    def test_theme_text_colors_meet_wcag_aa_contrast(self):
        styles = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")

        def color(variable: str, block: str) -> str:
            match = re.search(rf"{re.escape(variable)}:\s*(#[0-9a-fA-F]{{6}})", block)
            if match is None:
                self.fail(variable)
            return match.group(1)

        def luminance(value: str) -> float:
            channels = [int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

        def contrast(foreground: str, background: str) -> float:
            lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
            return (lighter + 0.05) / (darker + 0.05)

        dark = styles.split(":root[data-theme=\"light\"]", 1)[0]
        light = styles.split(":root[data-theme=\"light\"]", 1)[1].split("@media", 1)[0]
        combinations = [
            (color("--muted", dark), color("--bg", dark)),
            (color("--muted", dark), color("--panel", dark)),
            (color("--muted", light), color("--bg", light)),
            (color("--cyan", light), color("--bg", light)),
        ]
        for foreground, background in combinations:
            self.assertGreaterEqual(contrast(foreground, background), 4.5, (foreground, background))

    def test_entire_site_card_is_a_stable_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            catalog = load_catalog(CATALOG)
            build_all(CATALOG, out)
            collector = LinkCollector()
            collector.feed((out / "index.html").read_text(encoding="utf-8"))
            expected_ids = {
                site["id"]
                for country in catalog["countries"].values()
                for region in country["regions"].values()
                for site in region["sites"]
            }
            self.assertEqual(len(collector.site_cards), len(expected_ids))
            for tag, attributes in collector.site_cards:
                site_id = attributes.get("data-site-id")
                self.assertEqual(tag, "a")
                self.assertIn(site_id, expected_ids)
                self.assertEqual(attributes.get("href"), f"sites/{site_id}/")

    def test_build_emits_global_country_and_region_uddf(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            summary = build_all(CATALOG, out)
            self.assertEqual(summary["site_count"], 21)
            paths = [
                out / "exports" / "uddf" / "all.uddf",
                out / "exports" / "uddf" / "countries" / "eg.uddf",
                out / "exports" / "uddf" / "countries" / "eg" / "regions" / "south-sinai.uddf",
            ]
            for path in paths:
                self.assertTrue(path.is_file(), path)
                schema = etree.XMLSchema(etree.parse(str(UDDF_XSD)))
                document = etree.parse(str(path))
                self.assertTrue(schema.validate(document), str(schema.error_log))
                namespace = {"u": "http://www.streit.cc/uddf/3.2/"}
                root = document.getroot()
                self.assertEqual(root.attrib["version"], "3.2.3")
                self.assertEqual(len(root.findall("./u:divesite/u:site", namespace)), 21)

    def test_build_emits_browsable_html_hierarchy_and_site_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            build_all(CATALOG, out)
            expected = [
                out / "index.html",
                out / "countries" / "eg" / "index.html",
                out / "countries" / "eg" / "regions" / "south-sinai" / "index.html",
                out / "sites" / "site_jackson_reef" / "index.html",
                out / "assets" / "styles.css",
                out / "assets" / "app.js",
            ]
            for path in expected:
                self.assertTrue(path.is_file(), path)
            home = (out / "index.html").read_text(encoding="utf-8")
            region = (out / "countries" / "eg" / "regions" / "south-sinai" / "index.html").read_text(encoding="utf-8")
            detail = (out / "sites" / "site_jackson_reef" / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="map"', home)
            self.assertIn('id="search"', region)
            self.assertIn('class="site-card"', region)
            self.assertIn('data-locale="en"', detail)
            self.assertIn("Jackson Reef", detail)

    def test_preferred_locale_is_initial_html_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            catalog_dir = root / "catalog"
            out = root / "public"
            shutil.copytree(CATALOG, catalog_dir)
            path = catalog_dir / "countries" / "eg" / "regions" / "south-sinai" / "sites" / "site_jackson_reef.yaml"
            site = yaml.safe_load(path.read_text(encoding="utf-8"))
            site["names"]["zh-Hant"] = "傑克遜礁"
            site["content"]["zh-Hant"] = {
                "summary": "繁體中文說明。",
                "access": "船潛。",
                "hazards": "注意海流。",
                "marine_life": "珊瑚礁生物。",
            }
            path.write_text(yaml.safe_dump(site, sort_keys=False, allow_unicode=True), encoding="utf-8")
            build_all(catalog_dir, out)
            detail = (out / "sites" / "site_jackson_reef" / "index.html").read_text(encoding="utf-8")
            self.assertIn('<html lang="en" data-theme="auto">', detail)
            self.assertIn('class="locale-content" data-locale="en">', detail)
            self.assertIn('data-locale="zh-Hant" hidden', detail)
            self.assertIn('<option value="zh-Hant">ZH-HANT</option>', detail)

    def test_build_does_not_publish_media_or_non_requested_data_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            build_all(CATALOG, out)
            self.assertFalse((out / "media").exists())
            self.assertFalse((out / "sites.json").exists())
            self.assertFalse((out / "sites.geojson").exists())
            self.assertFalse((out / "sites.xml").exists())
            self.assertEqual(list(out.rglob("*.json")), [])

    def test_every_internal_html_reference_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            build_all(CATALOG, out)
            missing = []
            for page in out.rglob("*.html"):
                collector = LinkCollector()
                collector.feed(page.read_text(encoding="utf-8"))
                for reference in collector.references:
                    parsed = urlsplit(reference)
                    if parsed.scheme or parsed.netloc or not parsed.path:
                        continue
                    target = (page.parent / parsed.path).resolve()
                    if target.is_dir():
                        target /= "index.html"
                    if not target.exists():
                        missing.append((str(page.relative_to(out)), reference))
            self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
