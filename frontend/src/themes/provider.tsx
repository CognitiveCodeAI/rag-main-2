"use client";

/**
 * Theme Provider
 * React context provider for theme management
 */

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useMemo,
  type ReactNode,
} from "react";
import type { ThemeName, ThemeContextValue } from "./types";
import { getAllThemes } from "./registry";
import {
  applyTheme,
  getSystemTheme,
  getStoredTheme,
  storeTheme,
  subscribeToSystemTheme,
} from "./utils";

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

interface ThemeProviderProps {
  children: ReactNode;
  defaultTheme?: ThemeName;
  storageKey?: string;
  enableSystem?: boolean;
}

export function ThemeProvider({
  children,
  defaultTheme = "dark",
  enableSystem = true,
}: ThemeProviderProps) {
  const initialTheme = useMemo<ThemeName>(() => {
    const stored = getStoredTheme();
    if (stored) return stored;
    if (enableSystem) return getSystemTheme();
    return defaultTheme;
  }, [defaultTheme, enableSystem]);

  const [theme, setThemeState] = useState<ThemeName>(initialTheme);
  const resolvedTheme = theme;

  // Apply theme when it changes (after mount)
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // Listen for system theme changes
  useEffect(() => {
    if (!enableSystem) return;

    return subscribeToSystemTheme((systemTheme) => {
      // Only auto-switch if user hasn't set a preference
      const stored = getStoredTheme();
      if (!stored) {
        setThemeState(systemTheme);
      }
    });
  }, [enableSystem]);

  const setTheme = useCallback((newTheme: ThemeName) => {
    setThemeState(newTheme);
    storeTheme(newTheme);
  }, []);

  const value: ThemeContextValue = {
    theme,
    setTheme,
    resolvedTheme,
    themes: getAllThemes(),
  };

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

/**
 * Hook to access theme context
 */
export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  
  if (context === undefined) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  
  return context;
}
