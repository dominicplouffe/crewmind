import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { registerServiceWorker } from "./lib/push";
import { applyTheme, currentTheme } from "./theme";
import "./styles/base.css";
import "./styles/chat.css";
import "./styles/panels.css";
import "./styles/memory.css";
import "./styles/board.css";
import "./styles/plan.css";

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
