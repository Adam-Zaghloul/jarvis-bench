// JARVIS V2 Phase 5 — scanner anywhere on the page, photos pasted/dropped into the log line.
(function () {
  "use strict";
  var J = window.J, $ = J.$, esc = J.esc, api = J.api, S = J.S;

  // ------------------------------------------------------------ barcode / QR scanner (keyboard wedge)
  var det = new window.ScanDetector();
  var snap = null; // the focused field's value just before the current fast burst began
  document.addEventListener("keydown", function (e) {
    if (e.target && e.target.id === "bd-serial") return;            // typing/scanning into the serial box itself
    if (document.querySelector("dialog[open]")) { det.reset(); return; }
    var tgt = e.target, field = tgt && (tgt.tagName === "INPUT" || tgt.tagName === "TEXTAREA") ? tgt : null;
    var r = det.feed(e.key, e.timeStamp || performance.now(), { ctrl: e.ctrlKey, meta: e.metaKey, alt: e.altKey });
    if (r && r.scan) {
      e.preventDefault(); e.stopImmediatePropagation();               // the scanner's Enter must not submit anything
      if (snap && snap.el.value !== snap.value) snap.el.value = snap.value; // take the scanned characters back out
      snap = null;
      askSwitch(r.scan);
      return;
    }
    // keydown fires before the character is inserted: snapshot when a new burst starts.
    if (det.buf.length === 1) snap = field ? { el: field, value: field.value } : null;
    else if (!det.buf.length) snap = null;
  }, true);
  J.scanDetector = det;

  function askSwitch(serial) {
    if (S.active && S.active.serial === serial) { J.toast("Scanned " + serial + ": already the active board."); return; }
    J.openBoardDialog();
    $("dlg-board").dataset.via = "scan";
    $("dlg-board-title").textContent = "Scanned: switch to board " + serial + "?";
    $("bd-serial").value = serial;
    $("bd-ticket").value = "";
    var btn = $("board-form").querySelector('button[type="submit"]');
    btn.innerHTML = "Switch <kbd>Enter</kbd>";
    setTimeout(function () { btn.focus(); }, 0);
    $("dlg-board").addEventListener("close", function f() {
      $("dlg-board").removeEventListener("close", f);
      delete $("dlg-board").dataset.via;
      $("dlg-board-title").textContent = "Switch active board"; btn.textContent = "Switch";
    });
  }
  J.askSwitch = askSwitch;

  // ------------------------------------------------------------ photos: paste or drop into the log line
  J.pendingPhotos = [];
  function renderPending() {
    var box = $("ql-photos");
    if (!J.pendingPhotos.length) { box.hidden = true; box.innerHTML = ""; return; }
    box.hidden = false;
    box.innerHTML = J.pendingPhotos.map(function (p, i) {
      return '<span class="ph-chip"><img alt="Photo ' + (i + 1) + '" src="/api/raw?path=' + encodeURIComponent(p) + '"><button type="button" class="linkbtn" data-unph="' + i + '" aria-label="Remove photo">✕</button></span>';
    }).join("") + '<span class="hint">attached to the next entry · location data stripped</span>';
  }
  $("ql-photos").addEventListener("click", function (e) {
    var b = e.target.closest("[data-unph]"); if (!b) return;
    J.pendingPhotos.splice(+b.dataset.unph, 1); renderPending(); $("ql-text").focus();
  });
  J.clearPhotos = function () { J.pendingPhotos = []; renderPending(); };

  function reencode(file) {
    // Canvas re-encode drops every metadata block (EXIF, GPS). The server strips again on save.
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file), img = new Image();
      img.onload = function () {
        var max = 2400, w = img.naturalWidth, h = img.naturalHeight, k = Math.min(1, max / Math.max(w, h));
        var c = document.createElement("canvas"); c.width = Math.round(w * k); c.height = Math.round(h * k);
        c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        resolve(c.toDataURL("image/jpeg", 0.88));
      };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error("Not an image the browser can read.")); };
      img.src = url;
    });
  }
  function addFiles(files) {
    var imgs = Array.prototype.filter.call(files || [], function (f) { return /^image\//.test(f.type); });
    if (!imgs.length) return false;
    if (!S.active) { J.toast("Set the active board before adding photos.", true); return true; }
    imgs.forEach(function (f) {
      reencode(f).then(function (data) { return api("/api/photo", { data: data }); })
        .then(function (d) { J.pendingPhotos.push(d.path); renderPending(); $("ql-text").focus(); })
        .catch(function (err) { J.toast("Photo not saved: " + err.message, true); });
    });
    return true;
  }
  J.addPhotoFiles = addFiles;
  $("ql-text").addEventListener("paste", function (e) {
    var items = e.clipboardData && e.clipboardData.files;
    if (items && items.length && addFiles(items)) e.preventDefault();
  });
  var ql = $("quicklog");
  ["dragenter", "dragover"].forEach(function (ev) { ql.addEventListener(ev, function (e) { if (e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types, "Files") >= 0) { e.preventDefault(); ql.classList.add("drop"); } }); });
  ["dragleave", "drop"].forEach(function (ev) { ql.addEventListener(ev, function () { ql.classList.remove("drop"); }); });
  ql.addEventListener("drop", function (e) { if (e.dataTransfer && addFiles(e.dataTransfer.files)) e.preventDefault(); });

  J.photoThumbs = function (e) {
    if (!e.photos || !e.photos.length) return "";
    return ' <span class="ph-row">' + e.photos.map(function (p) {
      return '<button type="button" class="ph-thumb" data-open="' + esc(p) + '" title="' + esc(p) + '"><img alt="Bench photo" src="/api/raw?path=' + encodeURIComponent(p) + '"></button>';
    }).join("") + "</span>";
  };
})();
