/**
 * The names of the install's admins, for telling a member whom to ask. Listing people is an
 * admin operation, so for a member the server usually refuses; then this is empty and the
 * wording falls back to "an admin".
 */
import { useEffect, useState } from "react";
import { get } from "../api/client";

export function useAdminNames(enabled = true): string[] {
  const [names, setNames] = useState<string[]>([]);
  useEffect(() => {
    if (!enabled) return;
    let current = true;
    get("/v1/people/list", {})
      .then((page) => {
        if (current) setNames(page.items.filter((person) => person.role === "admin" && person.state === "active").map((person) => person.name));
      })
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [enabled]);
  return names;
}

/** "Ada", "Ada or Sol", "Ada, Sol or Rey". */
export function orList(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}`;
}
