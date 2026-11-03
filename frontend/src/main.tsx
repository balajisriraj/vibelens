import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Home } from "./Home";
import { navigate, usePath } from "./router";
import "./styles.css";
import { VideoView } from "./VideoView";

function App() {
  const path = usePath();
  const video = path.match(/^\/v\/([a-f0-9]+)$/);
  return (
    <>
      <header className="top">
        <button className="logo" onClick={() => navigate("/")}>
          <span className="mark">▶</span>VibeLens
        </button>
        <span className="beta">watch less · know more</span>
      </header>
      {video ? <VideoView key={video[1]} id={video[1]} /> : <Home />}
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
