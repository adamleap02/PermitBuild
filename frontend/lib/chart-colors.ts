"use client";

import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

/**
 * Categorical/status palette lifted from the dataviz skill's validated
 * reference instance (references/palette.md) -- run through
 * scripts/validate_palette.js: worst adjacent CVD delta 9.1 light / 8.4
 * dark (>= 8 target), worst adjacent normal-vision delta 19.6 light /
 * 19.3 dark (>= 15 floor). Assign these in fixed order; never cycle or
 * reassign per-render.
 */
export const CATEGORICAL_LIGHT = [
  "#2a78d6", // 1 blue
  "#eb6834", // 2 orange
  "#1baf7a", // 3 aqua
  "#eda100", // 4 yellow
  "#e87ba4", // 5 magenta
  "#008300", // 6 green
  "#4a3aa7", // 7 violet
  "#e34948", // 8 red
];

export const CATEGORICAL_DARK = [
  "#3987e5",
  "#d95926",
  "#199e70",
  "#c98500",
  "#d55181",
  "#008300",
  "#9085e9",
  "#e66767",
];

export const CHART_CHROME_LIGHT = {
  surface: "#fcfcfb",
  primaryInk: "#0b0b0b",
  secondaryInk: "#52514e",
  mutedInk: "#898781",
  gridline: "#e1e0d9",
  baseline: "#c3c2b7",
};

export const CHART_CHROME_DARK = {
  surface: "#1a1a19",
  primaryInk: "#ffffff",
  secondaryInk: "#c3c2b7",
  mutedInk: "#898781",
  gridline: "#2c2c2a",
  baseline: "#383835",
};

export const SEQUENTIAL_BLUE_LIGHT = "#2a78d6";
export const SEQUENTIAL_BLUE_DARK = "#3987e5";

/** Resolves the current chart palette against the active theme (light/dark). */
export function useChartPalette() {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const isDark = mounted && resolvedTheme === "dark";
  return {
    isDark,
    categorical: isDark ? CATEGORICAL_DARK : CATEGORICAL_LIGHT,
    chrome: isDark ? CHART_CHROME_DARK : CHART_CHROME_LIGHT,
    sequential: isDark ? SEQUENTIAL_BLUE_DARK : SEQUENTIAL_BLUE_LIGHT,
  };
}

/** Assigns a fixed-order categorical color to the Nth series/category. */
export function categoricalColor(index: number, isDark: boolean): string {
  const palette = isDark ? CATEGORICAL_DARK : CATEGORICAL_LIGHT;
  return palette[index % palette.length];
}
