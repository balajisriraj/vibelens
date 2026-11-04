// Pass 1 of the promo: run the real VibeLens (the API with the scripted model, and the Vite UI), drive it like a
// viewer would on the bundled sample talk, and save DOM snapshots of each moment to promo/out/snaps. Pass 2
// (kit/render.mjs) films them.
//
//   cd promo && pnpm install && node capture.mjs
import { rmSync } from "node:fs";
import { resolve } from "node:path";
import { film, freePort, launch, serve, sleep, snapper, until } from "./kit/snap.mjs";

const ROOT = resolve(import.meta.dirname, "..");
const SNAPS = resolve(import.meta.dirname, "out/snaps");
rmSync(SNAPS, { recursive: true, force: true });
const data = resolve(import.meta.dirname, "out/data");
rmSync(data, { recursive: true, force: true });

const api = await freePort();
const web = await freePort();
const stopApi = await serve("uv", ["run", "vibelens", "serve", "--host", "127.0.0.1", "--port", String(api)], {
  cwd: resolve(ROOT, "backend"),
  // Offline: the scripted model, and the embedding model from the local cache only.
  env: { VIBELENS_LLM: "scripted", VIBELENS_SCRIPTED_DELAY: "0.08", VIBELENS_DATA_DIR: data, HF_HUB_OFFLINE: "1" },
  url: `http://127.0.0.1:${api}/api/health`,
});
const stopWeb = await serve("pnpm", ["exec", "vite", "--host", "127.0.0.1", "--port", String(web), "--strictPort"], {
  cwd: resolve(ROOT, "frontend"),
  env: { VIBELENS_API: `http://127.0.0.1:${api}` },
  url: `http://127.0.0.1:${web}/`,
});

const { browser, page } = await launch();
await page.goto(`http://127.0.0.1:${web}/`);
await until(page, () => document.querySelector(".hero .btn.yellow"));
await sleep(500);
const raw = snapper(page, SNAPS);

// A snapshot can't play a <video>, so paint its current frame into an <img> in its place, snapshot, then put the
// player back.
// The page scrolls itself (the chat and transcript follow along), so hold the window still once the watch page is up:
// frames of one shot then line up.
let hold = null;
const shot = async (name) => {
  if (hold !== null) await page.evaluate((y) => window.scrollTo(0, y), hold);
  await page.evaluate(async () => {
    const wait = (v, ev) => new Promise((ok) => (v.addEventListener(ev, ok, { once: true }), setTimeout(ok, 4000)));
    for (const v of document.querySelectorAll("video")) {
      v.pause();
      if (v.readyState < 2) {
        v.currentTime = Math.max(0.05, v.currentTime);
        await wait(v, "seeked");
      }
      if (v.seeking) await wait(v, "seeked");
      const c = document.createElement("canvas");
      c.width = v.videoWidth;
      c.height = v.videoHeight;
      c.getContext("2d").drawImage(v, 0, 0);
      const img = document.createElement("img");
      img.src = c.toDataURL("image/jpeg", 0.92);
      img.className = "snap-frame";
      img.style.cssText = "position:absolute;inset:0;width:100%;height:100%;object-fit:cover";
      v.style.display = "none";
      v.after(img);
    }
  });
  await raw(name);
  await page.evaluate(() => {
    document.querySelectorAll(".snap-frame").forEach((n) => n.remove());
    document.querySelectorAll("video").forEach((v) => (v.style.display = ""));
  });
};
/** Seek through the UI the way a viewer would (a click), then hold the frame still. */
const clickSeek = async (sel) => {
  await page.click(sel);
  await sleep(500);
  await page.evaluate(() => document.querySelector("video")?.pause());
  await sleep(300);
};
const tab = async (n) => {
  await page.click(`.tabs button:nth-child(${n})`);
  await sleep(400);
};

// Home, then the sample talk, processed live.
await shot("home");
await page.click(".hero .btn.yellow");
await until(page, () => document.querySelector(".rail"));
const n = await film(page, shot, "build", () => !!document.querySelector(".watch-head"), { every: 250, max: 60 });
await until(page, () => document.querySelector("video")?.readyState >= 1);
await sleep(800);
await shot("build-done");
console.log(`build: ${n} frames`);
await shot("watch");

// Moments: a pin on the timeline seeks to where its quote is said.
await clickSeek(".tl-pins .pin:nth-child(2)");
await shot("pin");

// Chapters: click one, the player follows.
await tab(2);
await shot("chapters");
await clickSeek(".chapters li:nth-child(4) button");
await shot("chapter-seek");

// Transcript: live-synced, and searchable.
await tab(3);
await sleep(900);
hold = 0;
await page.evaluate(() => {
  window.scrollTo(0, 0);
  // Bring the playing line into the visible half of the panel.
  const line = document.querySelector(".line.on");
  const panel = line.closest(".panel");
  panel.scrollTop = line.getBoundingClientRect().top - panel.getBoundingClientRect().top + panel.scrollTop - 220;
});
await shot("transcript");
await page.click(".find");
await page.keyboard.type("week", { delay: 30 });
await sleep(400);
await shot("find");
await page.click(".find", { clickCount: 3 });
await page.keyboard.press("Backspace");

// Ask it: back to the top of the talk, then a question; the agent searches, answers, and the stamp seeks.
await clickSeek(".tl-pins .pin:nth-child(1)");
await tab(4);
await sleep(400);
await shot("ask-empty");
async function ask(prefix, question, settled) {
  await page.click(".chat input");
  await page.keyboard.type(question, { delay: 8 });
  await page.keyboard.press("Enter");
  await sleep(100);
  const frames = await film(page, shot, prefix, settled, { every: 250, max: 60 });
  await sleep(700);
  await shot(`${prefix}-done`);
  console.log(`${prefix}: ${frames} frames`);
}
await ask("ask", "What should you do in the first two weeks?", () => {
  const a = [...document.querySelectorAll(".a p")].pop();
  return !!a && /\.\s*$/.test(a.textContent) && !a.classList.contains("wait") && !!document.querySelector(".chat form input:not(:disabled)");
});
await clickSeek(".a .stamp");
await shot("ask-seek");

// An off-topic question cites nothing.
await ask("offtopic", "What is the recipe for a good lasagne?", () => {
  const a = [...document.querySelectorAll(".a p")].pop();
  return !!a && a.textContent.includes("chapters.");
});

// Back home: the tape is in the library.
hold = null;
await page.click(".back");
await until(page, () => document.querySelector(".library .tape"));
await page.evaluate(() => window.scrollTo(0, 330));
await sleep(500);
await shot("library");

await browser.close();
stopWeb();
stopApi();
console.log(`${raw.names.length} snapshots in promo/out/snaps`);
process.exit(0);
