import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

export default function globalTeardown(): void {
  execFileSync(join(here, "stop-backend.sh"), [join(here, ".run")], { stdio: "inherit" });
}
