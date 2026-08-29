(() => {
  "use strict";

  const normalize = (value) => (value || "").toLocaleLowerCase().trim();

  function initDirectory() {
    const search = document.querySelector("#search");
    const difficulty = document.querySelector("#difficulty-filter");
    const cards = [...document.querySelectorAll(".site-card")];
    const count = document.querySelector("#result-count");
    const empty = document.querySelector("#empty-state");
    if (!cards.length || !search) return;

    const filter = () => {
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
      if (count) count.textContent = `${visible} ${visible === 1 ? "site" : "sites"}`;
      if (empty) empty.hidden = visible !== 0;
    };
    search.addEventListener("input", filter);
    difficulty?.addEventListener("change", filter);
  }

  function initLocales() {
    const buttons = [...document.querySelectorAll("[data-locale-target]")];
    if (!buttons.length) return;
    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        const locale = button.dataset.localeTarget;
        buttons.forEach((item) => item.classList.toggle("active", item === button));
        document.querySelectorAll("[data-locale]").forEach((section) => {
          section.hidden = section.dataset.locale !== locale;
        });
        document.documentElement.lang = locale;
      });
    });
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
        name: site.name,
        confidence: site.confidence,
        difficulty: site.difficulty || "Not assigned",
        types: site.types.join(", "),
      },
    }));

    const map = new maplibregl.Map({
      container: element,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [{ id: "osm", type: "raster", source: "osm" }],
      },
      center: features.length ? features[0].geometry.coordinates : [0, 0],
      zoom: features.length > 1 ? 8 : 11,
      cooperativeGestures: true,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    map.on("load", () => {
      map.addSource("sites", {
        type: "geojson",
        data: { type: "FeatureCollection", features },
        cluster: true,
        clusterMaxZoom: 13,
        clusterRadius: 44,
      });
      map.addLayer({
        id: "clusters",
        type: "circle",
        source: "sites",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#5e6ad2",
          "circle-radius": ["step", ["get", "point_count"], 18, 10, 24, 30, 31],
          "circle-stroke-color": "rgba(255,255,255,.76)",
          "circle-stroke-width": 1,
        },
      });
      map.addLayer({
        id: "cluster-count",
        type: "symbol",
        source: "sites",
        filter: ["has", "point_count"],
        layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12 },
        paint: { "text-color": "#ffffff" },
      });
      map.addLayer({
        id: "sites",
        type: "circle",
        source: "sites",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": "#8dd6ee",
          "circle-radius": 7,
          "circle-stroke-color": "#08090a",
          "circle-stroke-width": 2,
        },
      });

      map.on("click", "clusters", async (event) => {
        const feature = map.queryRenderedFeatures(event.point, { layers: ["clusters"] })[0];
        const zoom = await map.getSource("sites").getClusterExpansionZoom(feature.properties.cluster_id);
        map.easeTo({ center: feature.geometry.coordinates, zoom });
      });
      map.on("click", "sites", (event) => {
        const feature = event.features[0];
        const title = document.createElement("strong");
        title.textContent = feature.properties.name;
        const details = document.createElement("span");
        details.textContent = `${feature.properties.types} · ${feature.properties.confidence}`;
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
        const bounds = features.reduce(
          (box, feature) => box.extend(feature.geometry.coordinates),
          new maplibregl.LngLatBounds(features[0].geometry.coordinates, features[0].geometry.coordinates),
        );
        map.fitBounds(bounds, { padding: 54, maxZoom: 11, duration: 0 });
      }
    });
  }

  window.addEventListener("DOMContentLoaded", () => {
    initDirectory();
    initLocales();
    initMap();
  });
})();
