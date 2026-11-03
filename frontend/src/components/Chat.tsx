import { Fragment, useEffect, useRef, useState } from "react";
import { api, type ChatEvent, type Citation, parseStamp } from "../api";

type Tool = { name: string; input: Record<string, string>; result: string };
export type Turn = { role: "user" | "assistant"; text: string; tools: Tool[]; citations: Citation[]; streaming?: boolean; error?: boolean };

const TOOL_LABEL: Record<string, string> = { search_transcript: "Searched", read_transcript: "Read", list_chapters: "Checked chapters" };

/** Fold one chat event into the answer being streamed. */
export function fold(turn: Turn, e: ChatEvent): Turn {
  switch (e.type) {
    case "text":
      return { ...turn, text: turn.text + e.text };
    case "tool":
      return { ...turn, tools: [...turn.tools, { name: e.name, input: e.input, result: e.result }] };
    case "done":
      return { ...turn, citations: e.citations, streaming: false };
    case "error":
      return { ...turn, text: e.message, error: true, streaming: false };
  }
}

function Answer({ text, citations, onSeek }: { text: string; citations: Citation[]; onSeek: (t: number) => void }) {
  const status = new Map(citations.map((c) => [c.stamp, c.verified]));
  return (
    <p>
      {text.split(/(\[\d{1,2}(?::\d{2}){1,2}\])/g).map((part, i) => {
        const m = part.match(/^\[(\d{1,2}(?::\d{2}){1,2})\]$/);
        if (!m) return <Fragment key={i}>{part}</Fragment>;
        const verified = status.get(m[1]);
        return (
          <button key={i} className={`stamp ${verified === false ? "unverified" : ""}`} onClick={() => onSeek(parseStamp(m[1]))} title={verified === false ? "Not in anything the agent read" : "Jump to this moment"}>
            ▶ {m[1]}
          </button>
        );
      })}
    </p>
  );
}

export function Chat({ videoId, questions, onSeek }: { videoId: string; questions: string[]; onSeek: (t: number) => void }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const abort = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const busy = turns.some((t) => t.streaming);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [turns]);
  useEffect(() => () => abort.current?.abort(), []);

  const ask = async (question: string) => {
    if (!question.trim() || busy) return;
    const history = turns.filter((t) => !t.error).map((t) => ({ role: t.role, content: t.text }));
    setTurns((ts) => [...ts, { role: "user", text: question, tools: [], citations: [] }, { role: "assistant", text: "", tools: [], citations: [], streaming: true }]);
    setDraft("");
    abort.current = new AbortController();
    const update = (fn: (t: Turn) => Turn) => setTurns((ts) => [...ts.slice(0, -1), fn(ts[ts.length - 1])]);
    try {
      await api.ask(videoId, { question, history }, (e) => update((t) => fold(t, e)), abort.current.signal);
    } catch (err) {
      if ((err as Error).name !== "AbortError") update((t) => ({ ...t, text: (err as Error).message, error: true }));
    } finally {
      update((t) => ({ ...t, streaming: false }));
    }
  };

  return (
    <div className="chat">
      <div className="log">
        {turns.length === 0 && (
          <div className="starters">
            <p>Ask anything. Every answer links to the second it's said.</p>
            {questions.map((q) => (
              <button key={q} onClick={() => ask(q)}>
                {q}
              </button>
            ))}
          </div>
        )}
        {turns.map((t, i) =>
          t.role === "user" ? (
            <div key={i} className="q">
              {t.text}
            </div>
          ) : (
            <div key={i} className={`a ${t.error ? "err" : ""}`}>
              {t.tools.map((tool, j) => (
                <span key={j} className="tool">
                  {TOOL_LABEL[tool.name] ?? tool.name}
                  {tool.input.query ? ` "${tool.input.query}"` : tool.input.start ? ` ${tool.input.start}-${tool.input.end}` : ""} → {tool.result}
                </span>
              ))}
              {t.text ? <Answer text={t.text} citations={t.citations} onSeek={onSeek} /> : <p className="wait">scrubbing the tape…</p>}
            </div>
          ),
        )}
        <div ref={end} />
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(draft);
        }}
      >
        <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Ask the video…" maxLength={1000} aria-label="Question" />
        <button disabled={!draft.trim() || busy}>Ask</button>
      </form>
    </div>
  );
}
