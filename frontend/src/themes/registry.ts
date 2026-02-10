/**
 * Theme Registry
 * Central registry for all available themes
 */

import type { ThemeConfig, ThemeName, ThemeCategory } from "./types";
import { darkTheme, lightTheme } from "./definitions";

/**
 * Registry of all available themes
 */
export const themeRegistry: Map<ThemeName, ThemeConfig> = new Map([
  ["dark", darkTheme],
  ["light", lightTheme],
  // Seasonal themes will be added here:
  // ["spring", springTheme],
  // ["summer", summerTheme],
  // ["autumn", autumnTheme],
  // ["winter", winterTheme],
]);

/**
 * Get a theme by name
 */
export function getTheme(name: ThemeName): ThemeConfig | undefined {
  return themeRegistry.get(name);
}

/**
 * Get all available theme names
 */
export function getAllThemes(): ThemeName[] {
  return Array.from(themeRegistry.keys());
}

/**
 * Get themes by category
 */
export function getThemesByCategory(category: ThemeCategory): ThemeConfig[] {
  return Array.from(themeRegistry.values()).filter(
    (theme) => theme.category === category
  );
}

/**
 * Check if a theme exists
 */
export function hasTheme(name: string): name is ThemeName {
  return themeRegistry.has(name as ThemeName);
}

/**
 * Register a new theme (for custom/plugin themes)
 */
export function registerTheme(theme: ThemeConfig): void {
  themeRegistry.set(theme.name, theme);
}
