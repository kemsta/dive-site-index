(() => {
  "use strict";

  const I18N = {
    en: {
      brand: "Dive Site Index",
      download_uddf: "UDDF",
      download_global_uddf: "Download global UDDF",
      download_site_uddf: "Download site UDDF",
      language: "Language",
      language_ru: "Русский",
      theme: "Theme",
      theme_auto: "Auto",
      theme_light: "Light",
      theme_dark: "Dark",
      footer_source: "Open dive-site data with cited sources.",
      footer_map: "Map © OpenStreetMap contributors.",
      home_eyebrow: "Open dive-site index",
      hero_title: "Dive sites,",
      hero_tagline: "open and portable.",
      hero_intro: "A multilingual, source-backed directory with maps, regional browsing and portable UDDF exports.",
      geography: "Geography",
      browse_country: "Browse by country",
      all_sites: "All sites",
      country: "country",
      region: "region",
      regions: "Regions",
      country_index: "Country index",
      region_index: "Region index",
      browse_subdivisions: "Browse subdivisions",
      sites: "sites",
      site_types: "site types",
      languages: "languages",
      directory: "Directory",
      site_cards: "Site cards",
      search: "Search",
      search_placeholder: "Name, description or type",
      difficulty: "Difficulty",
      all_levels: "All levels",
      difficulty_beginner: "Beginner",
      difficulty_intermediate: "Intermediate",
      difficulty_advanced: "Advanced",
      difficulty_not_assigned: "Not assigned",
      not_assigned: "Not assigned",
      geographic_index: "Geographic index",
      explore_map: "Explore the map",
      map_intro: "Browse dive-site locations.",
      map_aria: "Interactive dive-site map",
      no_matches: "No sites match these filters.",
      index: "Index",
      dive_site: "Dive site",
      depth: "Depth",
      coordinates: "Coordinates",
      access: "Access",
      hazards: "Hazards",
      marine_life: "Marine life",
      provenance: "Provenance",
      source_references: "Source references",
      open_osm: "Open in OpenStreetMap",
    },
    ru: {
      brand: "Индекс дайв-сайтов",
      download_uddf: "UDDF",
      download_global_uddf: "Скачать общий UDDF",
      download_site_uddf: "Скачать UDDF сайта",
      language: "Язык",
      language_ru: "Русский",
      theme: "Тема",
      theme_auto: "Авто",
      theme_light: "Светлая",
      theme_dark: "Тёмная",
      footer_source: "Открытые данные о дайв-сайтах с указанием источников.",
      footer_map: "Карта © участники OpenStreetMap.",
      home_eyebrow: "Открытый индекс дайв-сайтов",
      hero_title: "Дайв-сайты,",
      hero_tagline: "открытые и переносимые.",
      hero_intro: "Многоязычный каталог с картой, навигацией по регионам и переносимыми экспортами UDDF.",
      geography: "География",
      browse_country: "Выбрать страну",
      all_sites: "Все сайты",
      country: "страна",
      region: "регион",
      regions: "Регионы",
      country_index: "Каталог страны",
      region_index: "Каталог региона",
      browse_subdivisions: "Выбрать регион",
      sites: "сайты",
      site_types: "типы сайтов",
      languages: "языки",
      directory: "Каталог",
      site_cards: "Карточки сайтов",
      search: "Поиск",
      search_placeholder: "Название, описание или тип",
      difficulty: "Сложность",
      all_levels: "Все уровни",
      difficulty_beginner: "Начальный",
      difficulty_intermediate: "Средний",
      difficulty_advanced: "Продвинутый",
      difficulty_not_assigned: "Не указана",
      not_assigned: "Не указана",
      geographic_index: "Географический каталог",
      explore_map: "Карта сайтов",
      map_intro: "Просматривайте местоположения дайв-сайтов.",
      map_aria: "Интерактивная карта дайв-сайтов",
      no_matches: "Нет сайтов, соответствующих выбранным фильтрам.",
      index: "Каталог",
      dive_site: "Дайв-сайт",
      depth: "Глубина",
      coordinates: "Координаты",
      access: "Доступ",
      hazards: "Опасности",
      marine_life: "Морская жизнь",
      provenance: "Происхождение данных",
      source_references: "Источники",
      open_osm: "Открыть в OpenStreetMap",
    },
  };

  let activeLanguage = "en";
  let directoryFilter = null;
  const normalize = (value) => (value || "").toLocaleLowerCase().trim();
  const translate = (key) => I18N[activeLanguage]?.[key] || I18N.en[key] || key;

  function availableLanguages() {
    const selector = document.querySelector("#language-select");
    return selector ? Array.from(selector.options).map((option) => option.value) : ["en", "ru"];
  }

  function resolveLanguage(value) {
    const requested = normalize(value);
    return availableLanguages().find((language) => normalize(language) === requested) || null;
  }

  function browserLanguage() {
    const available = availableLanguages();
    const preferences = navigator.languages || [navigator.language || "en"];
    for (const value of preferences) {
      const preference = normalize(value);
      const exact = available.find((language) => normalize(language) === preference);
      if (exact) return exact;
      const base = preference.split("-")[0];
      const compatible = available.find((language) => normalize(language).split("-")[0] === base);
      if (compatible) return compatible;
    }
    return available.find((language) => normalize(language) === "en") || available[0];
  }

  function initialLanguage() {
    try {
      const stored = localStorage.getItem("language");
      const resolved = resolveLanguage(stored);
      if (resolved) return resolved;
    } catch (_) {
      // Storage may be unavailable in privacy modes; browser preference remains authoritative.
    }
    return browserLanguage();
  }

  function siteCountLabel(count) {
    if (activeLanguage !== "ru") return `${count} ${count === 1 ? "site" : "sites"}`;
    const mod10 = count % 10;
    const mod100 = count % 100;
    const noun = mod10 === 1 && mod100 !== 11 ? "сайт" : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? "сайта" : "сайтов";
    return `${count} ${noun}`;
  }

  function applyLanguage(language, persist = false) {
    const available = availableLanguages();
    activeLanguage = resolveLanguage(language) || resolveLanguage("en") || available[0];
    document.documentElement.lang = activeLanguage;
    const selector = document.querySelector("#language-select");
    if (selector) selector.value = activeLanguage;
    if (persist) {
      try { localStorage.setItem("language", activeLanguage); } catch (_) { /* no-op */ }
    }
    document.querySelectorAll("[data-i18n]").forEach((element) => {
      element.textContent = translate(element.dataset.i18n);
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
      element.placeholder = translate(element.dataset.i18nPlaceholder);
    });
    document.querySelectorAll("[data-i18n-aria]").forEach((element) => {
      element.setAttribute("aria-label", translate(element.dataset.i18nAria));
    });
    document.querySelectorAll("[data-l10n]").forEach((element) => {
      element.textContent = element.dataset[activeLanguage] || element.dataset.en || "";
    });
    document.querySelectorAll("[data-l10n-content]").forEach((element) => {
      element.setAttribute("content", element.dataset[activeLanguage] || element.dataset.en || "");
    });
    document.querySelectorAll("[data-locale]").forEach((section) => {
      section.hidden = section.dataset.locale !== activeLanguage;
    });
    if (directoryFilter) directoryFilter();
  }

  function initPreferences() {
    const language = document.querySelector("#language-select");
    language?.addEventListener("change", () => applyLanguage(language.value, true));

    const theme = document.querySelector("#theme-select");
    let selectedTheme = "auto";
    try { selectedTheme = localStorage.getItem("theme") || "auto"; } catch (_) { /* no-op */ }
    if (!["auto", "light", "dark"].includes(selectedTheme)) selectedTheme = "auto";
    document.documentElement.dataset.theme = selectedTheme;
    if (theme) theme.value = selectedTheme;
    theme?.addEventListener("change", () => {
      const value = ["auto", "light", "dark"].includes(theme.value) ? theme.value : "auto";
      document.documentElement.dataset.theme = value;
      try { localStorage.setItem("theme", value); } catch (_) { /* no-op */ }
    });

    applyLanguage(initialLanguage());
  }

  function initDirectory() {
    const search = document.querySelector("#search");
    const difficulty = document.querySelector("#difficulty-filter");
    const cards = [...document.querySelectorAll(".site-card")];
    const count = document.querySelector("#result-count");
    const empty = document.querySelector("#empty-state");
    if (!cards.length || !search) return;

    directoryFilter = () => {
      const query = normalize(search.value);
      const level = normalize(difficulty?.value);
      let visible = 0;
      cards.forEach((card) => {
        const haystack = normalize(`${card.dataset.name} ${card.dataset.types} ${card.textContent}`);
        const matchesQuery = !query || haystack.includes(query);
        const matchesLevel = !level || normalize(card.dataset.difficulty) === level;
        const show = matchesQuery && matchesLevel;
        card.hidden = !show;
        if (show) visible += 1;
      });
      if (count) count.textContent = siteCountLabel(visible);
      if (empty) empty.hidden = visible !== 0;
    };
    search.addEventListener("input", directoryFilter);
    difficulty?.addEventListener("change", directoryFilter);
    directoryFilter();
  }

  function initMap() {
    const element = document.querySelector("#map");
    const payload = document.querySelector("#site-data");
    if (!element || !payload || !window.maplibregl) return;

    const sites = JSON.parse(payload.textContent);
    const features = sites.map((site) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [site.longitude, site.latitude] },
      properties: {
        id: site.id,
        name_en: site.name_en,
        name_ru: site.name_ru,
        difficulty: site.difficulty || "not_assigned",
        types_en: site.types_en,
        types_ru: site.types_ru,
      },
    }));

    const map = new maplibregl.Map({
      container: element,
      style: {
        version: 8,
        sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap contributors" } },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      center: features.length ? features[0].geometry.coordinates : [0, 0],
      zoom: features.length > 1 ? 8 : 11,
      cooperativeGestures: true,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    map.on("load", () => {
      map.addSource("sites", { type: "geojson", data: { type: "FeatureCollection", features }, cluster: true, clusterMaxZoom: 13, clusterRadius: 44 });
      map.addLayer({ id: "clusters", type: "circle", source: "sites", filter: ["has", "point_count"], paint: { "circle-color": "#5e6ad2", "circle-radius": ["step", ["get", "point_count"], 18, 10, 24, 30, 31], "circle-stroke-color": "rgba(255,255,255,.76)", "circle-stroke-width": 1 } });
      map.addLayer({ id: "cluster-count", type: "symbol", source: "sites", filter: ["has", "point_count"], layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12 }, paint: { "text-color": "#ffffff" } });
      map.addLayer({ id: "sites", type: "circle", source: "sites", filter: ["!", ["has", "point_count"]], paint: { "circle-color": "#8dd6ee", "circle-radius": 7, "circle-stroke-color": "#08090a", "circle-stroke-width": 2 } });

      map.on("click", "clusters", async (event) => {
        const feature = map.queryRenderedFeatures(event.point, { layers: ["clusters"] })[0];
        const zoom = await map.getSource("sites").getClusterExpansionZoom(feature.properties.cluster_id);
        map.easeTo({ center: feature.geometry.coordinates, zoom });
      });
      map.on("click", "sites", (event) => {
        const feature = event.features[0];
        const title = document.createElement("strong");
        title.textContent = feature.properties[`name_${activeLanguage}`] || feature.properties.name_en;
        const details = document.createElement("span");
        const types = feature.properties[`types_${activeLanguage}`] || feature.properties.types_en;
        details.textContent = `${types} · ${translate(`difficulty_${feature.properties.difficulty}`)}`;
        const content = document.createElement("div");
        content.className = "map-popup";
        content.append(title, details);
        new maplibregl.Popup({ offset: 12 }).setLngLat(feature.geometry.coordinates).setDOMContent(content).addTo(map);
      });
      ["clusters", "sites"].forEach((layer) => {
        map.on("mouseenter", layer, () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", layer, () => { map.getCanvas().style.cursor = ""; });
      });

      if (features.length > 1) {
        const bounds = features.reduce((box, feature) => box.extend(feature.geometry.coordinates), new maplibregl.LngLatBounds(features[0].geometry.coordinates, features[0].geometry.coordinates));
        map.fitBounds(bounds, { padding: 54, maxZoom: 11, duration: 0 });
      }
    });
  }

  window.addEventListener("DOMContentLoaded", () => {
    initPreferences();
    initDirectory();
    initMap();
  });
})();
