import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import TrayPopover from "./TrayPopover";
import "./styles.css";

const params = new URLSearchParams(window.location.search);
const view = params.get("view");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {view === "tray" ? <TrayPopover /> : <App />}
  </React.StrictMode>,
);
