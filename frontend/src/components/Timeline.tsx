import { useRef, useState } from "react";
import { type Chapter, fmt, type Moment } from "../api";

const COLORS = ["#2f3cff", "#ff5fa2", "#00c48c", "#ff8a00", "#8b5cf6", "#00b8d9"];

/** The scrubber: chapters as coloured blocks, key moments as pins, a playhead, click anywhere to seek. */
export function Timeline({
  duration,
  chapters,
  moments,
  time,
  onSeek,
}: {
  duration: number;
  chapters: Chapter[];
  moments: Moment[];
  time: number;
  onSeek: (t: number) => void;
}) {
  const bar = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const pct = (t: number) => `${Math.min(100, Math.max(0, (t / (duration || 1)) * 100))}%`;
  const at = (clientX: number) => {
    const r = bar.current!.getBoundingClientRect();
    return Math.min(duration, Math.max(0, ((clientX - r.left) / r.width) * duration));
  };
  const chapterAt = (t: number) => chapters.findLast((c) => c.start <= t);
  const current = chapterAt(time);

  return (
    <div className="timeline">
      <div className="tl-head">
        <span className="now">{fmt(time)}</span>
        <b>{current?.title ?? " "}</b>
        <span className="len">{fmt(duration)}</span>
      </div>
      <div
        ref={bar}
        className="tl-bar"
        role="slider"
        aria-label="Seek"
        aria-valuemin={0}
        aria-valuemax={Math.round(duration)}
        aria-valuenow={Math.round(time)}
        aria-valuetext={fmt(time)}
        tabIndex={0}
        onClick={(e) => onSeek(at(e.clientX))}
        onMouseMove={(e) => setHover(at(e.clientX))}
        onMouseLeave={() => setHover(null)}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") onSeek(Math.min(duration, time + 5));
          if (e.key === "ArrowLeft") onSeek(Math.max(0, time - 5));
        }}
      >
        {chapters.map((c, i) => (
          <span
            key={c.start}
            className={`tl-chapter ${current === c ? "on" : ""}`}
            style={{ left: pct(c.start), width: `calc(${pct(c.end - c.start)} - 3px)`, background: COLORS[i % COLORS.length] }}
          >
            <i>{c.title}</i>
          </span>
        ))}
        <span className="tl-played" style={{ width: pct(time) }} />
        <span className="tl-head-mark" style={{ left: pct(time) }} />
        {hover !== null && (
          <span className="tl-hover" style={{ left: pct(hover) }}>
            {fmt(hover)} · {chapterAt(hover)?.title}
          </span>
        )}
      </div>
      <div className="tl-pins">
        {moments.map((m, i) => (
          <button key={i} className="pin" style={{ left: pct(m.start) }} onClick={() => onSeek(m.start)} title={`${fmt(m.start)} ${m.title}`}>
            {i + 1}
          </button>
        ))}
      </div>
    </div>
  );
}
