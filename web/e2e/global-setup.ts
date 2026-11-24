/** Builds the app and starts a real nightsquad server that serves it, for the end-to-end tests. */
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

export default function globalSetup(): void {
  const port = process.env.NIGHTSQUAD_E2E_PORT ?? "8455";
  if (process.env.NIGHTSQUAD_E2E_SKIP_BUILD !== "1") {
    execFileSync("npm", ["run", "build"], { cwd: join(here, ".."), stdio: "inherit" });
  }
  execFileSync(join(here, "start-backend.sh"), [port, join(here, ".run")], { stdio: "inherit" });
}
