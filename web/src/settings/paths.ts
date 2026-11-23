/** Addresses of the Settings sections, for links from elsewhere in the app. */
export type SectionId = "profile" | "notifications" | "models" | "founder" | "people" | "install";

/** `/settings/founder`, or `/settings/founder?return=/draft/abc` to offer the way back. */
export function settingsPath(section: SectionId, returnTo?: string): string {
  return returnTo ? `/settings/${section}?return=${encodeURIComponent(returnTo)}` : `/settings/${section}`;
}

/** Only paths inside this app are followed back. */
export function safeReturn(value: string | null): string | null {
  return value && value.startsWith("/") && !value.startsWith("//") ? value : null;
}
