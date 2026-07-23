import { useEffect, useState } from "react";

/** Read the saved theme, falling back to the OS preference. */
export function initialTheme(): "light" | "dark" {
  try {
    const s = localStorage.getItem("edi-theme");
    if (s === "light" || s === "dark") return s;
  } catch {
    /* ignore */
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Theme state that mirrors to <html data-theme> and localStorage.
 *  Persisted, so it stays consistent across the routed pages. */
export function useTheme(): ["light" | "dark", () => void] {
  const [theme, setTheme] = useState(initialTheme);
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("edi-theme", theme);
    } catch {
      /* ignore */
    }
  }, [theme]);
  const toggle = () => setTheme((t) => (t === "dark" ? "light" : "dark"));
  return [theme, toggle];
}
