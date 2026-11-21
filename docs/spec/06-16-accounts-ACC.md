### 6.16 Accounts and access (ACC)

- **ACC-1 Passwords.** At least 12 characters, hashed with a memory-hard function. Unknown, deactivated and wrong-password logins get the same answer and take the same time. Ten failures lock that address for 15 minutes.
- **ACC-2 Browser sessions** last at most 14 days and expire after 3 idle days. Signing out or changing the password ends them server-side.
- **ACC-3 Personal tokens** are named and expire after 1–365 days (default 30). Tokens that never expire are not offered. All tokens are stored only as hashes.
- **ACC-4 Invites and password resets** are single-use links valid for 72 hours.
- **ACC-5 Project membership.** Exactly one chairman, and any number of co-chairs and observers. Removal takes effect on the member's next request.
- **ACC-6 Secrets** are encrypted under an install master key. The server refuses to store or read secrets without that key. Rotating the key re-encrypts everything atomically: if one value fails, nothing changes.
- **ACC-7 Second factor** (SHOULD for v2.0): TOTP. Single sign-on is a later release. Until a factor ships, SECURITY.md states the gap plainly.
