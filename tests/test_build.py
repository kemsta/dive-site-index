import copy
import pathlib
import shutil
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


class LinkCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        for key in ("href", "src"):
            if key in attributes:
                self.references.append(attributes[key])


class CanonicalCatalogTests(unittest.TestCase):
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
            site["names"]["ar"] = "شعاب جاكسون"
            site["content"]["ar"] = {
                "summary": "وصف عربي.",
                "access": "وصول.",
                "hazards": "مخاطر.",
                "marine_life": "حياة بحرية.",
            }
            path.write_text(yaml.safe_dump(site, sort_keys=False, allow_unicode=True), encoding="utf-8")
            build_all(catalog_dir, out)
            detail = (out / "sites" / "site_jackson_reef" / "index.html").read_text(encoding="utf-8")
            self.assertIn('<html lang="en">', detail)
            self.assertIn('class="locale-content" data-locale="en">', detail)
            self.assertIn('data-locale="ar" hidden', detail)

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
