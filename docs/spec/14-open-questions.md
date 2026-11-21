## 14. Open questions for the owner

These are decisions this revision could not settle alone. Each has a recommendation; the spec as written follows the recommendation until the owner rules.

- **Rebuild or fix?** Recommendation: rebuild. The ideas are sound, but the defects are structural (no service layer, surfaces wired by hand, overlapping concepts, string-typed state). Fixing them means touching nearly every file.
- **Tokens are not equal across models.** A frontier token and a fast token count the same against the budget. Recommendation: accept this for simplicity. The quality dial is the lever, and the budget advice (GOV-4) accounts for the dial.
- **Desktop install in v2.0?** Recommendation: slim mode (NFR-23) ships in v2.0 using containers; host-jail mode for machines without Docker follows in phase 8.
- **Which harnesses ship first?** Recommendation: the vendor-neutral loop plus one vendor agent SDK, both through the gateway. Add CLI-based harnesses as plug-ins.
- **Egress control.** Recommendation: open egress in v2.0, with per-project networks (required, EXE-12) and honest documentation; revisit a logged egress policy after v2.0.
- **Second factor and SSO.** Recommendation: TOTP in v2.0; SSO later.
- **Guests in Slack.** Messages from unlinked Slack users in a project channel never reach agents. Recommendation: keep this, and show them to people only.
- **Workspace snapshots.** Snapshotting every workspace file as an artifact (ART-2) has a storage cost on large repositories. Recommendation: content-addressed storage with the retention in NFR-15. Revisit if repositories over 1 GB are common.

* **Mail servers beyond Stalwart.** Recommendation: ship the Stalwart adapter first, keep the adapter interface small, and add other servers as plug-ins when there is demand. Pin the Stalwart version the adapter is tested against, because its management API changed in 0.16.

- **Default skill sources.** Recommendation: trust no outside skill source by default. Ship crewmind's own skills (LIB-6) and let the admin add sources, with every new skill reviewed before use.
