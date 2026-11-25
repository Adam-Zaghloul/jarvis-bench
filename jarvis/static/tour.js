// JARVIS narrated tour: captions on screen, voiceover from static/tour/<id>.m4a.
// Text is set with textContent only. The audio plays when the user presses Play (a click is needed for sound).
(function () {
  "use strict";

  var FALLBACK_MS = 8000;      // captions advance this long when the audio can't load
  var scenes = [];
  var idx = 0;
  var playing = false;
  var timer = null;
  var audio = document.getElementById("tour-audio");
  var $ = function (id) { return document.getElementById(id); };

  function clearTimer() { if (timer) { clearTimeout(timer); timer = null; } }

  function show(i) {
    idx = Math.max(0, Math.min(scenes.length - 1, i));
    var s = scenes[idx];
    $("tour-title").textContent = s.title;
    var list = $("tour-caption");
    list.textContent = "";
    s.caption.forEach(function (line) {
      var li = document.createElement("li");
      li.textContent = line;
      list.appendChild(li);
    });
    $("tour-count").textContent = (idx + 1) + " / " + scenes.length;
    $("tour-prev").disabled = idx === 0;
    $("tour-next").disabled = idx === scenes.length - 1;
    if (playing) { speak(s); }
  }

  function speak(s) {
    clearTimer();
    audio.onerror = function () { audio.onerror = null; $("tour-warn").hidden = false; schedule(); };
    audio.onended = function () { advance(); };
    audio.src = "/static/tour/" + s.id + ".m4a";
    var p = audio.play();
    if (p && p.catch) { p.catch(function () { $("tour-warn").hidden = false; schedule(); }); }
  }

  function schedule() {
    clearTimer();
    timer = setTimeout(advance, FALLBACK_MS);
  }

  function advance() {
    if (!playing) { return; }
    if (idx >= scenes.length - 1) { stop(); return; }
    show(idx + 1);
  }

  function stop() {
    playing = false;
    clearTimer();
    audio.pause();
    $("tour-play").textContent = "Play tour";
  }

  function play() {
    playing = true;
    $("tour-play").textContent = "Pause";
    speak(scenes[idx]);
  }

  function toggle() { if (playing) { stop(); } else { play(); } }

  $("tour-play").addEventListener("click", toggle);
  $("tour-prev").addEventListener("click", function () { show(idx - 1); });
  $("tour-next").addEventListener("click", function () { show(idx + 1); });
  document.addEventListener("keydown", function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey) { return; }
    if (e.key === " ") {
      if (e.target && e.target.tagName === "BUTTON") { return; }   // a focused button handles Space itself
      e.preventDefault(); toggle();
    }
    else if (e.key === "ArrowRight") { show(idx + 1); }
    else if (e.key === "ArrowLeft") { show(idx - 1); }
  });

  fetch("/static/tour/scenes.json", { cache: "no-store" })
    .then(function (r) { if (!r.ok) { throw new Error("HTTP " + r.status); } return r.json(); })
    .then(function (data) { scenes = data; show(0); })
    .catch(function () { $("tour-title").textContent = "The tour couldn't load its scene list."; });
}());
