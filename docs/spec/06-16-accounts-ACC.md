### 6.16 Accounts and access (ACC)

- **ACC-1 Passwords.** At least 12 characters, hashed with a memory-hard function. Unknown, deactivated and wrong-password logins get the same answer and take the same time. Ten failures lock that address for 15 minutes.
- **ACC-2 Browser sessions** last at most 14 days and expire after 3 idle days. Signing out or changing the password ends them server-side.
- **ACC-3 Personal tokens** are named and expire after 1–365 days (default `token.default_expiry` \[30 days\]). Tokens that never expire are not offered. All tokens are stored only as hashes.
- **ACC-4 Invites and password resets** are single-use links valid for 72 hours.
- **ACC-5 Instance roles and project membership.**
  - Every person has one instance role: `admin` or `member`. Admins promote and demote. Any active person may create a project and becomes its chairman.
  - A project has exactly one chairman, and any number of co-chairs and observers. Removal takes effect on the member's next request.
  - Handing on the chair makes the previous chairman a co-chair, in the same change. An admin's emergency hand-on is recorded as break-glass (section 3).
  - Deactivating a person who chairs a project is refused, naming the projects. An admin hands each chair on first.
  - Lifecycles: section 7.8 to 7.11.
- **ACC-6 Secrets** are encrypted under an install master key. The server refuses to store or read secrets without that key. Rotating the key re-encrypts everything atomically: if one value fails, nothing changes.
- **ACC-7 Second factor** (SHOULD, after v2.0, phase 8): TOTP. Single sign-on is a later release. Until a factor ships, SECURITY.md states the gap plainly.
- **ACC-8 Your name.** A person sets the name they are shown by, and only their own; it is never empty, and the change is in the event log. A first admin is created as "Admin" until they set it.
