"use client";

/**
 * Theme Switcher Component
 * UI control for switching between themes
 */

import * as React from "react";
import { useTheme, type ThemeName } from "@/themes";
import { Button } from "@/components/ui/button";
import { Sun, Moon, Monitor } from "lucide-react";

interface ThemeSwitcherProps {
  showLabels?: boolean;
  className?: string;
}

const themeIcons: Record<ThemeName, typeof Sun> = {
  light: Sun,
  dark: Moon,
  // Seasonal themes will use appropriate icons
  spring: Sun,
  summer: Sun,
  autumn: Sun,
  winter: Moon,
};

const themeLabels: Record<ThemeName, string> = {
  light: "Light",
  dark: "Dark",
  spring: "Spring",
  summer: "Summer",
  autumn: "Autumn",
  winter: "Winter",
};

export function ThemeSwitcher({ showLabels = false, className }: ThemeSwitcherProps) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  // Avoid hydration mismatch by only rendering after mount
  React.useEffect(() => {
    setMounted(true);
  }, []);

  // Simple toggle between dark and light for now
  const toggleTheme = () => {
    setTheme(theme === "dark" ? "light" : "dark");
  };

  // Use Moon as default icon during SSR (matches defaultTheme="dark")
  const Icon = mounted ? (themeIcons[theme] || Monitor) : Moon;
  const nextTheme = theme === "dark" ? "light" : "dark";

  return (
    <Button
      variant="ghost"
      size={showLabels ? "default" : "icon"}
      onClick={toggleTheme}
      className={className}
      title={`Switch to ${nextTheme} theme`}
      suppressHydrationWarning
    >
      <Icon className="h-4 w-4" />
      {showLabels && <span className="ml-2">{mounted ? themeLabels[theme] : "Dark"}</span>}
    </Button>
  );
}

/**
 * Theme Selector - Full dropdown with all available themes
 */
export function ThemeSelector({ className }: { className?: string }) {
  const { theme, setTheme, themes } = useTheme();

  return (
    <div className={`flex gap-1 ${className || ""}`}>
      {themes.map((themeName) => {
        const Icon = themeIcons[themeName] || Monitor;
        const isActive = theme === themeName;
        
        return (
          <Button
            key={themeName}
            variant={isActive ? "secondary" : "ghost"}
            size="sm"
            onClick={() => setTheme(themeName)}
            className={isActive ? "bg-primary/10" : ""}
          >
            <Icon className="h-4 w-4 mr-1" />
            {themeLabels[themeName]}
          </Button>
        );
      })}
    </div>
  );
}
