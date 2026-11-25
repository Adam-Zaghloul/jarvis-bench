// JARVIS V2 front end. Loaded after app.js; uses the hooks it exposes on window.J.
(function () {
  "use strict";
  var J = window.J, $ = J.$, esc = J.esc, api = J.api, S = J.S;

  // ------------------------------------------------------------ helpers
  var PFX = [[1e6, "M"], [1e3, "k"], [1, ""], [1e-3, "m"], [1e-6, "µ"], [1e-9, "n"], [1e-12, "p"]];
  function fmt(v, unit) {
    if (v === null || v === undefined) return "—";
    var sym = unit === "ohm" ? "Ω" : unit, a = Math.abs(v);
    if (!a) return "0 " + sym;
    for (var i = 0; i < PFX.length; i++) {
      if (unit === "V" && (PFX[i][1] === "M" || PFX[i][1] === "k")) continue;
      if (a >= PFX[i][0]) return +(v / PFX[i][0]).toPrecision(4) + " " + PFX[i][1] + sym;
    }
    return v + " " + sym;
  }
  J.fmt = fmt;
  // CSP forbids inline style attributes: position gauge ticks from script whenever they appear.
  function placeTicks(root) { (root.querySelectorAll ? root : document).querySelectorAll(".g-tick[data-pos]").forEach(function (t) { t.style.left = t.dataset.pos + "%"; t.removeAttribute("data-pos"); }); }
  new MutationObserver(function (ms) { ms.forEach(function (m) { m.addedNodes.forEach(function (n) { if (n.nodeType === 1) placeTicks(n); }); }); })
    .observe(document.body, { childList: true, subtree: true });
  J.patternsBlock = function (pats) {
    if (!pats || !pats.length) return "";
    return '<h3 class="section-h">Verified patterns · ' + pats.length + '</h3><div class="cards">' + pats.map(function (p) {
      return '<article class="card pattern p-verified"><h4>' + esc(p.title) + '</h4><p class="hint">' + p.cases.length + " cases · matched: " +
        esc((p.matched || []).join(", ")) + "</p><ul>" + p.cases.map(function (c) { return "<li>" + esc(c.serial) + " → " + esc(c.root_cause) + " " + J.chip(c.ref) + "</li>"; }).join("") + "</ul></article>";
    }).join("") + "</div>";
  };
  function confirmBox(msg, yes) {
    return new Promise(function (resolve) {
      var d = $("dlg-confirm"); $("confirm-msg").textContent = msg; $("confirm-yes").firstChild.textContent = (yes || "Yes") + " ";
      function done(v) { d.close(); $("confirm-form").removeEventListener("submit", ok); $("confirm-no").removeEventListener("click", no); resolve(v); }
      function ok(e) { e.preventDefault(); done(true); }
      function no() { done(false); }
      $("confirm-form").addEventListener("submit", ok); $("confirm-no").addEventListener("click", no);
      d.addEventListener("cancel", function c() { d.removeEventListener("cancel", c); done(false); });
      d.showModal(); $("confirm-yes").focus();
    });
  }
  J.confirmBox = confirmBox;
  function store(k, v) { try { if (v === undefined) return JSON.parse(localStorage.getItem(k) || "null"); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, JSON.stringify(v)); } catch (e) { return null; } }

  // ------------------------------------------------------------ range flag + gauge
  function gauge(v, lo, hi) {
    // Small horizontal gauge: the range band in the middle 60 %, the reading as a tick. Clamped at the ends.
    if (lo === null && hi === null) return "";
    var a = lo !== null ? lo : hi * 0.5, b = hi !== null ? hi : lo * 1.5;
    var span = (b - a) || Math.abs(a) || 1, min = a - span * 0.33, max = b + span * 0.33;
    var pos = Math.max(0, Math.min(100, (v - min) / (max - min) * 100));
    var out = v < a || v > b;
    return '<span class="gauge' + (out ? " out" : "") + '" role="img" aria-label="Reading ' + (out ? "outside" : "inside") +
      ' range"><span class="g-band"></span><span class="g-tick" data-pos="' + pos.toFixed(1) + '"></span></span>';
  }
  function flag(chk, reading) {
    if (!chk) return "";
    var h = "";
    if (chk.status === "in" || chk.status === "out") {
      var rng = fmt(chk.min, chk.unit) + " – " + fmt(chk.max, chk.unit);
      h += '<span class="rflag rflag-' + chk.status + '" title="Range ' + esc(rng) + " · source: " + esc(chk.source) + '">' +
        (chk.status === "out" ? "OUT " : "in ") + esc(rng) + '</span><span class="rsrc">' + esc(chk.source) + "</span>" +
        gauge(reading.value, chk.min, chk.max);
    } else {
      h += '<span class="rflag rflag-none">no reference</span>';
    }
    if (chk.sample) {
      h += '<span class="rflag rflag-sample" title="Built from ' + chk.sample.n + " known-good samples on " + chk.sample.boards +
        ' board(s). Separate from your typed range.">' + (chk.sample.inside ? "" : "outside ") + "known-good " +
        esc(fmt(chk.sample.min, reading.unit)) + "–" + esc(fmt(chk.sample.max, reading.unit)) + " (n=" + chk.sample.n + ")</span>";
    }
    return h;
  }
  J.readingChip = function (e) {
    if (!e.reading) return "";
    var r = e.reading;
    return ' <span class="reading"><span class="rd">' + esc(r.test_point) + " = " + esc(e.reading_display || fmt(r.value, r.unit)) +
      " · " + esc(r.mode) + "</span>" + flag(e.check, r) + "</span>";
  };

  // ------------------------------------------------------------ quick-log preview chip
  var pv = { text: "", raw: false, t: null, seq: 0 };
  var KIND = /^([maor]):\s*/i;
  function previewNow() {
    var raw = $("ql-text").value, text = raw.replace(KIND, "").trim(), box = $("ql-preview");
    if (text !== pv.text) pv.raw = false;
    pv.text = text;
    if (!text || !S.active) { box.hidden = true; return; }
    var seq = ++pv.seq;
    api("/api/parse", { text: text }).then(function (d) {
      if (seq !== pv.seq) return;
      if (!d.reading) { box.hidden = true; pv.reading = null; return; }
      pv.reading = d.reading;
      var r = d.reading;
      box.className = "ql-preview" + (pv.raw ? " dropped" : "");
      box.innerHTML = pv.raw
        ? '<span>Will save as text only (no reading).</span> <button type="button" class="linkbtn" id="pv-undo">Use reading</button>'
        : '<span class="rd">Reading: <b>' + esc(r.test_point) + "</b> = <b>" + esc(d.display) + "</b> · " + esc(r.mode) + "</span>" +
          flag(d.check, r) + ' <button type="button" class="linkbtn" id="pv-drop" title="Garbled? Save the raw text only (Alt+X)">Wrong? text only <kbd>Alt+X</kbd></button>';
      box.hidden = false;
    }).catch(function () { box.hidden = true; });
  }
  $("ql-text").addEventListener("input", function () { clearTimeout(pv.t); pv.t = setTimeout(previewNow, 120); });
  $("ql-preview").addEventListener("click", function (e) {
    if (e.target.id === "pv-drop") { pv.raw = true; previewNow(); $("ql-text").focus(); }
    if (e.target.id === "pv-undo") { pv.raw = false; previewNow(); $("ql-text").focus(); }
  });
  document.addEventListener("keydown", function (e) {
    if (e.altKey && e.code === "KeyX" && !$("ql-preview").hidden) { e.preventDefault(); pv.raw = !pv.raw; previewNow(); }
  });
  J.beforeLog = function (text) {
    var x = { parse: !pv.raw };
    if (J.pendingPhotos && J.pendingPhotos.length) x.photos = J.pendingPhotos.slice();
    return x;
  };
  J.afterClear = function () {
    clearTimeout(pv.t); pv.seq++; // drop any in-flight preview for the line just saved
    pv.text = ""; pv.raw = false; pv.reading = null; $("ql-preview").hidden = true;
    if (J.clearPhotos) J.clearPhotos();
  };
  J.afterLog = function (d) {
    if (d.closeout_needed) openCloseout(d.entry.serial, d.entry.status);
    if (S.mode === "board") loadBoardPane();
  };

  // ------------------------------------------------------------ close-out card
  var CO_FIELDS = ["symptom", "root_cause", "fix", "parts", "outcome", "ticket"];
  var co = null;
  function fillCard(c) {
    CO_FIELDS.forEach(function (f) { $("co-" + f).value = c[f] || ""; });
    document.querySelectorAll('input[name="co-rcs"]').forEach(function (r) { r.checked = r.value === (c.root_cause_status || "suspected"); });
  }
  function readCard() {
    var c = {};
    CO_FIELDS.forEach(function (f) { c[f] = $("co-" + f).value.trim(); });
    var r = document.querySelector('input[name="co-rcs"]:checked');
    c.root_cause_status = r ? r.value : "suspected";
    return c;
  }
  function saveDraft() { if (co) store("jarvis.codraft." + co.serial, { serial: co.serial, status: co.status, card: readCard(), hyp: co.hyp }); }
  function openCloseout(serial, status) {
    var d = $("dlg-closeout");
    co = { serial: serial, status: status || "", hyp: null };
    $("co-serial").textContent = serial; $("co-status").textContent = status || "—"; $("co-err").hidden = true;
    $("co-rcs-hint").textContent = ""; $("co-hyp").hidden = true;
    var saved = store("jarvis.codraft." + serial);
    if (saved && saved.card) {
      fillCard(saved.card); co.status = saved.status || co.status; co.hyp = saved.hyp;
      $("co-status").textContent = co.status || "—";
      $("co-banner").textContent = "DRAFT — restored from your unsaved edits. Nothing is saved until you press Confirm.";
      d.showModal(); return;
    }
    fillCard({}); $("co-symptom").value = "Drafting from the log…";
    $("co-banner").textContent = "DRAFT — the brain is pre-filling this from the board's log. Edit, then confirm. Nothing is saved until you press Confirm.";
    d.showModal();
    J.busy(true);
    api("/api/closeout/draft", { serial: serial }).then(function (r) {
      if (r.error) { $("co-symptom").value = ""; $("co-err").textContent = "Brain pre-fill failed: " + r.error.message + " — fill the card by hand."; $("co-err").hidden = false; return; }
      co.status = co.status || r.closed_status || ""; $("co-status").textContent = co.status || "—";
      fillCard(r.draft);
      if (r.draft.brain_suggests_confirmed) $("co-rcs-hint").textContent = "The log shows a result after the fix; the brain suggests Confirmed. Your call.";
      renderHyp(r.hypotheses || []);
      saveDraft();
    }).catch(function (e) { $("co-err").textContent = e.message; $("co-err").hidden = false; })
      .then(function () { J.busy(false); });
  }
  J.openCloseout = openCloseout;
  function renderHyp(hs) {
    var box = $("co-hyp");
    if (!hs.length) { box.hidden = true; return; }
    var last = hs[hs.length - 1];
    co.hyp = co.hyp || { text: last.hypothesis, match: null };
    box.innerHTML = '<p class="hint">Your hypothesis before asking (' + esc(last.ts.slice(11, 16)) + '): <b>' + esc(last.hypothesis) +
      '</b></p><div class="row"><span class="co-label">Did it match the root cause?</span>' +
      '<label class="toggle"><input type="radio" name="co-hm" value="yes"> <span>Yes</span></label>' +
      '<label class="toggle"><input type="radio" name="co-hm" value="no"> <span>No</span></label></div>';
    box.hidden = false;
    box.querySelectorAll('input[name="co-hm"]').forEach(function (r) {
      if ((co.hyp.match === true && r.value === "yes") || (co.hyp.match === false && r.value === "no")) r.checked = true;
      r.addEventListener("change", function () { co.hyp.match = r.value === "yes"; saveDraft(); });
    });
  }
  $("closeout-form").addEventListener("input", saveDraft);
  $("co-cancel").addEventListener("click", function () { saveDraft(); $("dlg-closeout").close(); J.toast("Close-out kept as a draft (not saved). Board view → Close out… to finish."); });
  $("closeout-form").addEventListener("submit", function (e) {
    e.preventDefault();
    var card = readCard();
    if (!card.symptom || !card.root_cause) { $("co-err").textContent = "Symptom and root cause are required."; $("co-err").hidden = false; return; }
    $("co-confirm").disabled = true;
    api("/api/closeout/confirm", { serial: co.serial, closed_status: co.status || null, card: card, hypothesis: co.hyp })
      .then(function () {
        store("jarvis.codraft." + co.serial, null);
        $("dlg-closeout").close(); J.toast("Close-out saved for " + co.serial + " (root cause " + card.root_cause_status + ").");
        if (S.mode === "board") loadBoardPane(); if (S.mode === "patterns") loadPatterns();
      })
      .catch(function (err) { $("co-err").textContent = err.message; $("co-err").hidden = false; })
      .then(function () { $("co-confirm").disabled = false; });
  });

  // ------------------------------------------------------------ board pane
  function loadBoardPane() {
    var a = S.active;
    if (!a) { $("board-pane-id").textContent = "No active board."; $("timeline").innerHTML = ""; $("board-closeouts").innerHTML = ""; $("refview").innerHTML = ""; return; }
    $("board-pane-id").textContent = a.board_type + (a.rev ? " rev " + a.rev : "") + " · " + a.serial + (a.ticket ? " · " + a.ticket : "") +
      (store("jarvis.codraft." + a.serial) ? " · close-out draft pending" : "");
    api("/api/timeline?serial=" + encodeURIComponent(a.serial)).then(function (d) {
      var h = "", lastDay = "";
      d.entries.forEach(function (e) {
        var day = e.ts.slice(0, 10);
        if (day !== lastDay) { h += '<li class="tl-day">' + esc(day) + "</li>"; lastDay = day; }
        h += '<li class="tl-entry' + (e.check && e.check.status === "out" ? " tl-out" : "") + '"><span class="ts">' + esc(e.ts.slice(11, 16)) +
          '</span><span class="kind">' + esc(e.kind || "") + "</span><span>" + esc(e.text) + J.readingChip(e) +
          (J.photoThumbs ? J.photoThumbs(e) : "") + "</span>" + J.badge(e.status) + "</li>";
      });
      $("timeline").innerHTML = h || '<li class="hint">No entries for this board yet.</li>';
      $("board-closeouts").innerHTML = d.closeouts.length ? d.closeouts.map(coCard).join("") : '<p class="hint">None yet.</p>';
    });
    api("/api/reference").then(renderRef);
  }
  function coCard(c) {
    return '<article class="card"><dl><dt>Closed</dt><dd>' + esc(c.ts.slice(0, 16).replace("T", " ")) + " · " + J.badge(c.closed_status) + "</dd>" +
      "<dt>Symptom</dt><dd>" + esc(c.symptom) + "</dd><dt>Root cause</dt><dd>" + esc(c.root_cause) +
      ' <span class="badge badge-' + (c.root_cause_status === "confirmed" ? "fixed" : "open") + '">' + esc(c.root_cause_status) + "</span></dd>" +
      "<dt>Fix</dt><dd>" + esc(c.fix || "—") + "</dd><dt>Parts</dt><dd>" + esc(c.parts || "—") + "</dd>" +
      "<dt>Outcome</dt><dd>" + esc(c.outcome || "—") + "</dd>" + (c.ticket ? "<dt>Ticket</dt><dd>" + esc(c.ticket) + "</dd>" : "") +
      (c.hypothesis ? "<dt>Hypothesis</dt><dd>" + esc(c.hypothesis) + " · " + (c.hypothesis_match === true ? "matched" : c.hypothesis_match === false ? "did not match" : "not rated") + "</dd>" : "") +
      "</dl>" + (J.handoffButton ? J.handoffButton(c) : "") + "</article>";
  }
  J.coCard = coCard;
  function renderRef(o) {
    var h = '<p class="hint">Typed ranges: <code>jarvis/reference/' + esc(o.expected_file) + "</code>" +
      (o.draft ? " · candidates with doc values (min/max blank, not used for checks): <code>jarvis/reference/" + esc(o.draft) + "</code>" : "") + "</p>";
    if (o.conflicts.length) {
      h += '<div class="block gaps"><div class="block-h"><h3>⚠ Reference disagrees with the docs</h3></div><ul>' + o.conflicts.map(function (c) {
        return "<li><b>" + esc(c.test_point) + "</b> your range " + esc(fmt(c.min, unitOf(c.mode))) + "–" + esc(fmt(c.max, unitOf(c.mode))) + " " +
          J.chip("jarvis/reference/" + c.ref) + " vs docs: “" + esc(c.doc_text.slice(0, 140)) + "” " + J.chip(c.doc) + "</li>";
      }).join("") + "</ul></div>";
    }
    h += "<table><thead><tr><th>Test point</th><th>Mode</th><th>Your range</th><th>Source</th><th>Known-good samples</th></tr></thead><tbody>";
    var rows = {};
    o.ranges.forEach(function (r) { rows[r.test_point + "|" + r.mode] = { r: r }; });
    o.samples.forEach(function (s) { (rows[s.test_point + "|" + s.mode] = rows[s.test_point + "|" + s.mode] || {}).s = s; });
    var keys = Object.keys(rows).sort();
    keys.forEach(function (k) {
      var r = rows[k].r, s = rows[k].s, tp = k.split("|");
      h += "<tr><td>" + esc(tp[0]) + "</td><td>" + esc(tp[1]) + "</td><td>" + (r ? esc(fmt(r.min, unitOf(r.mode)) + " – " + fmt(r.max, unitOf(r.mode))) : "—") +
        "</td><td>" + (r ? esc(r.source || r.file) : "") + "</td><td>" + (s ? esc(fmt(s.min, s.unit) + " – " + fmt(s.max, s.unit)) + " (n=" + s.n + ", " + s.serials.length + " board)" : "—") + "</td></tr>";
    });
    h += "</tbody></table>" + (keys.length ? "" : '<p class="hint">No ranges typed and no known-good samples yet.</p>');
    $("refview").innerHTML = h;
  }
  function unitOf(mode) { return { dcv: "V", acv: "V", diode: "V", resistance: "ohm", current: "A", frequency: "Hz", capacitance: "F" }[mode] || ""; }
  $("btn-closeout").addEventListener("click", function () { if (S.active) openCloseout(S.active.serial, ""); });
  $("btn-knowngood").addEventListener("click", function () {
    var a = S.active; if (!a) return;
    confirmBox("Mark " + a.board_type + (a.rev ? " rev " + a.rev : "") + " " + a.serial + " known-good? Every parsed reading logged for this board is saved as a known-good sample. Your typed ranges are not changed.", "Mark known-good")
      .then(function (ok) {
        if (!ok) return;
        api("/api/reference/known-good", { serial: a.serial }).then(function (d) {
          J.toast(d.added ? d.added + " readings saved as known-good samples." : "No new readings to save for this board.", !d.added);
          loadBoardPane();
        }).catch(function (e) { J.toast(e.message, true); });
      });
  });

  // ------------------------------------------------------------ patterns pane
  function loadPatterns() {
    api("/api/patterns").then(function (d) {
      var h = d.patterns.length ? "" : '<p class="hint">No pattern yet. A pattern appears when 3 or more confirmed close-outs match.</p>';
      d.patterns.forEach(function (p) {
        h += '<article class="card pattern p-' + esc(p.status) + '"><h3>' + esc(p.title) + ' <span class="badge badge-' +
          (p.status === "verified" ? "fixed" : p.status === "dismissed" ? "scrap" : "open") + '">' + esc(p.status) + "</span></h3>" +
          '<p class="hint">' + p.cases.length + " cases · " + p.confirmed_root_causes + " with confirmed root cause</p><ul>" +
          p.cases.map(function (c) { return "<li>" + esc(c.serial) + " · " + esc(c.symptom) + " → " + esc(c.root_cause) + " (" + esc(c.root_cause_status) + ") " + J.chip(c.ref) + "</li>"; }).join("") +
          '</ul><div class="row">' +
          (p.status !== "verified" ? '<button type="button" class="btn" data-pat="' + p.id + '" data-st="verified">Verify</button>' : "") +
          (p.status !== "dismissed" ? '<button type="button" class="btn" data-pat="' + p.id + '" data-st="dismissed">Dismiss</button>' : "") +
          (p.status !== "new" ? '<button type="button" class="btn" data-pat="' + p.id + '" data-st="new">Reset</button>' : "") +
          (J.wiButton ? J.wiButton(p) : "") + "</div></article>";
      });
      $("patterns-out").innerHTML = h;
    });
  }
  $("patterns-out").addEventListener("click", function (e) {
    var b = e.target.closest("[data-pat]"); if (!b) return;
    api("/api/patterns", { id: b.dataset.pat, status: b.dataset.st }).then(loadPatterns).catch(function (err) { J.toast(err.message, true); });
  });
  J.loadPatterns = loadPatterns;
  J.loadBoardPane = loadBoardPane;

  J.onMode = function (m) {
    if (m === "board") loadBoardPane();
    if (m === "patterns") loadPatterns();
    if (J.onMode2) J.onMode2(m);
  };
  J.onBoard = function () { if (S.mode === "board") loadBoardPane(); if (J.onBoard2) J.onBoard2(); };
})();
