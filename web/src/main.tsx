import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { registerServiceWorker } from "./lib/push";
import { applyTheme, currentTheme } from "./theme";
import "./styles/base.css";
import "./styles/ui.css";
import "./styles/chat.css";
import "./styles/panels.css";
import "./styles/memory.css";
import "./styles/board.css";
import "./styles/plan.css";
import "./styles/desk.css";
import "./styles/founder.css";
import "./styles/shell.css";
import "./styles/home.css";
import "./styles/overview.css";
import "./styles/squad.css";
import "./styles/deliverables.css";
import "./styles/settings.css";
import "./styles/connections.css";
import "./styles/onboarding.css";

applyTheme(currentTheme());
registerServiceWorker();

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
