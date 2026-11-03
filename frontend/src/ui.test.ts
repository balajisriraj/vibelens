import { describe, expect, it } from "vitest";
import { fmt, parseSSE, parseStamp } from "./api";
import { fold, type Turn } from "./components/Chat";

describe("timestamps", () => {
  it("formats and parses", () => {
    expect(fmt(0)).toBe("0:00");
    expect(fmt(185.4)).toBe("3:05");
    expect(fmt(3723)).toBe("1:02:03");
    expect(parseStamp("1:02:03")).toBe(3723);
    expect(parseStamp("3:05")).toBe(185);
  });
});

describe("sse", () => {
  it("keeps partial frames for the next chunk", () => {
    const got: unknown[] = [];
    const rest = parseSSE('data: {"type":"text","text":"a"}\n\ndata: {"ty', (e) => got.push(e));
    expect(got).toEqual([{ type: "text", text: "a" }]);
    expect(rest).toBe('data: {"ty');
  });
});

describe("chat fold", () => {
  it("collects tool calls, text and citations", () => {
    let t: Turn = { role: "assistant", text: "", tools: [], citations: [], streaming: true };
    t = fold(t, { type: "tool", name: "search_transcript", input: { query: "trust" }, result: "1:08" });
    t = fold(t, { type: "text", text: "At [1:08] " });
    t = fold(t, { type: "text", text: "it says so." });
    t = fold(t, { type: "done", citations: [{ stamp: "1:08", t: 68, verified: true }], ms: 10 });
    expect(t.tools).toHaveLength(1);
    expect(t.text).toBe("At [1:08] it says so.");
    expect(t.citations[0].verified).toBe(true);
    expect(t.streaming).toBe(false);
  });
});
