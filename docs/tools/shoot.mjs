// Drive the real JARVIS UI in headless Chrome over CDP and save screenshots.
//   node shoot.mjs <app-url> <devtools-port> <out-dir> [scene ...]
import { writeFileSync, mkdirSync } from "node:fs";

const [APP, DT, OUT, ...ONLY] = process.argv.slice(2);
mkdirSync(OUT + "/frames", { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const targets = await (await fetch(`http://127.0.0.1:${DT}/json/list`)).json();
const page = targets.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let id = 0;
const pending = new Map();
ws.addEventListener("message", (m) => {
  const d = JSON.parse(m.data);
  if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); }
});
const send = (method, params = {}) => new Promise((res, rej) => {
  const i = ++id;
  pending.set(i, (d) => (d.error ? rej(new Error(method + ": " + d.error.message)) : res(d.result)));
  ws.send(JSON.stringify({ id: i, method, params }));
});
const js = async (expr) => {
  const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error("JS: " + (r.exceptionDetails.exception?.description || expr));
  return r.result.value;
};
const until = async (expr, ms = 180000, label = expr) => {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { if (await js(expr)) return; await sleep(500); }
  throw new Error("timeout: " + label);
};
const tidy = (closeViewer = true) => js(`document.activeElement && document.activeElement.blur(); ${closeViewer ? "document.body.classList.add('viewer-closed');" : ""} true`);
const shot = async (name) => {
  const r = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(`${OUT}/${name}.png`, Buffer.from(r.data, "base64"));
  console.log("saved", name);
};
const mode = (m) => js(`document.querySelector('.mode[data-mode="${m}"]').click(); true`);
const api = (path, body) => js(`fetch(${JSON.stringify(path)}, {method: "POST", headers: {"Content-Type": "application/json", "X-Jarvis": "1"}, body: ${JSON.stringify(JSON.stringify(body))}}).then(r => r.status)`);
const want = (s) => !ONLY.length || ONLY.includes(s);

await send("Page.enable");
await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1600, height: 1000, deviceScaleFactor: 2, mobile: false });
await send("Page.navigate", { url: APP });
await sleep(500);
await js(`localStorage.setItem("jarvis.settings", JSON.stringify({voice: true, speak: false, sound: false, motion: false, predict: false, lang: "en", mode: "ask"})); sessionStorage.clear(); true`);
await send("Page.reload");
await sleep(800);
await sleep(700);
await sleep(2600);
await js(`document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape"})); true`);
await sleep(600);

if (want("ask")) {
  await api("/api/board", { board_type: "DEMO", serial: "10000000000014", rev: "A", ticket: "DEMO-014" });
  await send("Page.reload"); await sleep(2500);
  await mode("ask");
  await js(`document.getElementById("ask-ctx").checked = true; true`);
  await js(`document.getElementById("ask-input").value = "5V reads 4.62 V at C20 and 3V3 is 3.05 V, VIN is fine. What do I check next?"; true`);
  await js(`document.getElementById("ask-form").requestSubmit(); true`);
  // frames for the GIF while it streams
  let n = 0;
  await until(`!document.getElementById("btn-stop").hidden`, 20000, "ask started");
  while (!(await js(`document.getElementById("btn-stop").hidden`)) && n < 400) {
    const r = await send("Page.captureScreenshot", { format: "png", clip: { x: 0, y: 0, width: 1600, height: 1000, scale: 0.5 } });
    writeFileSync(`${OUT}/frames/f${String(n++).padStart(4, "0")}.png`, Buffer.from(r.data, "base64"));
    await sleep(350);
  }
  await until(`document.querySelectorAll("#convo .chip").length > 0`, 30000, "chips");
  await sleep(800);
  await tidy(false);
  await shot("ask");
  await js(`document.querySelector("#convo .chip").click(); true`);
  await sleep(1800);
  await shot("ask-source");
  const r = await send("Page.captureScreenshot", { format: "png", clip: { x: 0, y: 0, width: 1600, height: 1000, scale: 0.5 } });
  for (let k = 0; k < 6; k++) writeFileSync(`${OUT}/frames/f${String(n++).padStart(4, "0")}.png`, Buffer.from(r.data, "base64"));
  console.log("frames", n);
}

if (want("board") || want("log")) {
  await api("/api/board", { board_type: "DEMO", serial: "10000000000013", rev: "A", ticket: "DEMO-013" });
  await send("Page.reload");
  await sleep(2500);
}
if (want("log")) {
  await mode("log"); await sleep(1500); await tidy();
  await js(`(() => { const h = [...document.querySelectorAll("#entries *")].find(e => e.children.length === 0 && /10000000000014/.test(e.textContent) && /DEMO/.test(e.textContent)); if (h) { h.scrollIntoView({block: "start"}); } return !!h; })()`);
  await sleep(700); await shot("log");
}
if (want("board")) { await mode("board"); await sleep(1800); await tidy(); await sleep(400); await shot("board"); }
if (want("seen")) {
  await mode("seen");
  await js(`document.getElementById("seen-input").value = "status LED never blinks"; document.getElementById("seen-form").requestSubmit(); true`);
  await until(`!!document.querySelector("#seen-out .summary") && !document.querySelector("#seen-out .working")`, 180000, "seen");
  await tidy(); await sleep(800); await shot("seen");
}
if (want("debrief")) {
  await mode("debrief");
  await js(`document.getElementById("btn-debrief").click(); true`);
  await sleep(1000);
  await until(`!document.querySelector("#deb-out .working") && document.getElementById("deb-out").innerText.length > 200`, 180000, "debrief");
  await tidy(); await sleep(800); await shot("debrief");
}
if (want("patterns")) { await mode("patterns"); await sleep(1500); await tidy(); await sleep(400); await shot("patterns"); }
if (want("review")) {
  await mode("review");
  await js(`document.getElementById("btn-weekly").click(); true`);
  await sleep(1000);
  await until(`!document.querySelector("#wk-out .working") && document.getElementById("wk-out").innerText.length > 200`, 180000, "weekly");
  await tidy(); await sleep(800); await shot("review");
}
if (want("health")) { await mode("health"); await sleep(2500); await tidy(); await sleep(400); await shot("health"); }
ws.close();
