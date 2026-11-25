// Keyboard-wedge scanner detector. Pure logic: no DOM, so it runs in the browser and in Node tests.
// A scan = at least MIN_LEN printable characters, every gap between them under MAX_GAP_MS,
// ended by Enter or Tab within MAX_END_MS of the last character. Human typing (even fast bursts)
// has gaps well over 50 ms somewhere in 6+ characters, so it never qualifies.
// Keyboard-wedge scanners send keys well under 60 ms apart; 50 ms leaves margin.
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.ScanDetector = factory();
})(this, function () {
  "use strict";
  var DEFAULTS = { MIN_LEN: 6, MAX_GAP_MS: 50, MAX_END_MS: 100, MAX_LEN: 64, CHARSET: /^[A-Za-z0-9_\-]$/ };

  function ScanDetector(opts) {
    this.o = Object.assign({}, DEFAULTS, opts || {});
    this.reset();
  }
  ScanDetector.prototype.reset = function () { this.buf = ""; this.last = -1; this.start = -1; };
  // Feed one keydown. Returns {scan: "SERIAL"} when a scan completes, {inScan: true} while a fast burst is
  // building (≥ 2 fast chars), or null.
  ScanDetector.prototype.feed = function (key, t, mods) {
    var o = this.o;
    if (mods && (mods.ctrl || mods.meta || mods.alt)) { this.reset(); return null; }
    if (key === "Enter" || key === "Tab") {
      var ok = this.buf.length >= o.MIN_LEN && this.last >= 0 && (t - this.last) <= o.MAX_END_MS;
      var s = this.buf;
      this.reset();
      return ok ? { scan: s, chars: s.length } : null;
    }
    if (key && key.length === 1 && o.CHARSET.test(key)) {
      if (this.last < 0 || (t - this.last) > o.MAX_GAP_MS) { this.buf = ""; this.start = t; }
      this.buf += key;
      if (this.buf.length > o.MAX_LEN) this.reset();
      this.last = t;
      return this.buf.length >= 2 ? { inScan: true, chars: this.buf.length, started: this.start } : null;
    }
    if (key === "Shift") return null;  // scanners send Shift for capitals; it's not a gap
    this.reset();
    return null;
  };
  ScanDetector.DEFAULTS = DEFAULTS;
  return ScanDetector;
});
