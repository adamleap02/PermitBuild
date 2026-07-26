"use client";

import * as React from "react";
import maplibregl, { type GeoJSONSource, type Map as MapLibreMap } from "maplibre-gl";
import { useTheme } from "next-themes";

import type { PermitListItem } from "@/lib/types";
import { bestCost, formatCurrency, formatDate } from "@/lib/utils";

// Free, self-hostable vector tile style -- no API key required, no rate
// limit for reasonable use. See BLOCKERS.md for the tradeoffs at real
// production scale (self-host vs. a paid provider's SLA).
const MAP_STYLE_LIGHT = "https://tiles.openfreemap.org/styles/liberty";
const MAP_STYLE_DARK = "https://tiles.openfreemap.org/styles/dark";

const SOURCE_ID = "permits";
const CLUSTER_LAYER = "permit-clusters";
const CLUSTER_COUNT_LAYER = "permit-cluster-count";
const POINT_LAYER = "permit-points";

// Categorical slot 1 (blue) from the dataviz palette -- see lib/chart-colors.ts.
const POINT_COLOR = "#2a78d6";
const POINT_COLOR_DARK = "#3987e5";

function permitsToGeoJSON(items: PermitListItem[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: items
      .filter((p) => typeof p.latitude === "number" && typeof p.longitude === "number")
      .map((p) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [p.longitude as number, p.latitude as number] },
        properties: {
          id: p.id,
          permit_number: p.permit_number,
          permit_type: p.permit_type ?? "Unknown type",
          status: p.status ?? "unknown",
          address: p.property_address ?? "Address unavailable",
          value: bestCost(p),
          issue_date: p.issue_date,
        },
      })),
  };
}

interface ResultsMapProps {
  items: PermitListItem[];
}

export function ResultsMap({ items }: ResultsMapProps) {
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const mapRef = React.useRef<MapLibreMap | null>(null);
  const popupRef = React.useRef<maplibregl.Popup | null>(null);
  const { resolvedTheme } = useTheme();
  const [ready, setReady] = React.useState(false);

  // Initialize the map once.
  React.useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: resolvedTheme === "dark" ? MAP_STYLE_DARK : MAP_STYLE_LIGHT,
      center: [-98.5, 39.8],
      zoom: 3.2,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;

    map.on("load", () => {
      map.addSource(SOURCE_ID, {
        type: "geojson",
        data: permitsToGeoJSON(items),
        cluster: true,
        clusterMaxZoom: 13,
        clusterRadius: 45,
      });

      map.addLayer({
        id: CLUSTER_LAYER,
        type: "circle",
        source: SOURCE_ID,
        filter: ["has", "point_count"],
        paint: {
          "circle-color": resolvedTheme === "dark" ? POINT_COLOR_DARK : POINT_COLOR,
          "circle-opacity": 0.85,
          "circle-radius": ["step", ["get", "point_count"], 16, 10, 22, 25, 30],
          "circle-stroke-width": 2,
          "circle-stroke-color": "#fff",
        },
      });

      map.addLayer({
        id: CLUSTER_COUNT_LAYER,
        type: "symbol",
        source: SOURCE_ID,
        filter: ["has", "point_count"],
        layout: {
          "text-field": ["get", "point_count_abbreviated"],
          "text-font": ["Noto Sans Bold"],
          "text-size": 12,
        },
        paint: { "text-color": "#ffffff" },
      });

      map.addLayer({
        id: POINT_LAYER,
        type: "circle",
        source: SOURCE_ID,
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": resolvedTheme === "dark" ? POINT_COLOR_DARK : POINT_COLOR,
          "circle-radius": 7,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#fff",
        },
      });

      map.on("click", CLUSTER_LAYER, (e) => {
        const features = map.queryRenderedFeatures(e.point, { layers: [CLUSTER_LAYER] });
        const clusterId = features[0]?.properties?.cluster_id;
        const source = map.getSource(SOURCE_ID) as GeoJSONSource;
        if (clusterId === undefined) return;
        source.getClusterExpansionZoom(clusterId).then((zoom) => {
          const geometry = features[0].geometry as GeoJSON.Point;
          map.easeTo({ center: geometry.coordinates as [number, number], zoom });
        });
      });

      map.on("click", POINT_LAYER, (e) => {
        const feature = e.features?.[0];
        if (!feature) return;
        const props = feature.properties as Record<string, string | number | null>;
        const geometry = feature.geometry as GeoJSON.Point;

        popupRef.current?.remove();
        const el = document.createElement("div");
        el.className = "text-sm min-w-[220px]";
        el.innerHTML = `
          <p class="font-semibold">${props.permit_type}</p>
          <p class="text-xs text-muted-foreground mb-1">${props.permit_number}</p>
          <p class="mb-1">${props.address}</p>
          <p class="mb-1"><span class="font-medium">Status:</span> ${props.status}</p>
          <p class="mb-2"><span class="font-medium">Value:</span> ${formatCurrency(
            props.value === null ? null : Number(props.value)
          )} &middot; <span class="font-medium">Issued:</span> ${formatDate(
          props.issue_date as string | null
        )}</p>
          <a href="/permits/${props.id}" class="text-primary underline underline-offset-2">View details &rarr;</a>
        `;

        popupRef.current = new maplibregl.Popup({ closeButton: true, maxWidth: "280px" })
          .setLngLat(geometry.coordinates as [number, number])
          .setDOMContent(el)
          .addTo(map);
      });

      map.on("mouseenter", POINT_LAYER, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", POINT_LAYER, () => (map.getCanvas().style.cursor = ""));
      map.on("mouseenter", CLUSTER_LAYER, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", CLUSTER_LAYER, () => (map.getCanvas().style.cursor = ""));

      setReady(true);
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update the data source when results change.
  React.useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const source = map.getSource(SOURCE_ID) as GeoJSONSource | undefined;
    if (!source) return;
    source.setData(permitsToGeoJSON(items));

    const withCoords = items.filter(
      (p) => typeof p.latitude === "number" && typeof p.longitude === "number"
    );
    if (withCoords.length > 0) {
      const bounds = new maplibregl.LngLatBounds();
      withCoords.forEach((p) => bounds.extend([p.longitude as number, p.latitude as number]));
      map.fitBounds(bounds, { padding: 60, maxZoom: 12, duration: 500 });
    }
  }, [items, ready]);

  return (
    <div className="relative h-[600px] w-full overflow-hidden rounded-b-lg">
      <div ref={containerRef} className="h-full w-full" />
      {items.filter((p) => p.latitude && p.longitude).length === 0 && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-background/70">
          <p className="rounded-md border border-border bg-background px-4 py-2 text-sm text-muted-foreground">
            No geocoded results to plot for this page of filters.
          </p>
        </div>
      )}
    </div>
  );
}
