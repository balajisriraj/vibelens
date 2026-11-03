import { useEffect, useRef, useState } from "react";
import { api, fmt, type VideoSummary } from "./api";
import { navigate } from "./router";

export function Home() {
  const [videos, setVideos] = useState<VideoSummary[]>([]);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.list().then(setVideos).catch(() => setError("The VibeLens API isn't reachable."));
  }, []);

  const start = async (label: string, go: () => Promise<{ id: string }>) => {
    setBusy(label);
    setError(null);
    try {
      navigate(`/v/${(await go()).id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  };

  return (
    <main className="page home">
      <section className="hero">
        <h1 className="huge">
          Watch less.
          <br />
          <mark>Know more.</mark>
        </h1>
        <p className="sub">Paste a video. Get the chapters, the moments that matter, and a chat where every answer jumps to the exact second.</p>

        <form
          className="paste"
          onSubmit={(e) => {
            e.preventDefault();
            if (url.trim()) start("link", () => api.youtube(url));
          }}
        >
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=…" aria-label="YouTube link" />
          <button className="btn blue" disabled={!url.trim() || !!busy}>
            {busy === "link" ? "Reading…" : "Lens it →"}
          </button>
        </form>

        <div className="alts">
          <button className="btn" disabled={!!busy} onClick={() => file.current?.click()}>
            {busy === "upload" ? "Uploading…" : "Upload video, audio or .vtt"}
          </button>
          <input
            ref={file}
            type="file"
            hidden
            accept="video/*,audio/*,.vtt,.srt"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) start("upload", () => api.upload(f));
            }}
          />
          <button className="btn yellow" disabled={!!busy} onClick={() => start("sample", api.sample)}>
            {busy === "sample" ? "Loading…" : "▶ Try the sample talk"}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
        <ul className="how">
          <li>
            <b>01</b> Captions, or local Whisper for your own files
          </li>
          <li>
            <b>02</b> Chapters and key moments, each pinned to its quote
          </li>
          <li>
            <b>03</b> An agent that searches the tape before it answers
          </li>
        </ul>
      </section>

      {videos.length > 0 && (
        <section className="library">
          <h2>Your tapes</h2>
          <ul>
            {videos.map((v) => (
              <li key={v.id}>
                <button className="tape" onClick={() => navigate(`/v/${v.id}`)}>
                  <span className={`thumb ${v.kind}`}>
                    {v.kind === "youtube" ? <img src={`https://i.ytimg.com/vi/${v.ref}/mqdefault.jpg`} alt="" loading="lazy" /> : <span>{v.kind === "captions" ? "CC" : "▶"}</span>}
                    {v.duration ? <em>{fmt(v.duration)}</em> : null}
                  </span>
                  <b>{v.title}</b>
                  <span className={`state ${v.status}`}>{v.status}</span>
                </button>
                <button className="x" aria-label={`Delete ${v.title}`} onClick={() => api.remove(v.id).then(() => setVideos((vs) => vs.filter((x) => x.id !== v.id)))}>
                  ×
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      <footer className="foot">
        VibeLens · Claude + FastAPI + faster-whisper · part of <a href="https://balajisriraj.com/#lab">Balaji's Lab</a>
      </footer>
    </main>
  );
}
