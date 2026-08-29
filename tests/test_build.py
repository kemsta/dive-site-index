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

from scripts.build import TYPE_RU, build_all, load_catalog, validate_catalog, validate_site


ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog"
EXPECTED_SITE_COUNT = 42
EXPECTED_HTML_COUNT = EXPECTED_SITE_COUNT + 3
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
    def test_south_sinai_expansion_tracks_all_researched_candidates(self):
        manifest_path = ROOT / "research" / "south-sinai-expansion.yaml"
        self.assertTrue(manifest_path.is_file(), manifest_path)
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], "1.0")
        resolutions = manifest["resolutions"]
        self.assertEqual(len(resolutions), 118)
        self.assertEqual(len({item["candidate_key"] for item in resolutions}), 118)

        catalog = load_catalog(CATALOG)
        sites = {
            site["id"]: site
            for country in catalog["countries"].values()
            for region in country["regions"].values()
            for site in region["sites"]
        }
        for item in resolutions:
            self.assertIn(item["resolution"], {"site", "alias", "pending"}, item["candidate_key"])
            if item["resolution"] == "pending":
                self.assertIsNone(item["target_site_id"], item["candidate_key"])
                continue
            target = sites[item["target_site_id"]]
            if item["resolution"] == "alias":
                self.assertIn(item["canonical_name"], target["aliases"], item["candidate_key"])

    def test_dahab_expansion_resolves_all_sixteen_candidates(self):
        expected = {
            "eel-garden-dahab-central-assalah-bay": ("site_dahab_eel_garden", 28.505, 34.519722, "src-9db3ce3b9e04"),
            "the-islands-dahab-central-lagoona-el-qura-bay": ("site_dahab_islands", 28.477778, 34.511667, "src-9db3ce3b9e04"),
            "napoleon-reef-dahab-central-lagoona-spit": ("site_dahab_napoleon_reef", 28.470556, 34.5075, "src-9db3ce3b9e04"),
            "bannerfish-bay-dahab-central-masbat-bay": ("site_dahab_bannerfish_bay", 28.498889, 34.518611, "src-9db3ce3b9e04"),
            "mashraba-dahab-central-south-end-of-dahab-bay": ("site_dahab_mashraba", 28.495, 34.516944, "src-9db3ce3b9e04"),
            "seven-pinnacles-dahab-central-tip-of-the-sand-spit": ("site_dahab_seven_pinnacles", 28.4745009297555, 34.4970166683197, "src-c4500222da23"),
            "abu-helal-dahab-north": ("site_dahab_abu_helal", 28.54221, 34.51669, "src-71755a43d3f9"),
            "abu-telha-dahab-north": ("site_dahab_abu_telha", 28.5505, 34.5215, "src-1e603da76b49"),
            "bells-dahab-north": ("site_dahab_bells", 28.573514, 34.539233, "src-74944b21d746"),
            "canyon-coral-garden-dahab-north-canyon-area": ("site_dahab_canyon_coral_garden", 28.554722, 34.520833, "src-9db3ce3b9e04"),
            "rick-s-reef-dahab-north-canyon-area": ("site_dahab_ricks_reef", 28.557222, 34.523611, "src-9db3ce3b9e04"),
            "three-pools-dahab-south-el-qura-bay": ("site_dahab_three_pools", 28.435833, 34.457222, "src-9db3ce3b9e04"),
            "the-caves-dahab-south-el-qura-bay-nabq-edge": ("site_dahab_caves", 28.416667, 34.455833, "src-9db3ce3b9e04"),
            "um-sid-dahab-south-southern-oasis": ("site_dahab_um_sid", 28.420833, 34.457222, "src-9db3ce3b9e04"),
            "golden-blocks-dahab-south-southern-oasis-wadi-qnai": ("site_dahab_golden_blocks", 28.439027777777778, 34.46352777777778, "src-2002a13df988"),
            "moray-garden-dahab-south-southern-oasis-wadi-qnai": ("site_dahab_moray_garden", 28.437778, 34.458889, "src-9db3ce3b9e04"),
        }
        manifest = yaml.safe_load(
            (ROOT / "research" / "south-sinai-expansion.yaml").read_text(encoding="utf-8")
        )
        resolutions = {
            item["candidate_key"]: item
            for item in manifest["resolutions"]
            if item["candidate_key"] in expected
        }
        self.assertEqual(set(resolutions), set(expected))

        catalog = load_catalog(CATALOG)
        sites = {
            site["id"]: site
            for country in catalog["countries"].values()
            for region in country["regions"].values()
            for site in region["sites"]
        }
        sources = {
            source["id"]: source
            for source in yaml.safe_load((CATALOG / "sources.yaml").read_text(encoding="utf-8"))["sources"]
        }
        for candidate_key, (site_id, latitude, longitude, coordinate_source_ref) in expected.items():
            self.assertEqual(resolutions[candidate_key]["resolution"], "site")
            self.assertEqual(resolutions[candidate_key]["target_site_id"], site_id)
            site = sites[site_id]
            self.assertIn(coordinate_source_ref, site["source_refs"])
            self.assertIn(coordinate_source_ref, sources)
            self.assertAlmostEqual(site["geography"]["coordinates"]["latitude"], latitude, places=6)
            self.assertAlmostEqual(site["geography"]["coordinates"]["longitude"], longitude, places=6)
            self.assertNotIn("current", site)
            self.assertNotIn("visibility", site)

        seven = sites["site_dahab_seven_pinnacles"]
        self.assertNotIn("no unambiguous current exact coordinate", seven["content"]["en"]["hazards"].casefold())
        self.assertNotIn("точные координаты не найдены", seven["content"]["ru"]["hazards"].casefold())

    def test_first_south_sinai_expansion_adds_five_grounded_sites(self):
        catalog = load_catalog(CATALOG)
        sites = {
            site["id"]: site
            for country in catalog["countries"].values()
            for region in country["regions"].values()
            for site in region["sites"]
        }
        expected = {
            "site_thomas_reef": ("Thomas Reef", 27.9906167, 34.4607333, "src-8ba0267b1a74"),
            "site_ss_thistlegorm": ("SS Thistlegorm", 27.8146, 33.9202, "src-b7fe7e40c809"),
            "site_dahab_blue_hole": ("Blue Hole", 28.57284, 34.53754, "src-d25a157b19f1"),
            "site_dahab_canyon": ("The Canyon", 28.5548333, 34.521, "src-4336d93f5ce3"),
            "site_dahab_lighthouse": ("Lighthouse", 28.4990167, 34.5198833, "src-3fb65c77fda4"),
        }
        source_documents = yaml.safe_load((CATALOG / "sources.yaml").read_text(encoding="utf-8"))
        sources = {source["id"]: source for source in source_documents["sources"]}
        self.assertEqual(set(expected), set(expected) & set(sites))
        for site_id, (name, latitude, longitude, coordinate_source_ref) in expected.items():
            site = sites[site_id]
            self.assertEqual(site["names"]["en"], name)
            self.assertEqual(site["identity"], {"kind": "canonical", "confidence": "confirmed"})
            self.assertGreaterEqual(len(site["source_refs"]), 2)
            self.assertIn(coordinate_source_ref, site["source_refs"])
            self.assertAlmostEqual(site["geography"]["coordinates"]["latitude"], latitude, places=6)
            self.assertAlmostEqual(site["geography"]["coordinates"]["longitude"], longitude, places=6)
            for source_ref in site["source_refs"]:
                self.assertNotEqual(urlsplit(sources[source_ref]["url"]).hostname, "www.openstreetmap.org")
            self.assertNotIn("current", site)
            self.assertNotIn("visibility", site)
            self.assertEqual(site["observations"], [])

    def test_every_site_uses_compact_public_classification(self):
        catalog = load_catalog(CATALOG)
        allowed_types = {
            "reef", "wall", "wreck", "drift", "cave", "cavern",
            "pinnacle", "drop-off", "slope", "plateau", "canyon",
            "channel", "sand", "bay", "swim-through", "jetty",
            "artificial", "training", "night", "snorkeling", "other",
        }
        allowed_access = {"boat", "shore", "pier", "liveaboard"}
        self.assertEqual(set(TYPE_RU), allowed_types)
        for country in catalog["countries"].values():
            for region in country["regions"].values():
                for site in region["sites"]:
                    self.assertNotIn("classification", site, site["id"])
                    self.assertIsInstance(site["types"], list, site["id"])
                    self.assertTrue(set(site["types"]) <= allowed_types, site["id"])
                    self.assertEqual(len(site["types"]), len(set(site["types"])), site["id"])
                    self.assertIsInstance(site["access"], list, site["id"])
                    self.assertTrue(set(site["access"]) <= allowed_access, site["id"])
                    self.assertEqual(len(site["access"]), len(set(site["access"])), site["id"])

    def test_optional_current_and_visibility_fields_are_validated(self):
        catalog = load_catalog(CATALOG)
        site = copy.deepcopy(catalog["countries"]["eg"]["regions"]["south-sinai"]["sites"][0])
        site["current"] = {"typical": "moderate", "variable": True}
        site["visibility"] = {"minimum_m": 15, "maximum_m": 30}
        validate_site(site, country_id="eg", region_id="south-sinai")

        invalid_current = copy.deepcopy(site)
        invalid_current["current"]["typical"] = "sometimes-fast"
        with self.assertRaises(ValueError):
            validate_site(invalid_current, country_id="eg", region_id="south-sinai")

        invalid_visibility = copy.deepcopy(site)
        invalid_visibility["visibility"] = {"minimum_m": 30, "maximum_m": 15}
        with self.assertRaisesRegex(ValueError, "visibility"):
            validate_site(invalid_visibility, country_id="eg", region_id="south-sinai")

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
        self.assertEqual(len(sites), EXPECTED_SITE_COUNT)
        self.assertEqual(len({site["id"] for site in sites}), EXPECTED_SITE_COUNT)

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
    def test_optional_conditions_are_exported_to_uddf(self):
        with tempfile.TemporaryDirectory() as tmp:
            catalog = pathlib.Path(tmp) / "catalog"
            out = pathlib.Path(tmp) / "public"
            shutil.copytree(CATALOG, catalog)
            site_path = catalog / "countries" / "eg" / "regions" / "south-sinai" / "sites" / "site_amphoras.yaml"
            site = yaml.safe_load(site_path.read_text(encoding="utf-8"))
            site["current"] = {"typical": "moderate", "variable": True}
            site["visibility"] = {"minimum_m": 15, "maximum_m": 30}
            site_path.write_text(yaml.safe_dump(site, sort_keys=False, allow_unicode=True), encoding="utf-8")
            build_all(catalog, out)
            uddf = (out / "exports" / "uddf" / "sites" / "site_amphoras.uddf").read_text(encoding="utf-8")
            self.assertIn("<minimumvisibility>15</minimumvisibility>", uddf)
            self.assertIn("<maximumvisibility>30</maximumvisibility>", uddf)
            self.assertIn("Typical current: moderate; variable", uddf)

    def test_public_output_uses_structured_types_and_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            build_all(CATALOG, out)
            site = (out / "sites" / "site_shark_yolanda" / "index.html").read_text(encoding="utf-8")
            home = (out / "index.html").read_text(encoding="utf-8")
            uddf = (out / "exports" / "uddf" / "sites" / "site_shark_yolanda.uddf").read_text(encoding="utf-8")
            self.assertIn('data-site-types="reef,wall,plateau,drift,wreck"', site)
            self.assertIn('data-site-access="boat"', site)
            self.assertIn('data-types="reef wall plateau drift wreck"', home)
            self.assertIn('data-access="boat"', home)
            self.assertIn("Site types: reef, wall, plateau, drift, wreck", uddf)
            self.assertIn("Access methods: boat", uddf)
            public_types = []
            for page in out.rglob("*.html"):
                document = page.read_text(encoding="utf-8")
                public_types.extend(re.findall(r'data-site-types="([^"]*)"', document))
                public_types.extend(re.findall(r'data-types="([^"]*)"', document))
            map_payload = (out / "index.html").read_text(encoding="utf-8")
            for forbidden in ("Garmin observation", "user-defined location", "unidentified dive"):
                self.assertNotIn(forbidden.casefold(), " ".join(public_types).casefold())
                self.assertNotIn(f'"types_en":"{forbidden}', map_payload)

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
        self.assertIn("permission to publish without displaying the standard odc-by license notice", licensing)
        self.assertIn("attribution requirements for that use are determined by the agreement", licensing)
        self.assertIn("individual written agreement", licensing)
        self.assertIn("does not withdraw or restrict odc-by 1.0 rights", licensing)

        self.assertNotIn("commercial use with required attribution", readme.casefold())
        self.assertIn("qualifying public use requires attribution", readme.casefold())
        self.assertIn("suggested attribution", readme.casefold())

        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp)
            build_all(CATALOG, out)
            pages = sorted(out.rglob("*.html"))
            self.assertEqual(len(pages), EXPECTED_HTML_COUNT)
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
            self.assertEqual(len(pages), EXPECTED_HTML_COUNT)
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
        self.assertIn("Dive-site catalog", source)
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
            self.assertNotIn("открытые для правок и интеграций", public_copy.casefold())
            self.assertIn("Каталог дайв-сайтов,", public_copy)
            self.assertIn("открытый для правок и использования в других приложениях.", public_copy)
            self.assertIn("Dive Site Index — многоязычный каталог дайв-сайтов.", public_copy)
            self.assertIn("Предлагайте новые дайв-сайты или исправления", public_copy)
            self.assertIn('data-i18n="about_title"', home)
            self.assertIn('data-i18n="about_body"', home)
            self.assertIn('data-i18n="suggest_site"', home)
            self.assertIn('data-i18n="correct_data"', home)
            self.assertIn('data-i18n="data_terms"', home)
            self.assertIn('data-i18n-aria="catalog_actions"', home)
            self.assertIn("открытый для правок и использования в других приложениях", home)
            self.assertIn("open to corrections and reuse in other applications.", public_copy)

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
            self.assertEqual(summary["site_count"], EXPECTED_SITE_COUNT)
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
                self.assertEqual(len(root.findall("./u:divesite/u:site", namespace)), EXPECTED_SITE_COUNT)

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
