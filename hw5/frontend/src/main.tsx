import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Fonts are bundled from npm, so the dashboard works offline.
import "@fontsource/courier-prime/400.css";
import "@fontsource/courier-prime/700.css";
import "@fontsource/courier-prime/400-italic.css";
import "@fontsource/special-elite/400.css";
import "./styles.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
