import type { ThemeConfig } from "../types";

/**
 * Light Theme - Cognitive Code
 * A clean light theme with teal primary accents
 */
export const lightTheme: ThemeConfig = {
  name: "light",
  label: "Light",
  category: "standard",
  colors: {
    // Core - Clean white base
    background: "oklch(0.98 0.005 220)",
    foreground: "oklch(0.15 0.03 240)",

    // Card - Pure white
    card: "oklch(1 0 0)",
    cardForeground: "oklch(0.15 0.03 240)",

    // Popover
    popover: "oklch(1 0 0)",
    popoverForeground: "oklch(0.15 0.03 240)",

    // Primary - Cognitive Code Teal
    primary: "oklch(0.55 0.14 180)",
    primaryForeground: "oklch(0.98 0.01 180)",

    // Secondary - Light gray
    secondary: "oklch(0.94 0.01 220)",
    secondaryForeground: "oklch(0.25 0.03 240)",

    // Muted
    muted: "oklch(0.95 0.01 220)",
    mutedForeground: "oklch(0.45 0.02 240)",

    // Accent - Vibrant teal
    accent: "oklch(0.65 0.12 180)",
    accentForeground: "oklch(0.15 0.02 180)",

    // Destructive
    destructive: "oklch(0.55 0.25 25)",

    // Border & Input
    border: "oklch(0.88 0.01 220)",
    input: "oklch(0.92 0.01 220)",
    ring: "oklch(0.55 0.14 180)",

    // Charts - Teal-inspired palette
    chart1: "oklch(0.55 0.14 180)",
    chart2: "oklch(0.50 0.12 200)",
    chart3: "oklch(0.55 0.15 160)",
    chart4: "oklch(0.52 0.1 220)",
    chart5: "oklch(0.58 0.16 140)",

    // Sidebar
    sidebar: "oklch(0.97 0.005 220)",
    sidebarForeground: "oklch(0.15 0.03 240)",
    sidebarPrimary: "oklch(0.55 0.14 180)",
    sidebarPrimaryForeground: "oklch(0.98 0.01 180)",
    sidebarAccent: "oklch(0.93 0.01 220)",
    sidebarAccentForeground: "oklch(0.25 0.03 240)",
    sidebarBorder: "oklch(0.88 0.01 220)",
    sidebarRing: "oklch(0.55 0.14 180)",
  },
  fonts: {
    sans: "'Outfit', system-ui, sans-serif",
    mono: "'JetBrains Mono', monospace",
  },
};
