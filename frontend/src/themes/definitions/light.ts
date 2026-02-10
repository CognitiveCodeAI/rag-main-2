import type { ThemeConfig } from "../types";

/**
 * Light Theme - Warm Ivory
 * A clean light theme with warm undertones and deep teal accents
 */
export const lightTheme: ThemeConfig = {
  name: "light",
  label: "Light",
  category: "standard",
  colors: {
    // Core - Warm ivory base
    background: "oklch(0.98 0.01 90)",
    foreground: "oklch(0.15 0.02 220)",
    
    // Card - Pure white with subtle warmth
    card: "oklch(1 0 0)",
    cardForeground: "oklch(0.15 0.02 220)",
    
    // Popover
    popover: "oklch(1 0 0)",
    popoverForeground: "oklch(0.15 0.02 220)",
    
    // Primary - Deep teal
    primary: "oklch(0.45 0.12 200)",
    primaryForeground: "oklch(0.98 0.01 90)",
    
    // Secondary - Warm gray
    secondary: "oklch(0.94 0.01 90)",
    secondaryForeground: "oklch(0.25 0.02 220)",
    
    // Muted
    muted: "oklch(0.95 0.01 90)",
    mutedForeground: "oklch(0.45 0.02 220)",
    
    // Accent - Vibrant amber
    accent: "oklch(0.75 0.18 60)",
    accentForeground: "oklch(0.15 0.02 60)",
    
    // Destructive
    destructive: "oklch(0.55 0.25 25)",
    
    // Border & Input
    border: "oklch(0.88 0.01 90)",
    input: "oklch(0.92 0.01 90)",
    ring: "oklch(0.45 0.12 200)",
    
    // Charts
    chart1: "oklch(0.45 0.12 200)",
    chart2: "oklch(0.75 0.18 60)",
    chart3: "oklch(0.6 0.15 140)",
    chart4: "oklch(0.55 0.18 300)",
    chart5: "oklch(0.58 0.2 25)",
    
    // Sidebar
    sidebar: "oklch(0.96 0.01 90)",
    sidebarForeground: "oklch(0.15 0.02 220)",
    sidebarPrimary: "oklch(0.45 0.12 200)",
    sidebarPrimaryForeground: "oklch(0.98 0.01 90)",
    sidebarAccent: "oklch(0.92 0.01 90)",
    sidebarAccentForeground: "oklch(0.25 0.02 220)",
    sidebarBorder: "oklch(0.88 0.01 90)",
    sidebarRing: "oklch(0.45 0.12 200)",
  },
  fonts: {
    sans: "'Outfit', system-ui, sans-serif",
    mono: "'JetBrains Mono', monospace",
  },
};
