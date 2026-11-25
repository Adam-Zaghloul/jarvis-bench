// JARVIS V2 Phase 2 — trust: feedback on every answer, predict-first hypothesis.
(function () {
  "use strict";
  var J = window.J, $ = J.$, esc = J.esc, api = J.api, S = J.S;

  // Troubleshooting = symptom or next-step language, or board context switched on. Documented in Build notes.
  var TROUBLE = /\b(not|never|no|won'?t|doesn'?t|fails?|failing|dead|stuck|short(ed)?|open|reads?|reading|measur\w*|check|next|start|why|fault|broken|wrong|missing|high|low|lock\w*|detect\w*)\b|\?\s*$/i;
  var LOOKUP = /^(what is|what's|which|where is|define|explain)\b(?!.*\b(check|next|start|fix)\b)/i;
  function isTroubleshooting(q, withCtx) { return !!withCtx || (TROUBLE.test(q) && !LOOKUP.test(q)); }
  J.isTroubleshooting = isTroubleshooting;

  J.onAskStart = function (o) {
    if (!J.settings.predict || !isTroubleshooting(o.question, o.withCtx)) return;
    o.ad.classList.add("held");
    o.ax.innerHTML = '<form class="hyp-form"><label for="hyp-' + (++J._hypN || (J._hypN = 1)) + '">Your hypothesis (optional) — the answer is held until you press Enter</label>' +
      '<div class="row"><input id="hyp-' + J._hypN + '" type="text" autocomplete="off" placeholder="e.g. R14 open on the LED_STATUS LED">' +
      '<button type="submit" class="btn btn-primary">Show answer <kbd>Enter</kbd></button></div><p class="hint hyp-state">Brain is working…</p></form>';
    var form = o.ax.querySelector("form"), inp = form.querySelector("input");
    setTimeout(function () { inp.focus(); }, 0);
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var h = inp.value.trim();
      var reveal = function () {
        o.ad.classList.remove("held");
        o.ax.innerHTML = h ? '<p class="hyp-saved">Your hypothesis: <b>' + esc(h) + "</b></p>" : '<p class="hint">No hypothesis given.</p>';
        if (o.ad._speak) o.ad._speak();
        $("ask-input").focus();
      };
      if (!h) return reveal();
      api("/api/hypothesis", { question: o.question, hypothesis: h, serial: S.active ? S.active.serial : null })
        .then(reveal).catch(function (err) { J.toast("Hypothesis not saved: " + err.message, true); reveal(); });
    });
    o.ad._held = true;
  };

  J.onAskDone = function (o) {
    o.ax = o.ax || o.ad.querySelector(".a-extra");
    if (o.ad.classList.contains("held")) {
      var st = o.ax.querySelector(".hyp-state"); if (st) st.textContent = "Answer ready. Press Enter to see it.";
      o.ad._speak = o.speak;
    } else {
      o.speak();
    }
    var fb = document.createElement("div"); fb.className = "feedback";
    fb.innerHTML = '<span class="hint">Was this right?</span>' +
      '<button type="button" class="btn btn-fb" data-r="up" aria-label="Good answer">👍</button>' +
      '<button type="button" class="btn btn-fb" data-r="down" aria-label="Bad answer">👎</button>' +
      '<form class="fb-reason" hidden><label class="sr">Reason</label><input type="text" placeholder="What was wrong? (optional)" autocomplete="off">' +
      '<button type="submit" class="btn">Save 👎</button></form>';
    o.ad.appendChild(fb);
    function send(rating, reason) {
      return api("/api/feedback", { rating: rating, reason: reason || "", question: o.question, answer: o.text, session_id: o.session_id })
        .then(function (d) {
          fb.innerHTML = '<span class="hint">' + (rating === "up" ? "👍 noted." : "👎 saved to " + esc(d.saved_to || "candidates") + " for the eval set.") + "</span>";
        }).catch(function (err) { J.toast(err.message, true); });
    }
    fb.addEventListener("click", function (e) {
      var b = e.target.closest("[data-r]"); if (!b) return;
      if (b.dataset.r === "up") return send("up");
      var f = fb.querySelector(".fb-reason"); f.hidden = false; f.querySelector("input").focus();
    });
    fb.querySelector(".fb-reason").addEventListener("submit", function (e) { e.preventDefault(); send("down", this.querySelector("input").value.trim()); });
  };
})();
