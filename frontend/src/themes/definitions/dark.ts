import type { ThemeConfig } from "../types";

/**
 * Dark Theme - Cognitive Code
 * A sophisticated dark theme with teal primary and navy undertones
 */
export const darkTheme: ThemeConfig = {
  name: "dark",
  label: "Dark",
  category: "standard",
  colors: {
    // Core - Deep navy base
    background: "oklch(0.13 0.025 240)",
    foreground: "oklch(0.95 0.01 220)",

    // Card - Slight navy tint
    card: "oklch(0.17 0.03 240)",
    cardForeground: "oklch(0.95 0.01 220)",

    // Popover
    popover: "oklch(0.15 0.025 240)",
    popoverForeground: "oklch(0.95 0.01 220)",

    // Primary - Cognitive Code Teal
    primary: "oklch(0.72 0.14 180)",
    primaryForeground: "oklch(0.12 0.02 180)",

    // Secondary - Muted teal
    secondary: "oklch(0.25 0.04 200)",
    secondaryForeground: "oklch(0.9 0.02 200)",

    // Muted
    muted: "oklch(0.22 0.03 240)",
    mutedForeground: "oklch(0.65 0.02 220)",

    // Accent - Lighter teal pop
    accent: "oklch(0.68 0.12 185)",
    accentForeground: "oklch(0.98 0 0)",

    // Destructive
    destructive: "oklch(0.65 0.22 25)",

    // Border & Input
    border: "oklch(0.28 0.03 240)",
    input: "oklch(0.22 0.025 240)",
    ring: "oklch(0.72 0.14 180)",

    // Charts - Teal-inspired palette
    chart1: "oklch(0.72 0.14 180)",
    chart2: "oklch(0.65 0.12 200)",
    chart3: "oklch(0.7 0.15 160)",
    chart4: "oklch(0.68 0.1 220)",
    chart5: "oklch(0.75 0.16 140)",

    // Sidebar
    sidebar: "oklch(0.11 0.02 240)",
    sidebarForeground: "oklch(0.9 0.01 220)",
    sidebarPrimary: "oklch(0.72 0.14 180)",
    sidebarPrimaryForeground: "oklch(0.12 0.02 180)",
    sidebarAccent: "oklch(0.2 0.03 240)",
    sidebarAccentForeground: "oklch(0.9 0.02 200)",
    sidebarBorder: "oklch(0.25 0.025 240)",
    sidebarRing: "oklch(0.72 0.14 180)",
  },
  fonts: {
    sans: "'Outfit', system-ui, sans-serif",
    mono: "'JetBrains Mono', monospace",
  },
};
