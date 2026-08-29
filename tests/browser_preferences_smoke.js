const fs = require("fs");
const vm = require("vm");
const assert = require("assert");
const listeners = {};
const stored = {};
const element = (dataset = {}) => ({
  dataset,
  textContent: "",
  value: "",
  hidden: false,
  placeholder: "",
  addEventListener(type, fn) { this[`on_${type}`] = fn; },
  setAttribute(name, value) { this[name] = value; },
});
const language = element({ i18nAria: "language" });
language.options = [{ value: "en" }, { value: "ru" }, { value: "ar" }, { value: "zh-Hant" }];
const theme = element({ i18nAria: "theme" });
const hero = element({ i18n: "hero_title" });
const localized = element({ en: "English summary", ru: "Русское описание", ar: "وصف عربي", "zh-Hant": "繁體中文說明" });
const localeEn = element({ locale: "en" });
const localeRu = element({ locale: "ru" });
const localeAr = element({ locale: "ar" });
const localeZhHant = element({ locale: "zh-Hant" });
const mapElement = element();
const siteData = element();
siteData.textContent = JSON.stringify([{
  id: "site_test",
  name_en: "Test site",
  name_ru: "Тестовый сайт",
  latitude: 1,
  longitude: 2,
  types_en: "reef, wall",
  types_ru: "риф, стенка",
  difficulty: null,
}]);
const selectors = {
  "#language-select": language,
  "#theme-select": theme,
  "#search": null,
  "#difficulty-filter": null,
  "#result-count": null,
  "#empty-state": null,
  "#map": mapElement,
  "#site-data": siteData,
};
const browserLanguages = process.argv[3].split(",");
const expectedLanguage = process.argv[4];
Object.defineProperty(global, "navigator", { value: { languages: browserLanguages, language: browserLanguages[0] }, configurable: true });
global.localStorage = {
  getItem(key) { return Object.prototype.hasOwnProperty.call(stored, key) ? stored[key] : null; },
  setItem(key, value) { stored[key] = value; },
};
global.document = {
  documentElement: { lang: "en", dataset: { theme: "auto" } },
  querySelector(selector) { return selectors[selector] ?? null; },
  querySelectorAll(selector) {
    if (selector === "[data-i18n]") return [hero];
    if (selector === "[data-l10n]") return [localized];
    if (selector === "[data-i18n-aria]") return [language, theme];
    if (selector === "[data-locale]") return [localeEn, localeRu, localeAr, localeZhHant];
    return [];
  },
};
let capturedGeoJson = null;
class FakeMap {
  addControl() {}
  addSource(_id, source) { capturedGeoJson = source.data; }
  addLayer() {}
  on(event, layerOrHandler) {
    if (event === "load" && typeof layerOrHandler === "function") layerOrHandler();
  }
  getCanvas() { return { style: {} }; }
}
const fakeMapLibre = {
  Map: FakeMap,
  NavigationControl: class {},
  LngLatBounds: class { extend() { return this; } },
  Popup: class {},
};
global.maplibregl = fakeMapLibre;
global.window = {
  maplibregl: fakeMapLibre,
  addEventListener(type, fn) { listeners[type] = fn; },
};
vm.runInThisContext(fs.readFileSync(process.argv[2], "utf8"), { filename: process.argv[2] });
listeners.DOMContentLoaded();
assert.equal(document.documentElement.lang, expectedLanguage);
assert.equal(language.value, expectedLanguage);
assert.equal(hero.textContent, expectedLanguage === "ru" ? "Дайв-сайты," : "Dive sites,");
assert.equal(localized.textContent, expectedLanguage === "ru" ? "Русское описание" : expectedLanguage === "ar" ? "وصف عربي" : expectedLanguage === "zh-Hant" ? "繁體中文說明" : "English summary");
assert.equal(localeEn.hidden, expectedLanguage !== "en");
assert.equal(localeRu.hidden, expectedLanguage !== "ru");
assert.equal(localeAr.hidden, expectedLanguage !== "ar");
assert.equal(localeZhHant.hidden, expectedLanguage !== "zh-Hant");
assert.equal(language["aria-label"], expectedLanguage === "ru" ? "Язык" : "Language");
assert.equal(theme["aria-label"], expectedLanguage === "ru" ? "Тема" : "Theme");
assert.equal(theme.value, "auto");
assert.equal(capturedGeoJson.features[0].properties.types_en, "reef, wall");
assert.equal(capturedGeoJson.features[0].properties.types_ru, "риф, стенка");
assert.equal(capturedGeoJson.features[0].properties.types, undefined);
language.value = expectedLanguage === "ru" ? "en" : "ru";
language.on_change();
assert.equal(stored.language, language.value);
assert.equal(document.documentElement.lang, language.value);
theme.value = "dark";
theme.on_change();
assert.equal(stored.theme, "dark");
assert.equal(document.documentElement.dataset.theme, "dark");
