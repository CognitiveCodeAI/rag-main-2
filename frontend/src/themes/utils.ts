/**
 * Theme Utilities
 * Helper functions for theme management
 */

import type { ThemeConfig, ThemeColors, ThemeName, StandardTheme } from "./types";
import { getTheme } from "./registry";

/**
 * Convert camelCase to kebab-case
 */
function toKebabCase(str: string): string {
  return str.replace(/([a-z0-9])([A-Z])/g, "$1-$2").toLowerCase();
}

/**
 * Apply a theme by setting CSS custom properties on the root element
 */
export function applyTheme(themeName: ThemeName): void {
  const theme = getTheme(themeName);
  if (!theme) {
    console.warn(`Theme "${themeName}" not found`);
    return;
  }

  const root = document.documentElement;
  
  // Apply color variables
  const colorEntries = Object.entries(theme.colors) as [keyof ThemeColors, string][];
  for (const [key, value] of colorEntries) {
    const cssVar = `--${toKebabCase(key)}`;
    root.style.setProperty(cssVar, value);
  }

  // Apply font variables if defined
  if (theme.fonts?.sans) {
    root.style.setProperty("--font-sans", theme.fonts.sans);
  }
  if (theme.fonts?.mono) {
    root.style.setProperty("--font-mono", theme.fonts.mono);
  }

  // Update data attribute for CSS selectors
  root.setAttribute("data-theme", themeName);
  
  // Update class for Tailwind dark mode
  if (themeName === "dark") {
    root.classList.add("dark");
  } else {
    root.classList.remove("dark");
  }
}

/**
 * Get the system's preferred color scheme
 */
export function getSystemTheme(): StandardTheme {
  if (typeof window === "undefined") {
    return "dark"; // SSR default
  }
  
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

/**
 * Subscribe to system theme changes
 */
export function subscribeToSystemTheme(
  callback: (theme: StandardTheme) => void
): () => void {
  if (typeof window === "undefined") {
    return () => {};
  }

  const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
  
  const handler = (e: MediaQueryListEvent) => {
    callback(e.matches ? "dark" : "light");
  };

  mediaQuery.addEventListener("change", handler);
  
  return () => {
    mediaQuery.removeEventListener("change", handler);
  };
}

/**
 * Get stored theme from localStorage
 */
export function getStoredTheme(): ThemeName | null {
  if (typeof window === "undefined") {
    return null;
  }
  
  const stored = localStorage.getItem("npr-theme");
  return stored as ThemeName | null;
}

/**
 * Store theme in localStorage
 */
export function storeTheme(theme: ThemeName): void {
  if (typeof window === "undefined") {
    return;
  }
  
  localStorage.setItem("npr-theme", theme);
}

/**
 * Generate CSS variables string for a theme (useful for SSR)
 */
export function generateThemeCSS(theme: ThemeConfig): string {
  const colorEntries = Object.entries(theme.colors) as [keyof ThemeColors, string][];
  const cssVars = colorEntries
    .map(([key, value]) => `  --${toKebabCase(key)}: ${value};`)
    .join("\n");

  let fontVars = "";
  if (theme.fonts?.sans) {
    fontVars += `  --font-sans: ${theme.fonts.sans};\n`;
  }
  if (theme.fonts?.mono) {
    fontVars += `  --font-mono: ${theme.fonts.mono};\n`;
  }

  return `:root[data-theme="${theme.name}"] {\n${cssVars}\n${fontVars}}`;
}
