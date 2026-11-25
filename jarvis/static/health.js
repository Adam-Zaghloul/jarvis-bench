// JARVIS V2 Phase 6 — Health view: backup status, weekly usage, doc audit (report only).
(function () {
  "use strict";
  var J = window.J, $ = J.$, esc = J.esc, api = J.api;

  function ago(days) { return days === 0 ? "today" : days === 1 ? "yesterday" : days + " days ago"; }
  J.backupAgo = function (b) { return !b || !b.last ? "never" : ago(b.age_days); };

  function renderBackup(b) {
    var h = '<div class="summary' + (b.stale ? " warn" : "") + '"><span class="big">' + esc(J.backupAgo(b)) + "</span>last backup";
    h += b.dest ? " · folder <code>" + esc(b.dest) + "</code>" : " · no folder set yet";
    h += "</div>";
    h += '<p class="hint">Run <code>sh jarvis.sh backup</code> in Terminal' + (b.dest ? "" : " (it asks for the folder once; pick a USB drive, not a synced cloud folder)") +
      ". It copies logs, photos, debriefs, reference, evals, drafts and settings and keeps the newest 10 copies." +
      (b.stale ? (b.last ? " <b>Over " + b.stale_days + " days old: back up today.</b>" : " <b>No backup yet: run one today.</b>") : "") + "</p>";
    $("hl-backup").innerHTML = h;
  }

  function renderUsage(u) {
    var h = '<div class="summary"><span class="big">' + u.entries + "</span>entries · " + u.boards + " boards · " +
      u.questions + " questions · " + u.seen + " Seen-before runs · " + u.debriefs + " debriefs · 👍 " + u.thumbs_up + " / 👎 " + u.thumbs_down +
      (u.thumbs_ratio !== null ? " (" + Math.round(u.thumbs_ratio * 100) + "% 👍)" : "") + "</div>";
    h += '<div class="tablewrap"><table><thead><tr><th>Feature</th><th>Uses</th></tr></thead><tbody>' +
      u.features.map(function (f) { return "<tr" + (f.count ? "" : ' class="muted-row"') + "><td>" + esc(f.label) + "</td><td>" + f.count + "</td></tr>"; }).join("") +
      "</tbody></table></div>";
    h += u.unused.length ? '<p class="hint">Not used in ' + esc(u.week) + ": " + esc(u.unused.join(", ")) + ".</p>" : '<p class="hint">Every feature was used this week.</p>';
    $("hl-usage").innerHTML = h;
  }

  function loc(x) { return J.chip(x.path + "#L" + x.line); }
  function renderAudit(a) {
    var h = '<div class="summary"><span class="big">' + (a.broken_links.length + a.missing_paths.length) + "</span>broken references · " +
      a.uncited_count + " of " + a.docs + " docs not cited in 30 days</div>";
    h += "<h4>Broken links</h4>" + (a.broken_links.length ? "<ul>" + a.broken_links.map(function (b) {
      return "<li>" + loc(b) + " → <code>" + esc(b.target) + "</code></li>"; }).join("") + "</ul>" : '<p class="hint">None.</p>');
    h += "<h4>References to missing folders or files</h4>" + (a.missing_paths.length ? "<ul>" + a.missing_paths.map(function (m) {
      return "<li>" + loc(m) + " <code>" + esc(m.ref) + "</code>: " + esc(m.why) + "</li>"; }).join("") + "</ul>" : '<p class="hint">None.</p>');
    h += "<h4>Not cited by the brain in 30 days</h4>";
    h += '<p class="hint">' + (a.citations_since ? "Citation tracking started " + esc(a.citations_since) +
      (a.tracking_days < 30 ? " (" + a.tracking_days + " days ago, so this list is still settling)" : "") + "."
      : "No citations recorded yet: Ask and Seen before record which files they cite from now on.") + "</p>";
    var cls = Object.keys(a.uncited);
    h += cls.length ? cls.map(function (c) {
      return "<details><summary>" + esc(c) + " (" + a.uncited[c].length + ")</summary><ul>" +
        a.uncited[c].map(function (p) { return "<li>" + J.chip(p) + "</li>"; }).join("") + "</ul></details>"; }).join("") : '<p class="hint">Every doc was cited.</p>';
    h += "<h4>Oldest files (last modified)</h4><ul>" + a.oldest.map(function (o) {
      return "<li>" + J.chip(o.path) + " " + esc(o.modified) + " (" + o.days + " days)</li>"; }).join("") + "</ul>";
    $("hl-audit").innerHTML = h;
  }

  function load() {
    api("/api/backup").then(renderBackup).catch(function (e) { $("hl-backup").textContent = e.message; });
    loadUsage();
    $("hl-audit").innerHTML = '<p class="working">Checking links…</p>';
    api("/api/audit").then(renderAudit).catch(function (e) { $("hl-audit").textContent = e.message; });
  }
  function loadUsage() {
    api("/api/usage?week=" + encodeURIComponent($("hl-week").value)).then(renderUsage)
      .catch(function (e) { $("hl-usage").textContent = e.message; });
  }
  $("hl-week").value = J.isoWeek(new Date());
  $("hl-week").addEventListener("change", loadUsage);

  var prevMode = J.onMode2;
  J.onMode2 = function (m) { if (m === "health") load(); if (prevMode) prevMode(m); };
})();
