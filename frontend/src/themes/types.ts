/**
 * Theme system types for NPR
 * Supports standard themes (dark/light) and seasonal themes
 */

export type ThemeCategory = "standard" | "seasonal" | "custom";

export type StandardTheme = "dark" | "light";
export type SeasonalTheme = "spring" | "summer" | "autumn" | "winter";
export type ThemeName = StandardTheme | SeasonalTheme;

export interface ThemeColors {
  // Core
  background: string;
  foreground: string;
  
  // Card
  card: string;
  cardForeground: string;
  
  // Popover
  popover: string;
  popoverForeground: string;
  
  // Primary
  primary: string;
  primaryForeground: string;
  
  // Secondary
  secondary: string;
  secondaryForeground: string;
  
  // Muted
  muted: string;
  mutedForeground: string;
  
  // Accent
  accent: string;
  accentForeground: string;
  
  // Destructive
  destructive: string;
  
  // Border & Input
  border: string;
  input: string;
  ring: string;
  
  // Charts
  chart1: string;
  chart2: string;
  chart3: string;
  chart4: string;
  chart5: string;
  
  // Sidebar
  sidebar: string;
  sidebarForeground: string;
  sidebarPrimary: string;
  sidebarPrimaryForeground: string;
  sidebarAccent: string;
  sidebarAccentForeground: string;
  sidebarBorder: string;
  sidebarRing: string;
}

export interface ThemeConfig {
  name: ThemeName;
  label: string;
  category: ThemeCategory;
  colors: ThemeColors;
  fonts?: {
    sans?: string;
    mono?: string;
  };
}

export interface ThemeContextValue {
  theme: ThemeName;
  setTheme: (theme: ThemeName) => void;
  resolvedTheme: ThemeName;
  themes: ThemeName[];
}
