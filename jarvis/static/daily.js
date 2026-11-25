// JARVIS V2 Phase 4 — daily work: time-on-board, escalation handoff, weekly review, work-instruction drafts.
(function () {
  "use strict";
  var J = window.J, $ = J.$, esc = J.esc, api = J.api, S = J.S;

  // ------------------------------------------------------------ time on board (board bar)
  function refreshTob() {
    var a = S.active;
    if (!a) return;
    api("/api/tob?serial=" + encodeURIComponent(a.serial)).then(function (d) {
      if (!S.active || S.active.serial !== d.serial) return;
      $("board-meta").textContent = [a.ticket, d.seconds ? "⏱ " + d.display + " on board" : ""].filter(Boolean).join(" · ");
      $("board-meta").title = "First to last entry, gaps over 30 min excluded.";
    });
  }
  var prevBoard = J.onBoard2;
  J.onBoard2 = function () { refreshTob(); if (prevBoard) prevBoard(); };
  var prevAfterLog = J.afterLog;
  J.afterLog = function (d) { prevAfterLog(d); refreshTob(); };
  setInterval(refreshTob, 60000);

  // ------------------------------------------------------------ escalation handoff
  J.handoffButton = function (c) {
    if (c.closed_status !== "escalated") return "";
    return '<div class="row"><button type="button" class="btn" data-handoff="' + esc(c.serial) + '">Escalation handoff note</button></div><div class="handoff-out"></div>';
  };
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-handoff]"); if (!b) return;
    var out = b.parentNode.nextElementSibling;
    out.innerHTML = '<p class="working">Drafting the handoff note…</p>'; b.disabled = true; J.busy(true);
    api("/api/handoff", { serial: b.dataset.handoff }).then(function (d) {
      if (d.error) { out.innerHTML = '<p class="err">' + esc(d.error.message) + "</p>"; return; }
      out.innerHTML = J.block("Handoff note · " + d.serial + " (copy only)", d.text);
    }).catch(function (err) { out.innerHTML = '<p class="err">' + esc(err.message) + "</p>"; })
      .then(function () { b.disabled = false; J.busy(false); });
  });

  // ------------------------------------------------------------ weekly review
  function isoWeek(d) {
    var t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    var day = t.getUTCDay() || 7; t.setUTCDate(t.getUTCDate() + 4 - day);
    var y0 = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
    return t.getUTCFullYear() + "-W" + String(Math.ceil(((t - y0) / 864e5 + 1) / 7)).padStart(2, "0");
  }
  J.isoWeek = isoWeek;
  $("wk").value = isoWeek(new Date());
  function loadSavedWeek() {
    api("/api/weekly?week=" + encodeURIComponent($("wk").value)).then(function (d) {
      if (S.wkBusy) return;
      $("wk-out").innerHTML = d.saved ? '<p class="hint">Saved review for ' + esc(d.week) + " (run again to regenerate):</p>" + J.block("week-" + d.week + ".md", d.saved) : "";
    });
  }
  $("wk").addEventListener("change", loadSavedWeek);
  $("btn-weekly").addEventListener("click", function () {
    var out = $("wk-out");
    out.innerHTML = '<p class="working">Counting the week and writing the competency log…</p>';
    S.wkBusy = true; J.busy(true); $("btn-weekly").disabled = true;
    api("/api/weekly", { week: $("wk").value }).then(function (d) {
      var st = d.stats, c = st.counts;
      var h = '<div class="summary"><span class="big">' + st.boards.length + "</span>boards · fixed " + c.fixed + " · escalated " + c.escalated +
        " · scrap " + c.scrap + " · open " + c.open + " · median time on board " + esc(fmtDur(st.median_seconds)) +
        (st.hit_rate.rated ? " · hypothesis hit rate " + st.hit_rate.pct + "% (" + st.hit_rate.matched + "/" + st.hit_rate.rated + ")" : "") + "</div>";
      h += '<div class="a">' + JMD.render(d.markdown, { cite: J.chip }) + "</div>";
      h += J.block("Weekly review " + d.week + " (copy)", d.markdown);
      if (d.dropped.length) h += '<p class="hint">⚠ ' + d.dropped.length + " competency item(s) removed for containing identifiers: " + esc(d.dropped.map(function (x) { return x.reason; }).join(", ")) + ".</p>";
      if (d.brain_error) h += '<p class="err">Competency log not written: ' + esc(d.brain_error.message) + "</p>";
      h += '<p class="hint">Saved to <code>' + esc(d.saved) + "</code></p>";
      out.innerHTML = h;
      checkNudge();
    }).catch(function (err) { out.innerHTML = '<p class="err">' + esc(err.message) + "</p>"; })
      .then(function () { S.wkBusy = false; J.busy(false); $("btn-weekly").disabled = false; });
  });
  function fmtDur(s) { if (!s && s !== 0) return "—"; var m = Math.round(s / 60); return m < 60 ? m + " min" : Math.floor(m / 60) + " h " + String(m % 60).padStart(2, "0") + " min"; }

  // Friday nudge: one line on the status bar, only if this week's review isn't saved yet.
  var nudge = false;
  function paintNudge(el) {
    var tag = $("nudge");
    if (nudge && !tag) {
      var sp = document.createElement("span"); sp.id = "nudge"; sp.className = "nudge";
      sp.textContent = (J.settings.voice ? " It's Friday. The weekly review is still to do (Alt+7)." : " · Friday: weekly review not run (Alt+7)");
      el.appendChild(sp);
    } else if (!nudge && tag) tag.remove();
  }
  var prevAfterStatus = J.afterStatus;
  J.afterStatus = function (el) { paintNudge(el); if (prevAfterStatus) prevAfterStatus(el); };
  function checkNudge() {
    api("/api/weekly").then(function (d) { nudge = !!d.nudge; paintNudge($("status-line")); });
  }
  J.checkNudge = checkNudge;
  setTimeout(checkNudge, 2500);

  // ------------------------------------------------------------ work-instruction draft (verified patterns)
  J.wiButton = function (p) {
    return p.status === "verified" ? '<button type="button" class="btn" data-wi="' + p.id + '">Work-instruction draft</button><div class="wi-out"></div>' : "";
  };
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-wi]"); if (!b) return;
    var out = b.nextElementSibling;
    out.innerHTML = '<p class="working">Drafting…</p>'; b.disabled = true; J.busy(true);
    api("/api/workinstruction", { pattern_id: b.dataset.wi }).then(function (d) {
      if (d.error) { out.innerHTML = '<p class="err">' + esc(d.error.message) + "</p>"; return; }
      out.innerHTML = '<p class="draft-banner">DRAFT saved to <code>' + esc(d.saved) + "</code>. It is not added to your docs.</p>" + J.block("Work-instruction DRAFT", d.text);
    }).catch(function (err) { out.innerHTML = '<p class="err">' + esc(err.message) + "</p>"; })
      .then(function () { b.disabled = false; J.busy(false); });
  });

  var prevMode = J.onMode2;
  J.onMode2 = function (m) { if (m === "review") loadSavedWeek(); if (prevMode) prevMode(m); };
})();
