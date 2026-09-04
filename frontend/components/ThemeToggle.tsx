"use client";

import { Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";

type Theme = "light" | "dark";

function subscribeToTheme(onStoreChange: () => void) {
  const observer = new MutationObserver(onStoreChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => observer.disconnect();
}

function getThemeSnapshot(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

function getServerThemeSnapshot(): null {
  return null;
}

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribeToTheme, getThemeSnapshot, getServerThemeSnapshot);

  function toggle() {
    const root = document.documentElement;
    const next = !root.classList.contains("dark");
    root.classList.add("theme-changing");
    root.classList.toggle("dark", next);
    try {
      localStorage.setItem("civicscope-theme", next ? "dark" : "light");
    } catch {
      // Storage can be unavailable in hardened/private contexts; the in-page
      // theme change should still complete normally.
    }
    window.requestAnimationFrame(() => root.classList.remove("theme-changing"));
  }

  const isDark = theme === "dark";
  const actionLabel = theme === null
    ? "Switch color theme"
    : `Switch to ${isDark ? "light" : "dark"} theme`;

  return (
    <button
      type="button"
      onClick={toggle}
      className="grid h-11 w-11 shrink-0 place-items-center rounded-md border border-civic-line text-civic-muted transition hover:bg-civic-subtle hover:text-civic-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-civic-teal focus-visible:ring-offset-2 focus-visible:ring-offset-civic-surface"
      aria-label="Dark theme"
      aria-pressed={isDark}
      title={actionLabel}
    >
      <Sun className="hidden h-4 w-4 dark:block" aria-hidden="true" />
      <Moon className="h-4 w-4 dark:hidden" aria-hidden="true" />
    </button>
  );
}
