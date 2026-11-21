/** Switches between the light and dark themes. */
import { createContext, useContext, type ReactNode } from "react";
import { useTheme, type Theme } from "../theme";
import { t } from "../strings";

const ThemeContext = createContext<{ theme: Theme; toggle(): void } | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }): JSX.Element {
  const value = useTheme();
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useThemeContext(): { theme: Theme; toggle(): void } {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useThemeContext needs a ThemeProvider");
  return value;
}

export function ThemeButton(): JSX.Element {
  const { theme, toggle } = useThemeContext();
  return (
    <button type="button" className="button" onClick={toggle} aria-pressed={theme === "dark"}>
      {t.theme.dark}
    </button>
  );
}
