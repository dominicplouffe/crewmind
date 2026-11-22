/** The theme context: System, Light or Dark. The choice lives in the user menu and in Settings. */
import { createContext, useContext, type ReactNode } from "react";
import { useTheme, type ThemeValue } from "../theme";

const ThemeContext = createContext<ThemeValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }): JSX.Element {
  const value = useTheme();
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useThemeContext(): ThemeValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useThemeContext needs a ThemeProvider");
  return value;
}
