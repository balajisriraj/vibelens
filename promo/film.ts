// VibeLens's promo: the problem, the product, then each feature given room on the real UI (DOM snapshots from
// capture.mjs, the sample talk on the scripted model), and what's under the hood. 112 bpm; shots are counted in beats.
// The look is the app's own: neo-brutalist, hard borders, hard shadows, electric blue and acid yellow.
import { big, chips, eyebrow, grad, makeFilm, stream, sub } from "./kit/film";

const INK = "#111";
const BLUE = "#2f3cff";
const YELLOW = "#e4ff3a";
const PAPER = "#f7f7f2";
const PINK = "#ff5fa2";
const logo = `<div style="width:176px;height:150px;margin:0 auto;background:${BLUE};border:9px solid ${INK};box-shadow:14px 14px 0 ${INK};display:grid;place-items:center;color:#fff;font:64px/1 'Arial Black',sans-serif;transform:rotate(-2deg)">▶</div>`;
const { word, ui, run, BEAT } = makeFilm({
  name: "vibelens",
  style: "punch",
  bpm: 112,
  bgs: { dark: [INK, PAPER], light: [PAPER, INK], yellow: [YELLOW, INK], blue: [BLUE, "#fff"], pink: [PINK, INK] },
  // Solid blue: the caption eyebrow is clipped from it. Type-card .grad is restyled below as the app's highlighter mark.
  grad: `linear-gradient(90deg, ${BLUE}, ${BLUE})`,
  font: `"Helvetica Neue", Helvetica, Arial, sans-serif`,
  stage: `radial-gradient(${INK} 2px, transparent 2.5px) 0 0 / 34px 34px, ${BLUE}`,
  caption: { bg: "#fff", ink: INK, shadow: `0 0 0 4px ${INK}, 9px 9px 0 4px ${INK}` },
  logo,
  css: `
    #type { box-shadow: inset 0 0 0 22px ${INK}; }
    #type[data-bg=dark] { box-shadow: inset 0 0 0 22px ${YELLOW}; }
    #type .w { font-family: "Arial Black", "Helvetica Neue", sans-serif; font-weight: 900; letter-spacing: -.03em; }
    #type .w.s { font-size: 92px; letter-spacing: -.025em; line-height: 1.06; }
    #type .sub { opacity: .85; font-weight: 600; }
    #type .eyebrow { justify-self: center; opacity: 1; padding: 10px 20px; background: ${INK}; color: ${YELLOW}; font-family: Menlo, monospace; letter-spacing: .12em; border: 4px solid ${INK}; box-shadow: 7px 7px 0 ${YELLOW}; }
    #type[data-bg=dark] .eyebrow { background: ${YELLOW}; color: ${INK}; box-shadow: 7px 7px 0 ${BLUE}; }
    #type .grad { display: inline-block; padding: .02em .16em .08em; margin-top: .08em; background: ${YELLOW}; color: ${INK}; -webkit-text-fill-color: ${INK}; border: 7px solid ${INK}; box-shadow: 14px 14px 0 ${INK}; transform: rotate(-1.4deg); }
    #type[data-bg=yellow] .grad { background: #fff; }
    #type[data-bg=dark] .grad { box-shadow: 14px 14px 0 ${BLUE}; }
    #type .chips span { border-radius: 0; border: 4px solid currentColor; box-shadow: 6px 6px 0 currentColor; opacity: 1; font-family: Menlo, monospace; font-size: 27px; background: #fff; }
    #caption { border-radius: 0; padding: 14px 30px 16px; }
    #caption .eyebrow { font-family: Menlo, monospace; letter-spacing: .14em; }
    #camera.window { border-radius: 0; box-shadow: 0 0 0 6px ${INK}, 26px 26px 0 6px ${INK}; }
    #ring { border-radius: 0; box-shadow: 0 0 0 5px ${PINK}, 9px 9px 0 5px ${INK}; }
    #ripple { background: ${YELLOW}; box-shadow: 0 0 0 3px ${INK}; }
  `,
});
const C = { x: 960, y: 540 };

// The hook: what's broken.
word(4, big("An hour-long video.", "m"), "light");
word(5, big("The one answer you need is in there somewhere.", "s"), "yellow");
word(5, `${big("So you scrub. And skim. And scrub.", "s")}${sub("Hunting for the minute that matters.")}`, "dark");
word(5, big(`What if you could just ${grad("ask it?")}`, "s"), "blue");
// The product.
word(7, `${logo}${big("VibeLens")}${sub("Paste a video. Get the chapters, the moments that matter, and a chat that jumps to the exact second.")}`, "yellow", { mark: "reveal", hit: true });
ui(7, { snap: "home", cam: [0.7, C, 0.78, C] });

// 1. In.
word(5, `${eyebrow("01 · Bring a video")}${big("Any talk, any source.", "s")}${sub("A YouTube link, your own video or audio, or a caption file.")}`, "light");
ui(9, {
  snap: "home",
  cam: [1.15, { x: 900, y: 540 }, 1.35, { x: 860, y: 560 }],
  ring: [{ sel: ".hero .paste", from: 0.5, to: 2.1 }, { sel: ".hero .alts .btn:first-child", from: 2.1, to: 3.5 }],
  cursor: { path: [[0, { x: 1300, y: 900 }], [3.4, ".hero .btn.yellow"], [4.8, ".hero .btn.yellow"]], click: [3.9] },
  caption: ["Three ways in", "A link, your own file, or captions"],
});
const build: [number, string][] = Array.from({ length: 11 }, (_, i) => [i * 0.3, `build-${String(i).padStart(2, "0")}`]);
ui(8, { snap: build, cam: [1.5, { x: 700, y: 330 }, 1.6, { x: 700, y: 360 }], caption: ["Watched for you", "Transcript, search index, chapters"] });

// 2. Chapters and moments.
word(5, `${eyebrow("02 · Summarise")}${big("The whole talk, at a glance.", "s")}${sub("Chapters on a timeline, and the moments worth jumping to.")}`, "light");
ui(8, { snap: "build-done", cam: [1.3, { x: 820, y: 360 }, 1.6, ".watch-head"], ring: [{ sel: ".vibe", from: 2.2 }], caption: ["The vibe check", "Format, tone, energy and audience"] });
ui(9, {
  snap: [[0, "watch"], [3.1, "pin"]],
  cam: [1.45, { x: 960, y: 700 }, 1.5, { x: 960, y: 720 }],
  cursor: { path: [[0, { x: 900, y: 650 }], [2.4, ".tl-pins .pin:nth-child(2)"], [4.4, ".tl-pins .pin:nth-child(2)"]], click: [2.8] },
  ring: [{ sel: ".moment:nth-child(2)", from: 3.2 }],
  caption: ["Key moments", "Pinned to the second the quote is said"],
});
ui(7, { snap: "pin", cam: [1.9, ".moment:nth-child(2)", 2.15, ".moment:nth-child(2)"], ring: [{ sel: ".moment:nth-child(2) .check", from: 1.4 }], caption: ["Verified quotes", "Each one found in the transcript"] });
ui(9, {
  snap: [[0, "chapters"], [3.0, "chapter-seek"]],
  cam: [1.4, { x: 960, y: 640 }, 1.45, { x: 960, y: 660 }],
  cursor: { path: [[0, { x: 1500, y: 300 }], [2.3, ".chapters li:nth-child(4) button"], [4.4, ".chapters li:nth-child(4) button"]], click: [2.7] },
  caption: ["Chapters", "Click one, the player follows"],
});

// 3. Transcript.
word(5, `${eyebrow("03 · Read")}${big("Every word, in sync.", "s")}${sub("The transcript follows the player. Find any line in a keystroke.")}`, "light");
ui(9, {
  snap: [[0, "transcript"], [3.0, "find"]],
  type: { sel: ".find", text: "week", from: 1.2, to: 2.4, until: 3.0 },
  cam: [1.5, { x: 960, y: 690 }, 1.75, { x: 1330, y: 690 }],
  ring: [{ sel: ".line.on", from: 0.4, to: 1.2 }],
  caption: ["Transcript", "Live-synced and searchable"],
});

// 4. The hero: ask it, and it cites the second.
word(4, big("Most AI answers just tell you.", "s"), "dark", { mark: "heroIn" });
word(4, big("Then you go find it yourself.", "s"), "light");
word(6, `${eyebrow("04 · Ask it")}${big(grad("Answers that cite the second."), "s")}${sub("An agent searches the tape before it answers. Every timestamp is a button.")}`, "blue", { mark: "hero", hit: true });
const Q = "What should you do in the first two weeks?";
ui(14, {
  snap: [[0, "ask-empty"], ...stream("ask", 3.6, 0.28)],
  type: { sel: ".chat input", text: Q, from: 0.6, to: 2.8, until: 3.6 },
  cursor: { path: [[0, { x: 1300, y: 950 }], [2.9, ".chat form button"], [3.6, ".chat form button"], [4.6, { x: 1500, y: 980 }]], click: [3.2] },
  cam: [1.9, { x: 1335, y: 700 }, 1.95, { x: 1335, y: 640 }],
  ring: [{ sel: ".a .tool", from: 4.6, to: 6.0 }],
  caption: ["Ask it", "It searches the tape first"],
});
ui(8, { snap: "ask-done", cam: [2.2, ".a", 2.45, ".a"], ring: [{ sel: ".a .stamp", from: 1.2 }], caption: ["Cited to the second", "Checked against what it read"] });
ui(9, {
  snap: [[0, "ask-done"], [2.6, "ask-seek"]],
  cam: [1.3, { x: 960, y: 560 }, 1.35, { x: 960, y: 580 }],
  cursor: { path: [[0, { x: 1300, y: 600 }], [1.9, ".a .stamp"], [4.2, ".a .stamp"]], click: [2.3] },
  ring: [{ sel: ".tl-head", from: 2.8 }],
  caption: ["Tap the stamp", "The player jumps right there"],
});
ui(8, { snap: stream("offtopic", 0, 0.3), cam: [1.85, { x: 1335, y: 700 }, 2.0, ".log > .a:nth-last-child(2)"], caption: ["Honest by design", "Not in the video? It says so"] }, { mark: "heroEnd" });

// The angles: how it's built, where your files go, and who it's for.
word(8, `${eyebrow("Under the hood")}${big("A pipeline, plus an agent.", "s")}${chips("Claude tool use", "faster-whisper", "sqlite-vec + FTS5", "Rank fusion", "SSE streaming", "FastAPI", "React")}`, "light");
word(6, `${big("Your uploads stay yours.", "s")}${sub("Speech recognition runs locally, on your own machine.")}`, "dark");
word(7, `${big("For anyone who learns from video.", "s")}${sub("And for engineers, a reference build of an agent that cites its sources.")}`, "yellow");
word(8, `${logo}${big(grad("VibeLens"))}${sub("Watch less. Know more. · by Balaji Sri Raj")}`, "blue", { mark: "outro" });

run((m) => ({ teaser: [m.reveal, m.reveal + 43 * BEAT], poster: [m.hero + 4 * BEAT, 0] }));
