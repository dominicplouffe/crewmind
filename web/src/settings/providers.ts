/** The providers' display names, loaded once per page from `GET /v1/models/providers`. */
import { useCallback } from "react";
import { get } from "../api/client";
import { useLoad } from "../lib/useLoad";
import { humanizeName } from "../lib/settingsMeta";

export function useProviderLabels(): (name: string) => string {
  const providers = useLoad(() => get("/v1/models/providers"), []);
  const items = providers.data?.items;
  return useCallback(
    (name: string) => {
      const label = items?.find((item) => item.name === name)?.label;
      return label ? label.replace(/\s*\(.*\)\s*$/, "") : humanizeName(name);
    },
    [items],
  );
}
