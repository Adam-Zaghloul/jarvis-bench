// JARVIS front end. No framework, no network beyond 127.0.0.1.
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var esc = JMD.esc;

  // ------------------------------------------------------------ settings (per-browser convenience only)
  var DEFAULTS = { voice: true, speak: false, voiceName: "", sound: false, motion: false, predict: false, lang: "en", mode: "ask" };
  var settings = Object.assign({}, DEFAULTS);
  try { Object.assign(settings, JSON.parse(localStorage.getItem("jarvis.settings") || "{}")); } catch (e) {}
  function saveSettings() { try { localStorage.setItem("jarvis.settings", JSON.stringify(settings)); } catch (e) {} }

  // ------------------------------------------------------------ api
  function api(path, body) {
    var opt = body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json", "X-Jarvis": "1" }, body: JSON.stringify(body)
    };
    // POST /api/log is token-protected (same token Shortcuts uses); fetch it once from this same-origin page.
    var pre = Promise.resolve();
    if (path === "/api/log" && body !== undefined) {
      api._tok = api._tok || fetch("/api/token").then(function (r) { return r.json(); }).then(function (d) { return d.token; });
      pre = api._tok.then(function (t) { opt.headers.Authorization = "Bearer " + t; });
    }
    return pre.then(function () { return fetch(path, opt); }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok) { var e = new Error(d.error || ("HTTP " + r.status)); e.hint = d.hint; throw e; }
        return d;
      });
    });
  }

  // ------------------------------------------------------------ state
  var S = { status: null, active: null, session: null, busy: false, abort: null, mode: "ask", busyCount: 0 };

  function setOrb(state) {
    document.body.dataset.state = state;
    $("orb").setAttribute("aria-label", "JARVIS status: " + state);
  }
  function busy(on) {
    S.busyCount = Math.max(0, S.busyCount + (on ? 1 : -1));
    if (S.busyCount) setOrb("thinking");
    else if (document.body.dataset.state === "thinking") setOrb("idle");
  }

  function toast(msg, warn) {
    var t = $("toast"); t.textContent = msg; t.className = "toast" + (warn ? " warn" : ""); t.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(function () { t.hidden = true; }, 2600);
  }

  // ------------------------------------------------------------ sound (off by default, synthesised, no files)
  var actx = null;
  function beep(kind) {
    if (!settings.sound) return;
    try {
      actx = actx || new (window.AudioContext || window.webkitAudioContext)();
      var o = actx.createOscillator(), g = actx.createGain();
      o.type = "sine"; o.frequency.value = kind === "error" ? 220 : kind === "log" ? 1320 : 880;
      g.gain.setValueAtTime(0.05, actx.currentTime); g.gain.exponentialRampToValueAtTime(0.0001, actx.currentTime + 0.15);
      o.connect(g); g.connect(actx.destination); o.start(); o.stop(actx.currentTime + 0.16);
    } catch (e) {}
  }

  // ------------------------------------------------------------ speech (off by default; local voices only)
  function localVoices() {
    if (!window.speechSynthesis) return [];
    return speechSynthesis.getVoices().filter(function (v) { return v.localService === true; });
  }
  function fillVoices() {
    var sel = $("set-voice-name"), vs = localVoices();
    sel.innerHTML = "";
    vs.forEach(function (v) {
      var o = document.createElement("option"); o.value = v.name; o.textContent = v.name + " (" + v.lang + ")";
      if (v.name === settings.voiceName) o.selected = true; sel.appendChild(o);
    });
    $("voice-note").textContent = !window.speechSynthesis ? "This browser has no speech synthesis." :
      vs.length ? vs.length + " on-device voices. Cloud voices are hidden." : "No on-device voices found; spoken answers stay off.";
    $("set-speak").disabled = !vs.length;
  }
  function speak(md) {
    if (!settings.speak || !window.speechSynthesis) return;
    var vs = localVoices(); if (!vs.length) return;
    var text = String(md).split(/##\s*General knowledge/i)[0]
      .replace(/\[\[[^\]]+\]\]/g, "").replace(/[#*_`>|]/g, "").replace(/\s+/g, " ").trim();
    var u = new SpeechSynthesisUtterance(text.slice(0, 1200));
    u.voice = vs.filter(function (v) { return v.name === settings.voiceName; })[0] || vs[0];
    u.lang = u.voice.lang;
    speechSynthesis.cancel(); speechSynthesis.speak(u);
  }

  // ------------------------------------------------------------ status voice
  function partOfDay() { var h = new Date().getHours(); return h < 12 ? "Good morning." : h < 18 ? "Good afternoon." : "Good evening."; }
  function statusLine() {
    var s = S.status; if (!s) return;
    var el = $("status-line"), h = s.health || {}, n = (s.open_prev || []).length, bk = s.backup, txt, cls = "";
    if (h.ok === false) { cls = "fail"; txt = (settings.voice ? "I'm afraid the brain is offline. " : "Brain offline: ") + (h.detail || ""); }
    else if (settings.voice) {
      txt = partOfDay() + " ";
      if (s.prev_day && n) txt += n + (n === 1 ? " board" : " boards") + " still open from " + dayName(s.prev_day) + ".";
      else if (s.prev_day) txt += "Everything from " + dayName(s.prev_day) + " was closed out.";
      else txt += "No previous shifts on file.";
      if (s.today_entries) txt += " " + s.today_entries + " entries logged today.";
      if (bk && bk.stale) txt += bk.last ? " Your last backup was " + bk.age_days + " days ago." : " No backup yet.";
      if (h.ok === null) txt += " Checking the brain.";
    } else {
      txt = (s.prev_day ? n + " open from " + s.prev_day : "No previous log") + " · " + s.today_entries + " entries today" +
            (bk && bk.stale ? (bk.last ? " · last backup " + bk.age_days + " d ago" : " · no backup yet") : "") +
            (h.ok === null ? " · brain check pending" : "");
    }
    if (h.ok && (n || (bk && bk.stale))) cls = "warn";
    el.className = "status-line " + cls; el.textContent = txt;
    if (window.J && J.afterStatus) J.afterStatus(el);
  }
  function dayName(iso) {
    var d = new Date(iso + "T12:00:00"), t = new Date(); t.setHours(12, 0, 0, 0);
    var diff = Math.round((t - d) / 864e5);
    return diff === 1 ? "yesterday" : diff < 7 ? d.toLocaleDateString("en", { weekday: "long" }) : iso;
  }

  // ------------------------------------------------------------ boot sequence
  function openList(bs) {
    bs = bs || [];
    if (!bs.length) return "0";
    var names = bs.slice(0, 4).map(function (b) { return "…" + String(b.serial).slice(-5); });
    return bs.length + " (" + names.join(", ") + (bs.length > 4 ? ", +" + (bs.length - 4) : "") + ")";
  }
  function boot(s) {
    var seen = null;
    try { seen = sessionStorage.getItem("jarvis.boot"); } catch (e) {}
    if (seen === s.boot_id) { watchHealth(false); return; }
    try { sessionStorage.setItem("jarvis.boot", s.boot_id); } catch (e) {}
    var el = $("boot"), list = $("boot-lines"), done = false;
    document.body.classList.add("boot-on"); el.hidden = false;
    var lines = [
      ["Docs indexed", s.docs],
      ["Past cases on file", s.cases],
      ["Past log entries", s.past_log_entries],
      ["Today's entries", s.today_entries],
      ["Open from " + (s.prev_day ? dayName(s.prev_day) : "previous shift"), openList(s.open_prev)],
      ["Last backup", !s.backup || !s.backup.last ? "never" : s.backup.age_days === 0 ? "today" : s.backup.age_days + " days ago" + (s.backup.stale ? " ⚠" : "")],
    ];
    lines.forEach(function (l, i) {
      var li = document.createElement("li");
      li.style.animationDelay = (i * 0.18) + "s";
      li.innerHTML = esc(String(l[0]).padEnd(26, ".")) + ' <span class="v">' + esc(String(l[1])) + "</span>";
      list.appendChild(li);
    });
    var hl = document.createElement("li"); hl.id = "boot-health"; hl.style.animationDelay = (lines.length * 0.18) + "s";
    list.appendChild(hl);
    renderBootHealth(s.health);
    function finish() {
      if (done) return;
      if (S.status && S.status.health && S.status.health.ok === false) return; // error panel holds the screen
      done = true; el.hidden = true; document.body.classList.remove("boot-on");
      document.removeEventListener("keydown", skip, true); el.removeEventListener("click", skip);
      $("ql-text").focus();
    }
    function skip(e) {
      if (!$("boot-error").hidden) return; // error panel: let Tab/Enter reach its buttons
      if (e.type === "keydown") e.preventDefault();
      finish();
    }
    document.addEventListener("keydown", skip, true); el.addEventListener("click", skip);
    setTimeout(finish, 2000);
    boot.finish = function () { done = false; finish(); };
    watchHealth(true);
  }
  function renderBootHealth(h) {
    var li = $("boot-health"); if (!li) return;
    h = h || {};
    var v = h.ok === null || h.ok === undefined ? '<span class="pending">checking…</span>' :
            h.ok ? '<span class="v">online' + (h.mock ? " (mock)" : h.startup_s ? " · " + h.startup_s + " s" : "") + "</span>" :
            '<span class="bad">OFFLINE</span>';
    li.innerHTML = esc("Claude Code".padEnd(26, ".")) + " " + v;
  }
  function showBrainError(h) {
    // Reopen the boot screen in error state, even if the 2 s boot already finished.
    document.body.classList.add("boot-on");
    $("boot").hidden = false; $("boot-skip").hidden = true;
    $("boot-error").hidden = false;
    $("boot-error-msg").textContent = h.detail || "Claude Code did not answer.";
    $("boot-error-hint").textContent = h.hint || "";
    setOrb("error");
    $("boot-continue").focus();
  }
  function watchHealth(onBoot) {
    var tries = 0;
    (function poll() {
      api("/api/status").then(function (s) {
        S.status = s; statusLine(); renderBootHealth(s.health);
        if (s.health.ok === null && tries++ < 60) return setTimeout(poll, 1000);
        if (s.health.ok === false) showBrainError(s.health);
      });
    })();
  }
  $("boot-continue").addEventListener("click", function () {
    $("boot").hidden = true; document.body.classList.remove("boot-on"); $("boot-error").hidden = true;
    $("ql-text").focus();
  });
  $("boot-retry").addEventListener("click", function () {
    $("boot-error-msg").textContent = "Checking…";
    api("/api/health", {}).then(function (h) {
      S.status.health = h; statusLine(); renderBootHealth(h);
      if (h.ok) { $("boot-error").hidden = true; setOrb("idle"); $("boot").hidden = true; document.body.classList.remove("boot-on"); toast("Brain online."); }
      else showBrainError(h);
    });
  });

  // ------------------------------------------------------------ modes
  var PANES = Array.prototype.map.call(document.querySelectorAll(".mode"), function (b) { return b.dataset.mode; });
  function setMode(m, focus) {
    S.mode = m; settings.mode = m; saveSettings();
    PANES.forEach(function (p) { $("pane-" + p).hidden = p !== m; });
    document.querySelectorAll(".mode").forEach(function (b) {
      if (b.dataset.mode === m) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
    });
    if (m === "log") loadLog();
    if (m === "seen" && !$("seen-input").value) prefillSeen();
    if (m === "debrief") loadSavedDebrief();
    if (window.J && J.onMode) J.onMode(m);
    if (focus !== false) {
      var f = { ask: "ask-input", seen: "seen-input", log: "log-date", debrief: "btn-debrief" }[m];
      var el = f ? $(f) : $("pane-" + m).querySelector("button, input, select, textarea");
      setTimeout(function () { if (el) el.focus(); }, 0);
    }
  }
  document.querySelectorAll(".mode").forEach(function (b) { b.addEventListener("click", function () { setMode(b.dataset.mode); }); });

  // ------------------------------------------------------------ active board
  function renderBoard(a, switched) {
    S.active = a;
    var box = $("board");
    if (!a) {
      box.classList.add("none"); $("board-type").textContent = "—"; $("board-serial").textContent = "No board set";
      $("board-meta").textContent = "";
      $("ql-board").textContent = "NO BOARD"; $("quicklog").classList.add("disabled");
      $("ql-text").placeholder = "Set the active board first (Alt+B)";
      return;
    }
    box.classList.remove("none");
    $("board-type").textContent = a.board_type + (a.rev ? " rev " + a.rev : ""); $("board-serial").textContent = a.serial;
    $("board-meta").textContent = a.ticket || "";
    $("ql-board").textContent = a.board_type + " …" + a.serial.slice(-5);
    $("quicklog").classList.remove("disabled");
    $("ql-text").placeholder = "Log to …" + a.serial.slice(-5) + " · m: a: o: r: set kind";
    if (switched) {
      box.classList.remove("switched"); void box.offsetWidth; box.classList.add("switched");
      var f = $("switch-flash");
      f.innerHTML = "BOARD SWITCHED<small>" + esc(a.board_type) + " · " + esc(a.serial) + "</small>";
      f.hidden = false; f.style.animation = "none"; void f.offsetWidth; f.style.animation = "";
      setTimeout(function () { f.hidden = true; }, 1150);
    }
    if (window.J && J.onBoard) J.onBoard(a, switched);
  }
  function openBoardDialog() {
    $("bd-err").hidden = true;
    $("bd-type").value = (S.active && S.active.board_type) || "DEMO";
    $("bd-serial").value = "";
    $("bd-rev").value = (S.active && S.active.rev) || "";
    $("bd-ticket").value = "";
    $("dlg-board").showModal(); $("bd-serial").focus();
  }
  function switchBoard(board_type, serial, rev, ticket, via) {
    return api("/api/board", { board_type: board_type, serial: serial, rev: rev, ticket: ticket, via: via || "" }).then(function (d) {
      var changed = !S.active || S.active.serial !== d.active.serial;
      renderBoard(d.active, changed); refreshStatus();
      if (S.mode === "log") loadLog();
      if (changed && S.session) { newQuestion(); toast("Board switched: Ask session reset so readings don't mix."); }
      return d.active;
    });
  }
  $("btn-switch").addEventListener("click", openBoardDialog);
  $("bd-cancel").addEventListener("click", function () { $("dlg-board").close(); });
  $("board-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var serial = $("bd-serial").value.trim();
    var via = $("dlg-board").dataset.via || "";   // "scan" when the scanner opened this dialog (usage count only)
    switchBoard($("bd-type").value, serial, $("bd-rev").value.trim(), $("bd-ticket").value.trim(), via).then(function () {
      $("dlg-board").close(); $("ql-text").focus();
    }).catch(function (err) { $("bd-err").textContent = err.message; $("bd-err").hidden = false; });
  });

  // ------------------------------------------------------------ quick log
  var KIND_PREFIX = { m: "measurement", a: "action", o: "observation", r: "result" };
  $("quicklog").addEventListener("submit", function (e) {
    e.preventDefault();
    if (!S.active) { openBoardDialog(); return; }
    var text = $("ql-text").value.trim(), kind = $("ql-kind").value, m = /^([maor]):\s*/i.exec(text);
    if (m) { kind = KIND_PREFIX[m[1].toLowerCase()]; text = text.slice(m[0].length); }
    if (!text && !(window.J && J.pendingPhotos && J.pendingPhotos.length)) return;
    var raw = $("ql-text").value, st = $("ql-status").value;
    var extra = (window.J && J.beforeLog) ? J.beforeLog(text) : {};
    // Clear now, not on response: fast typing after Enter must not be wiped.
    $("ql-text").value = ""; $("ql-status").value = "";
    if (window.J && J.afterClear) J.afterClear();
    api("/api/log", Object.assign({ text: text, kind: kind || null, status: st || null, serial: S.active.serial }, extra)).then(function (d) {
      beep("log");
      var r = d.entry.reading, c = d.entry.check;
      toast("Logged to " + d.entry.serial + (d.entry.kind ? " · " + d.entry.kind : "") + (d.entry.status ? " · " + d.entry.status : "") +
            (r ? " · " + r.test_point + " " + d.entry.reading_display : "") + (c && c.status === "out" ? " · OUT OF RANGE" : ""), c && c.status === "out");
      refreshStatus(); if (S.mode === "log") loadLog(true);
      if (window.J && J.afterLog) J.afterLog(d);
    }).catch(function (err) {
      toast("Not saved: " + err.message, true);
      if (!$("ql-text").value) { $("ql-text").value = raw; $("ql-status").value = st; }
    });
  });
  function undo() {
    api("/api/log/undo", {}).then(function (d) {
      toast(d.removed ? "Removed: " + d.removed.text.slice(0, 60) : "Nothing to undo today.", !d.removed);
      refreshStatus(); if (S.mode === "log") loadLog();
    });
  }
  $("btn-undo").addEventListener("click", undo);

  function today() { var d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); }
  $("log-date").value = today(); $("deb-date").value = today();
  $("log-date").addEventListener("change", function () { loadLog(); });

  function badge(st) { return st ? '<span class="badge badge-' + esc(st) + '">' + esc(st) + "</span>" : ""; }
  function loadLog(flashLast) {
    var date = $("log-date").value || today();
    api("/api/log?date=" + encodeURIComponent(date)).then(function (d) {
      var ol = $("entries"), last = null, html = "";
      if (!d.entries.length) html = '<li class="hint">No entries for ' + esc(date) + ".</li>";
      d.entries.forEach(function (e, i) {
        if (e.serial !== last) {
          html += '<li class="board-divider">' + esc(e.board_type) + " · " + esc(e.serial) + "</li>"; last = e.serial;
        }
        html += '<li class="entry' + (flashLast && i === d.entries.length - 1 ? " new" : "") + '">' +
          '<span class="ts">' + esc(e.ts.slice(11)) + '</span><span class="sn">' + esc(e.serial) + "</span>" +
          '<span class="kind">' + esc(e.kind || "") + "</span><span>" + esc(e.text) + (window.J && J.readingChip ? J.readingChip(e) : "") + (window.J && J.photoThumbs ? J.photoThumbs(e) : "") +
          "</span>" + badge(e.status) + "</li>";
      });
      ol.innerHTML = html;
      $("btn-undo").disabled = date !== today() || !d.entries.length;
    });
  }

  // ------------------------------------------------------------ citations + source viewer
  function parseCite(c) {
    c = c.trim();
    var m = /^(.+?\.(?:pdf|PDF))\s*(?:p\.?|page|#page=|#p)\s*(\d+)/.exec(c);
    if (m) return { path: m[1].trim(), page: +m[2], label: m[1].split("/").pop() + " p." + m[2] };
    var i = c.indexOf("#"), path = i < 0 ? c : c.slice(0, i), frag = i < 0 ? "" : c.slice(i + 1);
    path = path.trim().replace(/^\.\//, "");
    var lm = /^L(\d+)(?:\s*-\s*L?(\d+))?$/.exec(frag.trim());
    var o = { path: path, frag: frag.trim() };
    if (lm) { o.l1 = +lm[1]; o.l2 = +(lm[2] || lm[1]); }
    var short = path.split("/").pop().replace(/\.md$/, "");
    if (short.length > 28) short = short.slice(0, 26) + "…";
    o.label = short + (o.l1 ? ":" + o.l1 + (o.l2 !== o.l1 ? "–" + o.l2 : "") : o.frag ? " § " + o.frag.slice(0, 32) : "");
    return o;
  }
  function chip(c) {
    var o = parseCite(c);
    return '<button type="button" class="chip" data-cite="' + esc(c) + '" title="' + esc(c) + '">' + esc(o.label) + "</button>";
  }
  document.addEventListener("click", function (e) {
    var t = e.target.closest(".chip, .doclink, [data-open]");
    if (!t) return;
    e.preventDefault();
    if (t.classList.contains("chip")) openSource(parseCite(t.dataset.cite), t);
    else if (t.dataset.open) openSource(parseCite(t.dataset.open), t);
    else openSource(parseCite(t.dataset.path), t);
  });
  document.addEventListener("keydown", function (e) {
    var t = e.target; if (e.key === "Enter" && t.dataset && t.dataset.open && t.tagName === "LI") { e.preventDefault(); openSource(parseCite(t.dataset.open), t); }
  });

  function fold(s) { return String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[*_`]/g, "").replace(/\s+/g, " ").trim(); }

  function openSource(o, from) {
    document.body.classList.remove("viewer-closed");
    var body = $("viewer-body");
    $("viewer-path").textContent = o.path + (o.page ? " · page " + o.page : o.l1 ? " · L" + o.l1 + "–" + o.l2 : o.frag ? " · " + o.frag : "");
    body.innerHTML = '<p class="hint">Loading…</p>';
    api("/api/file?path=" + encodeURIComponent(o.path)).then(function (d) {
      if (d.ext === ".pdf") {
        body.innerHTML = '<iframe title="' + esc(o.path) + '" src="/api/raw?path=' + encodeURIComponent(o.path) + (o.page ? "#page=" + o.page : "") + '"></iframe>';
        return;
      }
      if (d.ext === ".png" || d.ext === ".jpg") { body.innerHTML = '<img alt="' + esc(o.path) + '" src="/api/raw?path=' + encodeURIComponent(o.path) + '">'; return; }
      if (d.ext === ".md") {
        body.innerHTML = JMD.render(d.text, { cite: chip });
        highlightMd(body, o, d.text);
      } else {
        var lines = d.text.split("\n");
        body.innerHTML = '<pre class="src-lines">' + lines.map(function (l, i) {
          var n = i + 1, hl = o.l1 && n >= o.l1 && n <= o.l2;
          return '<span data-l1="' + n + '" data-l2="' + n + '"' + (hl ? ' class="hl"' : "") + ">" + (esc(l) || " ") + "</span>";
        }).join("") + "</pre>";
        scrollToHl(body);
      }
    }).catch(function (err) {
      body.innerHTML = '<p class="err">' + esc(err.message) + '</p><p class="hint">Citation <code>' + esc(o.path) + "</code> does not match a file in the repo. Treat the claim as unverified.</p>";
      if (from && from.classList) from.classList.add("missing");
    });
  }
  function highlightMd(body, o, text) {
    var els = body.querySelectorAll("[data-l1]"), l1 = o.l1, l2 = o.l2;
    if (!l1 && o.frag) {
      var want = fold(o.frag), hs = body.querySelectorAll("[data-heading]"), hit = null;
      hs.forEach(function (h) { if (!hit && fold(h.dataset.heading) === want) hit = h; });
      hs.forEach(function (h) { if (!hit && (fold(h.dataset.heading).indexOf(want) >= 0 || want.indexOf(fold(h.dataset.heading)) >= 0) && fold(h.dataset.heading).length > 2) hit = h; });
      if (hit) {
        var lvl = +hit.tagName[1]; l1 = +hit.dataset.l1; l2 = text.split("\n").length;
        var after = false;
        hs.forEach(function (h) { if (h === hit) { after = true; return; } if (after && +h.tagName[1] <= lvl && +h.dataset.l1 > l1 && +h.dataset.l1 - 1 < l2) { l2 = +h.dataset.l1 - 1; after = false; } });
      } else {
        // Fall back to a text search for the fragment.
        var lines = text.split("\n");
        for (var i = 0; i < lines.length; i++) if (fold(lines[i]).indexOf(want) >= 0) { l1 = l2 = i + 1; break; }
      }
    }
    if (!l1) return;
    // Highlight the most specific overlapping blocks (a table row or list item, not the whole table/list).
    var hits = [];
    els.forEach(function (el) { if (+el.dataset.l1 <= l2 && +el.dataset.l2 >= l1) hits.push(el); });
    hits.forEach(function (el) {
      var inner = false;
      for (var j = 0; j < hits.length; j++) if (hits[j] !== el && el.contains(hits[j])) { inner = true; break; }
      if (!inner) el.classList.add("hl");
    });
    scrollToHl(body);
  }
  function scrollToHl(body) {
    var h = body.querySelector(".hl");
    if (h) h.scrollIntoView({ block: "center", behavior: document.body.classList.contains("reduce-motion") ? "auto" : "smooth" });
    else body.scrollTop = 0;
  }
  $("viewer-close").addEventListener("click", function () { document.body.classList.add("viewer-closed"); });

  // ------------------------------------------------------------ ASK
  function newQuestion() {
    if (S.abort) S.abort.abort();
    S.session = null; $("convo").innerHTML = ""; $("session-tag").hidden = true; $("btn-followup").disabled = true;
    $("ask-input").value = ""; $("ask-input").placeholder = "Ask the docs… (English or français)"; $("ask-input").focus();
  }
  $("btn-new").addEventListener("click", newQuestion);
  $("btn-followup").addEventListener("click", function () { $("ask-input").focus(); });
  $("ask-input").addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("ask-form").requestSubmit(); }
  });
  $("btn-stop").addEventListener("click", function () { if (S.abort) S.abort.abort(); });

  $("ask-form").addEventListener("submit", function (e) {
    e.preventDefault();
    if (S.busy) return;
    var q = $("ask-input").value.trim(); if (!q) return;
    var withCtx = $("ask-ctx").checked;
    if (withCtx && !S.active) { toast("No active board: question sent without board context.", true); withCtx = false; }
    var convo = $("convo");
    var qd = document.createElement("div"); qd.className = "q"; qd.textContent = q;
    if (withCtx) { var c = document.createElement("span"); c.className = "q-ctx"; c.textContent = "+ board " + S.active.serial + " and today's log"; qd.appendChild(c); }
    convo.appendChild(qd);
    var ad = document.createElement("div"); ad.className = "a"; convo.appendChild(ad);
    // ab = answer body (re-rendered while streaming); ax = extras that must survive re-renders (hypothesis, feedback)
    var ax = document.createElement("div"); ax.className = "a-extra";
    var ab = document.createElement("div"); ab.className = "a-body"; ab.innerHTML = '<p class="activity">Thinking…</p>';
    ad.appendChild(ax); ad.appendChild(ab);
    if (window.J && J.onAskStart) J.onAskStart({ question: q, withCtx: withCtx, ad: ad, ax: ax, ab: ab });
    ad.scrollIntoView({ block: "end" });
    $("ask-input").value = "";
    S.busy = true; busy(true); $("btn-ask").disabled = true; $("btn-stop").hidden = false;
    var ctrl = new AbortController(); S.abort = ctrl;
    var text = "", activity = "Thinking…", lastRender = 0, t0 = performance.now(), gotDone = false;

    function render(final) {
      var now = performance.now();
      if (!final && now - lastRender < 80) return; lastRender = now;
      ab.innerHTML = (text ? JMD.render(text, { cite: chip }) : "") +
        (final ? "" : '<p class="activity' + (text ? " cursor" : "") + '">' + esc(activity) + "</p>");
    }
    function fail(msg, hint) {
      ad.className = "a err";
      ab.innerHTML = (text ? JMD.render(text, { cite: chip }) + "<hr>" : "") + "<h3>" + esc(msg) + "</h3>" + (hint ? "<p>" + esc(hint) + "</p>" : "");
      ad.classList.remove("held");
      setOrb("error"); beep("error");
    }
    fetch("/api/ask", {
      method: "POST", signal: ctrl.signal,
      headers: { "Content-Type": "application/json", "X-Jarvis": "1" },
      body: JSON.stringify({ question: q, session_id: S.session, board_context: withCtx })
    }).then(function (r) {
      if (!r.ok) return r.json().then(function (d) { throw Object.assign(new Error(d.error || "HTTP " + r.status), { hint: d.hint }); });
      var reader = r.body.getReader(), dec = new TextDecoder(), buf = "";
      function pump() {
        return reader.read().then(function (res) {
          if (res.done) return;
          buf += dec.decode(res.value, { stream: true });
          var parts = buf.split("\n"); buf = parts.pop();
          parts.forEach(function (line) {
            if (!line.trim()) return;
            var ev; try { ev = JSON.parse(line); } catch (x) { return; }
            if (ev.type === "session") S.session = ev.id;
            else if (ev.type === "tool") {
              activity = !ev.detail ? "Using " + ev.name : ev.name === "Read" ? "Reading " + ev.detail :
                         ev.name === "Grep" ? "Searching docs for “" + ev.detail + "”" : "Listing " + ev.detail;
              render();
            }
            else if (ev.type === "delta") { if (!text) setOrb("answering"); text += ev.text; activity = "…"; render(); }
            else if (ev.type === "done") {
              gotDone = true; text = ev.text || text; S.session = ev.session_id || S.session; render(true);
              var meta = document.createElement("div"); meta.className = "a-meta";
              meta.textContent = (ev.duration_s || ((performance.now() - t0) / 1000).toFixed(1)) + " s · session " + String(S.session || "").slice(0, 8);
              ad.appendChild(meta); beep("done"); setOrb("idle");
              if (window.J && J.onAskDone) J.onAskDone({ question: q, text: text, session_id: S.session, ad: ad, ax: ax, withCtx: withCtx, speak: function () { speak(text); } });
              else speak(text);
            } else if (ev.type === "error") { gotDone = true; fail(ev.message, ev.hint); }
          });
          return pump();
        });
      }
      return pump();
    }).catch(function (err) {
      if (err.name === "AbortError") { gotDone = true; render(true); ad.insertAdjacentHTML("beforeend", '<p class="hint">Stopped.</p>'); setOrb("idle"); return; }
      gotDone = true; fail(err.message === "Failed to fetch" ? "Lost contact with the JARVIS server." : err.message,
        err.hint || "Is the JARVIS window (cmd.exe) still open? Restart with jarvis.bat.");
    }).then(function () {
      if (!gotDone) fail("The answer stream ended early.", "Retry. If it repeats, check jarvis/logs/brain.log.");
      S.busy = false; busy(false); S.abort = null;
      if (document.body.dataset.state === "answering") setOrb("idle");
      $("btn-ask").disabled = false; $("btn-stop").hidden = true;
      if (S.session) { $("session-tag").hidden = false; $("btn-followup").disabled = false; $("ask-input").placeholder = "Follow-up (keeps context) — or Alt+N for a new question"; }
      var hypIn = ad.classList.contains("held") && ax.querySelector("input");
      (hypIn || $("ask-input")).focus();
    });
  });

  // ------------------------------------------------------------ SEEN BEFORE
  function prefillSeen() {
    api("/api/seen/prefill").then(function (d) { if (d.text && !$("seen-input").value) $("seen-input").value = d.text; });
  }
  function markTokens(s, toks) {
    var h = esc(s);
    toks.forEach(function (t) {
      if (t.length < 2) return;
      h = h.replace(new RegExp("(" + t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig"), "<mark>$1</mark>");
    });
    return h;
  }
  function card(c, unres) {
    var src = c.source_path + "#L" + c.source_line;
    return '<article class="card' + (unres ? " unres" : "") + '">' +
      (unres ? '<span class="label-unres">UNRESOLVED</span>' : "") +
      "<dl><dt>Date</dt><dd>" + esc(c.date || "—") + "</dd>" +
      "<dt>Board</dt><dd>" + esc(c.board_type || "—") + ' <span class="serial">' + esc(c.serial || "serial not recorded") + "</span></dd>" +
      "<dt>Symptom</dt><dd>" + esc(c.symptom) + "</dd>" +
      "<dt>Fix</dt><dd>" + esc(c.fix || "—") + "</dd>" +
      "<dt>Outcome</dt><dd>" + esc(c.outcome || "—") + "</dd></dl>" + chip(src) + "</article>";
  }
  $("seen-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var q = $("seen-input").value.trim(); if (!q) return;
    var out = $("seen-out");
    out.innerHTML = '<p class="working">Searching…</p>';
    var token = (S.seenToken = (S.seenToken || 0) + 1);
    api("/api/seen/fast", { q: q }).then(function (r) {
      if (token !== S.seenToken) return;
      var html = (J.patternsBlock ? J.patternsBlock(r.patterns) : "") + '<h3 class="section-h">Keyword matches · ' + (r.hits.length > 15 ? "top 15 of " : "") + r.hits.length + ' <span class="hint">(instant, no AI)</span></h3>';
      if (!r.hits.length) html += '<p class="hint">No matches for: ' + esc(r.tokens.join(", ") || q) + "</p>";
      else html += '<ol class="hits">' + r.hits.slice(0, 15).map(function (h) {
        var m = h.meta || {};
        return '<li class="hit" tabindex="0" data-open="' + esc(h.path + "#L" + h.line + (h.line_end ? "-L" + h.line_end : "")) + '">' +
          '<span class="hp">' + esc(h.path) + ":" + h.line + "</span> " + (h.heading ? "· " + esc(h.heading) + " " : "") +
          (m.serial ? '<span class="hint">' + esc(m.serial) + " " + esc(m.date || "") + " " + esc(m.status || "") + "</span>" : "") +
          "<div>" + markTokens(h.snippet, r.tokens) + "</div></li>";
      }).join("") + "</ol>";
      html += '<div id="seen-brain"><p class="working">' + (r.hits.length ? "Brain is grouping " + r.hits.length + " matches into cases…" : "") + "</p></div>";
      out.innerHTML = html;
      if (!r.hits.length) return;
      busy(true);
      return api("/api/seen/brain", { q: q }).then(function (b) {
        if (token !== S.seenToken) return;
        var el = $("seen-brain");
        if (b.error) { el.innerHTML = '<div class="a err"><h3>' + esc(b.error.message) + "</h3><p>" + esc(b.error.hint || "") + "</p><p>The keyword matches above are still valid.</p></div>"; setOrb("error"); return; }
        var s = b.summary || {}, h = "";
        var md = function (x) { return JMD.inline(String(x || ""), { cite: chip }); };
        h += '<h3 class="section-h">Pattern</h3><div class="summary"><span class="big">' + esc(String(s.similar_count != null ? s.similar_count : (b.resolved.length + b.unresolved.length))) + "</span>similar case(s). " + md(s.pattern) +
          (s.worked && s.worked.length ? "<h4>Fixes that worked</h4><ul>" + s.worked.map(function (x) { return "<li>" + md(x) + "</li>"; }).join("") + "</ul>" : "") +
          (s.did_not_work && s.did_not_work.length ? "<h4>Didn't work</h4><ul>" + s.did_not_work.map(function (x) { return "<li>" + md(x) + "</li>"; }).join("") + "</ul>" : "") +
          '<p class="hint">' + (b.duration_s ? b.duration_s + " s" : "") + "</p></div>";
        h += '<h3 class="section-h">Resolved cases · ' + b.resolved.length + "</h3>";
        h += b.resolved.length ? '<div class="cards">' + b.resolved.map(function (c) { return card(c, false); }).join("") + "</div>" : '<p class="hint">None.</p>';
        h += '<h3 class="section-h unres">Unresolved · ' + b.unresolved.length + "</h3>";
        h += b.unresolved.length ? '<div class="cards">' + b.unresolved.map(function (c) { return card(c, true); }).join("") + "</div>" : '<p class="hint">None.</p>';
        if (b.dropped && b.dropped.length) h += '<p class="hint">⚠ ' + b.dropped.length + " case(s) dropped: their source could not be found in the repo.</p>";
        el.innerHTML = h;
        beep("done");
      }).catch(function (err) { $("seen-brain").innerHTML = '<div class="a err"><h3>' + esc(err.message) + "</h3></div>"; setOrb("error"); })
        .then(function () { busy(false); });
    }).catch(function (err) { out.innerHTML = '<p class="err">' + esc(err.message) + "</p>"; });
  });

  // ------------------------------------------------------------ DEBRIEF
  $("deb-lang").value = settings.lang;
  $("deb-lang").addEventListener("change", function () { settings.lang = $("deb-lang").value; saveSettings(); $("set-lang").value = settings.lang; });
  $("deb-date").addEventListener("change", loadSavedDebrief);
  function copyText(text, btn) {
    function ok() { var o = btn.textContent; btn.textContent = "Copied ✓"; setTimeout(function () { btn.textContent = o; }, 1400); }
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(ok, fallback); else fallback();
    function fallback() {
      var ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); ok(); } catch (e) { toast("Copy failed; select the text manually.", true); }
      ta.remove();
    }
  }
  function block(title, text, cls) {
    return '<section class="block ' + (cls || "") + '"><div class="block-h"><h3>' + esc(title) + '</h3><button type="button" class="btn copy" data-copy="' +
      esc(text) + '">Copy</button></div><pre>' + esc(text) + "</pre></section>";
  }
  document.addEventListener("click", function (e) { var b = e.target.closest("[data-copy]"); if (b) copyText(b.dataset.copy, b); });
  function loadSavedDebrief() {
    var date = $("deb-date").value || today();
    api("/api/debrief?date=" + encodeURIComponent(date)).then(function (d) {
      if (S.debBusy) return;
      $("deb-out").innerHTML = d.saved ? '<p class="hint">Saved debrief for ' + esc(date) + " (run again to regenerate):</p>" + block("Saved file", d.saved) : "";
    });
  }
  $("btn-debrief").addEventListener("click", function () {
    var date = $("deb-date").value || today(), lang = $("deb-lang").value, out = $("deb-out");
    out.innerHTML = '<p class="working">Reading the ' + esc(date) + " log and drafting…</p>";
    S.debBusy = true; busy(true); $("btn-debrief").disabled = true;
    api("/api/debrief", { date: date, lang: lang }).then(function (d) {
      if (d.empty) { out.innerHTML = '<p class="hint">' + esc(d.note) + "</p>"; return; }
      if (d.error) { out.innerHTML = '<div class="a err"><h3>' + esc(d.error.message) + "</h3><p>" + esc(d.error.hint || "") + "</p></div>"; setOrb("error"); return; }
      var fr = d.lang === "fr", h = "";
      h += block(fr ? "Mise à jour Slack" : "Slack update", d.slack);
      d.jira.forEach(function (j) { h += block((fr ? "Note Jira · " : "Jira comment · ") + j.serial, j.text); });
      h += block(fr ? "Points ouverts pour demain" : "Open items for tomorrow", d.open_items.map(function (o) { return "- " + o; }).join("\n") || "(none)");
      var g = d.gaps, gl = [];
      g.no_close.forEach(function (b) { gl.push((fr ? "Sans statut de fermeture: " : "No closing status: ") + b.board_type + " " + b.serial + (b.status ? " (" + b.status + ")" : "")); });
      g.unplaced.forEach(function (u) { gl.push((fr ? "Non placée: " : "Not placed: ") + "[" + u.ts + "] " + u.text + " — " + u.reason + (u.traced ? "" : " ⚠ no such timestamp in the log")); });
      g.untraced.forEach(function (u) { gl.push("⚠ " + (fr ? "Sans horodatage du journal: " : "No matching log timestamp: ") + "[" + (u.ts || "") + "] " + u.text); });
      h += block(fr ? "Vérification des trous" : "Gap check", gl.join("\n") || (fr ? "Aucun trou." : "No gaps."), "gaps");
      h += '<p class="hint">' + d.entries + " entries · " + (d.duration_s || "?") + " s · saved to <code>" + esc(d.saved) + "</code></p>";
      out.innerHTML = h; beep("done");
    }).catch(function (err) { out.innerHTML = '<p class="err">' + esc(err.message) + "</p>"; setOrb("error"); })
      .then(function () { S.debBusy = false; busy(false); $("btn-debrief").disabled = false; });
  });

  // ------------------------------------------------------------ settings dialog
  function applySettings() {
    document.body.classList.toggle("reduce-motion", !!settings.motion);
    $("set-voice").checked = settings.voice; $("set-speak").checked = settings.speak; $("set-sound").checked = settings.sound;
    $("set-motion").checked = settings.motion; $("set-predict").checked = !!settings.predict; $("set-lang").value = settings.lang; $("deb-lang").value = settings.lang;
    statusLine();
  }
  $("btn-settings").addEventListener("click", function () { fillVoices(); $("dlg-settings").showModal(); });
  ["voice", "speak", "sound", "motion", "predict"].forEach(function (k) {
    $("set-" + k).addEventListener("change", function () { settings[k] = $("set-" + k).checked; saveSettings(); applySettings(); });
  });
  $("set-lang").addEventListener("change", function () { settings.lang = $("set-lang").value; saveSettings(); applySettings(); });
  $("set-voice-name").addEventListener("change", function () { settings.voiceName = $("set-voice-name").value; saveSettings(); });
  if (window.speechSynthesis) speechSynthesis.onvoiceschanged = fillVoices;

  // ------------------------------------------------------------ global keys
  function typing(t) { return t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable); }
  document.addEventListener("keydown", function (e) {
    if (document.querySelector("dialog[open]") || !$("boot").hidden) return;
    if (e.altKey && !e.ctrlKey && !e.metaKey) {
      var k = e.key.toLowerCase(), code = e.code;
      var dm = /^Digit([1-9])$/.exec(code);
      if (dm && PANES[+dm[1] - 1]) { e.preventDefault(); setMode(PANES[+dm[1] - 1]); return; }
      if (code === "KeyB") { e.preventDefault(); openBoardDialog(); return; }
      if (code === "KeyZ") { e.preventDefault(); undo(); return; }
      if (code === "KeyN") { e.preventDefault(); setMode("ask", false); newQuestion(); return; }
      if (code === "KeyL") { e.preventDefault(); $("ql-text").focus(); return; }
      if (code === "Comma") { e.preventDefault(); $("btn-settings").click(); return; }
    }
    if (e.key === "/" && !typing(e.target)) { e.preventDefault(); $("ql-text").focus(); return; }
    if (e.key === "Escape") {
      if (S.abort) { S.abort.abort(); return; }
      if (typing(e.target)) { e.target.blur(); return; }
      document.body.classList.add("viewer-closed");
    }
  });

  // ------------------------------------------------------------ start
  function refreshStatus() {
    return api("/api/status").then(function (s) {
      var keepHealth = S.status && S.status.health && s.health.ok === null ? S.status.health : null;
      S.status = s; if (keepHealth) s.health = keepHealth;
      $("mock-tag").hidden = !s.mock;
      statusLine(); return s;
    });
  }
  // Hooks for v2.js (loaded after this file).
  window.J = Object.assign(window.J || {}, {
    api: api, $: $, esc: esc, S: S, settings: settings, saveSettings: saveSettings, setMode: setMode, toast: toast,
    chip: chip, openSource: openSource, refreshStatus: refreshStatus, renderBoard: renderBoard, loadLog: loadLog,
    switchBoard: switchBoard, openBoardDialog: openBoardDialog, badge: badge, today: today, setOrb: setOrb, busy: busy,
    beep: beep, copyText: copyText, block: block
  });
  applySettings();
  refreshStatus().then(function (s) {
    renderBoard(s.active, false);
    setMode(PANES.indexOf(settings.mode) >= 0 ? settings.mode : "ask", false);
    boot(s);
    if (!document.body.classList.contains("boot-on")) $("ql-text").focus();
  }).catch(function () {
    $("status-line").textContent = "Cannot reach the JARVIS server."; $("status-line").className = "status-line fail"; setOrb("error");
  });
})();
