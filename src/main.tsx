import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import TrayPopover from "./TrayPopover";
import Clothesline from "./Clothesline";
import Library from "./Library";
import Settings from "./Settings";
import "./styles.css";

const params = new URLSearchParams(window.location.search);
const view = params.get("view");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {view === "tray" ? (
      <TrayPopover />
    ) : view === "line" ? (
      <Clothesline />
    ) : view === "library" ? (
      <Library />
    ) : view === "settings" ? (
      <Settings />
    ) : (
      <App />
    )}
  </React.StrictMode>,
);
