/** The ⌘K palette's items: the shell's own, plus whatever the current page registers. */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { PaletteItem } from "../components/CommandPalette";

interface PaletteValue {
  pageItems: PaletteItem[];
  setPageItems(items: PaletteItem[]): void;
  open: boolean;
  setOpen(open: boolean): void;
}

const PaletteContext = createContext<PaletteValue | null>(null);

export function PaletteProvider({ children }: { children: ReactNode }): JSX.Element {
  const [pageItems, setPageItems] = useState<PaletteItem[]>([]);
  const [open, setOpen] = useState(false);
  const value = useMemo(() => ({ pageItems, setPageItems, open, setOpen }), [pageItems, open]);
  return <PaletteContext.Provider value={value}>{children}</PaletteContext.Provider>;
}

export function usePalette(): PaletteValue {
  const value = useContext(PaletteContext);
  if (!value) throw new Error("usePalette needs a PaletteProvider");
  return value;
}

/** Adds a page's items to the palette while the page is shown. */
export function usePaletteItems(items: PaletteItem[]): void {
  const { setPageItems } = usePalette();
  useEffect(() => {
    setPageItems(items);
  }, [items, setPageItems]);
  useEffect(() => () => setPageItems([]), [setPageItems]);
}
