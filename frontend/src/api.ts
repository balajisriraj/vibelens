export type Cue = { start: number; end: number; text: string };
export type Chapter = { start: number; end: number; title: string; summary: string };
export type Moment = { start: number; title: string; why: string; quote: string; verified: boolean };
export type Summary = {
  title: string;
  tldr: string;
  vibe: { tone: string; energy: "low" | "medium" | "high"; audience: string; format: string };
  chapters: Chapter[];
  moments: Moment[];
  topics: string[];
  questions: string[];
};
export type Video = {
  id: string;
  title: string;
  kind: "youtube" | "upload" | "captions" | "sample";
  ref: string;
  duration: number | null;
  status: "processing" | "ready" | "failed";
  error: string | null;
  cues: Cue[];
  summary: Summary | null;
  created_at: string;
};
export type VideoSummary = Omit<Video, "cues" | "summary" | "error">;

export type BuildEvent =
  | { type: "step"; step: "transcript" | "index" | "summary"; status: "running" | "done"; detail?: string; ms?: number; title?: string; duration?: number }
  | { type: "done"; summary: Summary }
  | { type: "error"; message: string };

export type Citation = { stamp: string; t: number; verified: boolean };
export type ChatEvent =
  | { type: "text"; text: string }
  | { type: "tool"; name: string; input: Record<string, string>; result: string }
  | { type: "done"; citations: Citation[]; ms: number }
  | { type: "error"; message: string };

export const fmt = (s: number) => {
  const t = Math.max(0, Math.round(s));
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), sec = t % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}` : `${m}:${String(sec).padStart(2, "0")}`;
};

export const parseStamp = (s: string) => s.split(":").reduce((acc, p) => acc * 60 + Number(p), 0);

/** Split an SSE stream into parsed `data:` payloads; returns the unconsumed remainder. */
export function parseSSE<T>(buffer: string, emit: (event: T) => void): string {
  const frames = buffer.split(/\r?\n\r?\n/);
  const rest = frames.pop() ?? "";
  for (const frame of frames) {
    const data = frame
      .split(/\r?\n/)
      .filter((l) => l.startsWith("data:"))
      .map((l) => l.slice(5).trimStart())
      .join("\n");
    if (data) emit(JSON.parse(data) as T);
  }
  return rest;
}

async function errorText(res: Response) {
  try {
    const body = await res.json();
    return typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`;
  } catch {
    return `Request failed (${res.status})`;
  }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(await errorText(res));
  return (await res.json()) as T;
}

async function stream<T>(res: Response, onEvent: (e: T) => void) {
  if (!res.ok || !res.body) throw new Error(await errorText(res));
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer = parseSSE(buffer + value, onEvent);
  }
  parseSSE(buffer + "\n\n", onEvent);
}

const post = (url: string, body?: unknown, signal?: AbortSignal) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined, signal });

export const api = {
  list: () => fetch("/api/videos").then(json<VideoSummary[]>),
  get: (id: string) => fetch(`/api/videos/${id}`).then(json<Video>),
  remove: (id: string) => fetch(`/api/videos/${id}`, { method: "DELETE" }).then(json<{ deleted: boolean }>),
  youtube: (url: string) => post("/api/videos/youtube", { url }).then(json<{ id: string }>),
  sample: () => post("/api/videos/sample").then(json<{ id: string }>),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch("/api/videos/upload", { method: "POST", body: form }).then(json<{ id: string }>);
  },
  events: (id: string, onEvent: (e: BuildEvent) => void, signal: AbortSignal) =>
    fetch(`/api/videos/${id}/events`, { signal }).then((res) => stream(res, onEvent)),
  ask: (id: string, body: { question: string; history: { role: string; content: string }[] }, onEvent: (e: ChatEvent) => void, signal: AbortSignal) =>
    post(`/api/videos/${id}/ask`, body, signal).then((res) => stream(res, onEvent)),
};
