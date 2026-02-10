/**
 * Theme System Index
 * Central export for all theme-related functionality
 */

// Types
export type {
  ThemeCategory,
  StandardTheme,
  SeasonalTheme,
  ThemeName,
  ThemeColors,
  ThemeConfig,
  ThemeContextValue,
} from "./types";

// Theme definitions
export { darkTheme, lightTheme } from "./definitions";

// Registry
export { themeRegistry, getTheme, getAllThemes, getThemesByCategory } from "./registry";

// Provider (will be created next)
export { ThemeProvider, useTheme } from "./provider";

// Utils
export { applyTheme, getSystemTheme } from "./utils";
