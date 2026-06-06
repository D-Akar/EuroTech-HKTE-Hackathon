import { useEffect, useState } from "react";

export type Theme = "dark" | "light";

const STORAGE_KEY = "sentinel-theme";

function initialTheme(): Theme {
  if (typeof window === "undefined") return "dark";
  const saved = window.localStorage.getItem(STORAGE_KEY);
  if (saved === "light" || saved === "dark") return saved;
  return "dark"; // mission-control dark is the default
}

/**
 * Theme state synced to ``data-theme`` on <html> and persisted to localStorage.
 * The CSS keys both palettes off that attribute (dark is the default :root).
 */
export function useTheme(): readonly [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const toggle = () => setTheme((t) => (t === "dark" ? "light" : "dark"));
  return [theme, toggle] as const;
}
