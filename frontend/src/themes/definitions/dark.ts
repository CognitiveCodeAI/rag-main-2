import type { ThemeConfig } from "../types";

/**
 * Dark Theme - Deep Ocean
 * A sophisticated dark theme with teal undertones and amber accents
 */
export const darkTheme: ThemeConfig = {
  name: "dark",
  label: "Dark",
  category: "standard",
  colors: {
    // Core - Deep ocean base
    background: "oklch(0.12 0.02 220)",
    foreground: "oklch(0.95 0.01 220)",
    
    // Card - Slight teal tint
    card: "oklch(0.16 0.025 220)",
    cardForeground: "oklch(0.95 0.01 220)",
    
    // Popover
    popover: "oklch(0.14 0.02 220)",
    popoverForeground: "oklch(0.95 0.01 220)",
    
    // Primary - Amber/gold
    primary: "oklch(0.78 0.16 70)",
    primaryForeground: "oklch(0.15 0.02 70)",
    
    // Secondary - Teal
    secondary: "oklch(0.25 0.04 200)",
    secondaryForeground: "oklch(0.9 0.02 200)",
    
    // Muted
    muted: "oklch(0.22 0.03 220)",
    mutedForeground: "oklch(0.65 0.02 220)",
    
    // Accent - Cyan pop
    accent: "oklch(0.65 0.15 190)",
    accentForeground: "oklch(0.98 0 0)",
    
    // Destructive
    destructive: "oklch(0.65 0.22 25)",
    
    // Border & Input
    border: "oklch(0.28 0.03 220)",
    input: "oklch(0.22 0.025 220)",
    ring: "oklch(0.78 0.16 70)",
    
    // Charts
    chart1: "oklch(0.78 0.16 70)",
    chart2: "oklch(0.65 0.15 190)",
    chart3: "oklch(0.7 0.18 140)",
    chart4: "oklch(0.75 0.14 300)",
    chart5: "oklch(0.68 0.2 25)",
    
    // Sidebar
    sidebar: "oklch(0.1 0.015 220)",
    sidebarForeground: "oklch(0.9 0.01 220)",
    sidebarPrimary: "oklch(0.78 0.16 70)",
    sidebarPrimaryForeground: "oklch(0.15 0.02 70)",
    sidebarAccent: "oklch(0.2 0.03 220)",
    sidebarAccentForeground: "oklch(0.9 0.02 200)",
    sidebarBorder: "oklch(0.25 0.025 220)",
    sidebarRing: "oklch(0.78 0.16 70)",
  },
  fonts: {
    sans: "'Outfit', system-ui, sans-serif",
    mono: "'JetBrains Mono', monospace",
  },
};
