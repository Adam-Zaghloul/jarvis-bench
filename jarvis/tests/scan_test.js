// node jarvis/tests/scan_test.js — scanner vs human typing. Exit 1 on failure.
const ScanDetector = require("../static/scan.js");
let fail = 0;
function run(name, keys, expect) {
  const d = new ScanDetector(); let got = null, t = 0;
  for (const [k, dt] of keys) { t += dt; const r = d.feed(k, t, {}); if (r && r.scan) got = r.scan; }
  const ok = expect === null ? got === null : got === expect;
  console.log((ok ? "PASS " : "FAIL ") + name + (ok ? "" : "  got " + JSON.stringify(got)));
  if (!ok) fail++;
}
const seq = (s, gap) => s.split("").map((c, i) => [c, i ? gap : 1000]);
const SN = "10000000000011";
run("scanner 14 chars @15ms + Enter", [...seq(SN, 15), ["Enter", 10]], SN);
run("scanner @45ms + Tab", [...seq(SN, 45), ["Tab", 30]], SN);
run("scanner with Shift for capitals", [["L",1000],["Shift",2],["G",8],["2",12],["6",12],["3",12],["7",12],["O",12],["B",12],["Enter",12]], "LG2637OB");
run("human types serial @120ms + Enter", [...seq(SN, 120), ["Enter", 150]], null);
run("fast human @70ms (very fast typist)", [...seq(SN, 70), ["Enter", 80]], null);
run("human burst 'the' @35ms then normal", [...seq("the", 35), ...seq(" board", 140).slice(0), ["Enter", 200]], null);
run("rollover burst of 5 then Enter fast", [...seq("abcde", 20), ["Enter", 20]], null);
run("fast chars but Enter 400ms later", [...seq(SN, 15), ["Enter", 400]], null);
run("one slow gap in the middle", [...seq("8062309", 15), ...seq("0636864", 15).map((x, i) => i ? x : [x[0], 300]), ["Enter", 10]], "0636864");
run("Ctrl+V paste then Enter", [["v", 1000], ["Enter", 5]], null);
run("typing a log line then Enter", [...seq("C64 5.03 V", 110), ["Enter", 200]], null);
run("Backspace breaks a burst", [...seq("806230", 15), ["Backspace", 15], ...seq("90636864", 15).map((x, i) => i ? x : [x[0], 15]), ["Enter", 10]], "90636864");
process.exit(fail ? 1 : 0);
