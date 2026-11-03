import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type BuildEvent, fmt, type Video } from "./api";
import { Chat } from "./components/Chat";
import { Player, type PlayerHandle } from "./components/Player";
import { Timeline } from "./components/Timeline";
import { navigate } from "./router";

type Tab = "moments" | "chapters" | "transcript" | "ask";
type Step = { step: string; status: string; detail?: string; ms?: number };
const STEPS = [
  ["transcript", "Transcript"],
  ["index", "Search index"],
  ["summary", "Chapters + moments"],
] as const;

export function VideoView({ id }: { id: string }) {
  const [video, setVideo] = useState<Video | null>(null);
  const [missing, setMissing] = useState(false);
  const [steps, setSteps] = useState<Record<string, Step>>({});
  const [time, setTime] = useState(0);
  const [tab, setTab] = useState<Tab>("moments");
  const [filter, setFilter] = useState("");
  const player = useRef<PlayerHandle>(null);
  const activeLine = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    const onEvent = (e: BuildEvent) => {
      if (e.type === "step") setSteps((s) => ({ ...s, [e.step]: e }));
      if (e.type === "done" || e.type === "error") api.get(id).then(setVideo);
    };
    api
      .get(id)
      .then((v) => {
        setVideo(v);
        if (v.status === "processing") api.events(id, onEvent, ctrl.signal).catch(() => {});
      })
      .catch(() => setMissing(true));
    return () => ctrl.abort();
  }, [id]);

  const seek = useCallback((t: number) => {
    if (player.current) player.current.seek(t);
    else setTime(t);
  }, []);
  const onTime = useCallback((t: number) => setTime(t), []);

  const cues = video?.cues ?? [];
  const active = useMemo(() => cues.findLastIndex((c) => c.start <= time + 0.25), [cues, time]);
  useEffect(() => {
    if (tab === "transcript" && !filter) activeLine.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [active, tab, filter]);

  if (missing)
    return (
      <main className="page center">
        <h1 className="huge">Not found.</h1>
        <button className="btn" onClick={() => navigate("/")}>
          Back home
        </button>
      </main>
    );
  if (!video) return <main className="page center">Loading…</main>;

  if (video.status !== "ready" || !video.summary) {
    return (
      <main className="page processing">
        <button className="back" onClick={() => navigate("/")}>
          ← All videos
        </button>
        <h1>{video.status === "failed" ? "That didn't work." : "Watching it for you…"}</h1>
        {video.status === "failed" ? (
          <p className="error">{video.error}</p>
        ) : (
          <ol className="rail">
            {STEPS.map(([key, label], i) => {
              const s = steps[key];
              return (
                <li key={key} className={s?.status ?? "todo"}>
                  <span className="n">{s?.status === "done" ? "✓" : i + 1}</span>
                  <div>
                    <b>{label}</b>
                    <span>{s?.status === "done" ? `${s.detail} · ${s.ms} ms` : s ? "working…" : "waiting"}</span>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </main>
    );
  }

  const s = video.summary;
  const duration = video.duration ?? cues[cues.length - 1]?.end ?? 0;
  const shown = filter ? cues.map((c, i) => [c, i] as const).filter(([c]) => c.text.toLowerCase().includes(filter.toLowerCase())) : cues.map((c, i) => [c, i] as const);

  return (
    <main className="page watch">
      <button className="back" onClick={() => navigate("/")}>
        ← All videos
      </button>
      <header className="watch-head">
        <h1>{s.title}</h1>
        <p className="tldr">{s.tldr}</p>
        <div className="vibe">
          <span className="chip yellow">{s.vibe.format}</span>
          <span className="chip">{s.vibe.tone}</span>
          <span className="chip energy" data-level={s.vibe.energy}>
            energy <i />
            <i />
            <i />
          </span>
          <span className="chip">for {s.vibe.audience}</span>
          {s.topics.map((t) => (
            <span key={t} className="tag">
              #{t}
            </span>
          ))}
        </div>
      </header>

      <div className="stage">
        <section className="left">
          <Player ref={video.kind === "captions" ? undefined : player} video={video} onTime={onTime} />
          <Timeline duration={duration} chapters={s.chapters} moments={s.moments} time={time} onSeek={seek} />
        </section>

        <section className="right">
          <nav className="tabs" role="tablist">
            {(["moments", "chapters", "transcript", "ask"] as Tab[]).map((t) => (
              <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
                {t === "ask" ? "Ask it" : t}
              </button>
            ))}
          </nav>

          <div className="panel" hidden={tab !== "moments"}>
            {s.moments.map((m, i) => (
              <article key={i} className="moment">
                <button className="t" onClick={() => seek(m.start)}>
                  <span>{i + 1}</span>▶ {fmt(m.start)}
                </button>
                <h3>{m.title}</h3>
                <blockquote>“{m.quote}”</blockquote>
                <p>{m.why}</p>
                <span className={`check ${m.verified ? "" : "no"}`}>{m.verified ? "quote found at this second" : "quote not found in transcript"}</span>
              </article>
            ))}
          </div>

          <div className="panel" hidden={tab !== "chapters"}>
            <ol className="chapters">
              {s.chapters.map((c) => (
                <li key={c.start} className={time >= c.start && time < c.end ? "on" : ""}>
                  <button onClick={() => seek(c.start)}>
                    <span className="t">{fmt(c.start)}</span>
                    <b>{c.title}</b>
                    <span className="sum">{c.summary}</span>
                  </button>
                </li>
              ))}
            </ol>
          </div>

          <div className="panel transcript" hidden={tab !== "transcript"}>
            <input className="find" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={`Find in ${cues.length} lines…`} />
            {shown.map(([c, i]) => (
              <button key={i} ref={i === active ? activeLine : undefined} className={`line ${i === active ? "on" : ""}`} onClick={() => seek(c.start)}>
                <span className="t">{fmt(c.start)}</span>
                {c.text}
              </button>
            ))}
          </div>

          <div className="panel" hidden={tab !== "ask"}>
            <Chat videoId={video.id} questions={s.questions} onSeek={seek} />
          </div>
        </section>
      </div>
    </main>
  );
}
