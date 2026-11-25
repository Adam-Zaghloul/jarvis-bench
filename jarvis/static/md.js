// Minimal, safe markdown renderer for JARVIS. Escapes all HTML first.
// Each block element gets data-l1/data-l2 (1-based source lines) so the
// source viewer can highlight a cited line range or heading section.
// Citations [[path#...]] become chips via the `cite` callback.
(function (global) {
  "use strict";

  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function inline(s, opt) {
    // Protect code spans first.
    var codes = [];
    s = s.replace(/`([^`]+)`/g, function (_, c) { codes.push(c); return "\u0000" + (codes.length - 1) + "\u0000"; });
    var cites = [];
    s = s.replace(/\[\[([^\]\n]{1,300})\]\]/g, function (_, c) { cites.push(c); return "\u0001" + (cites.length - 1) + "\u0001"; });
    s = esc(s);
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g, "$1<em>$2</em>");
    s = s.replace(/(^|[^\w])_([^_\n]+)_(?!\w)/g, "$1<em>$2</em>");
    // Links: only relative or anchor links; never external (offline app).
    s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, function (_, t, href) {
      if (/^[a-z]+:/i.test(href)) return t;
      return '<a href="#" class="doclink" data-path="' + href + '">' + t + "</a>";
    });
    s = s.replace(/\u0000(\d+)\u0000/g, function (_, i) { return "<code>" + esc(codes[+i]) + "</code>"; });
    s = s.replace(/\u0001(\d+)\u0001/g, function (_, i) {
      return opt && opt.cite ? opt.cite(cites[+i]) : "[[" + esc(cites[+i]) + "]]";
    });
    s = s.replace(/⚡ ?POWER ON/g, '<span class="flag flag-power">⚡ POWER ON</span>');
    s = s.replace(/⚠ ?DESTRUCTIVE/g, '<span class="flag flag-destructive">⚠ DESTRUCTIVE</span>');
    return s;
  }

  function attrs(a, b) { return ' data-l1="' + a + '" data-l2="' + b + '"'; }

  function render(src, opt) {
    opt = opt || {};
    var lines = String(src || "").replace(/\r\n?/g, "\n").split("\n");
    var out = [], i = 0, n = lines.length;

    function isBlockStart(l) {
      return /^\s*$/.test(l) || /^#{1,6}\s/.test(l) || /^```/.test(l) || /^\s*([-*+]|\d+[.)])\s+/.test(l) ||
             /^>\s?/.test(l) || /^(\*\s*\*\s*\*|-\s*-\s*-|_\s*_\s*_)[\s*_-]*$/.test(l) || /^\|/.test(l);
    }

    while (i < n) {
      var l = lines[i];
      if (/^\s*$/.test(l)) { i++; continue; }
      var start = i + 1, m;
      if ((m = /^(#{1,6})\s+(.*)$/.exec(l))) {
        var lvl = m[1].length, text = m[2].replace(/\s*#+\s*$/, "");
        out.push("<h" + lvl + attrs(start, start) + ' data-heading="' + esc(text) + '">' + inline(text, opt) + "</h" + lvl + ">");
        i++; continue;
      }
      if (/^```/.test(l)) {
        var buf = []; i++;
        while (i < n && !/^```/.test(lines[i])) { buf.push(lines[i]); i++; }
        i++;
        out.push("<pre" + attrs(start, i) + "><code>" + esc(buf.join("\n")) + "</code></pre>");
        continue;
      }
      if (/^(\*\s*\*\s*\*|-\s*-\s*-|_\s*_\s*_)[\s*_-]*$/.test(l)) { out.push("<hr" + attrs(start, start) + ">"); i++; continue; }
      if (/^\|/.test(l) && i + 1 < n && /^\|?\s*:?-{2,}/.test(lines[i + 1])) {
        var row = function (r) { return r.replace(/^\|/, "").replace(/\|\s*$/, "").split("|").map(function (c) { return c.trim(); }); };
        var head = row(l); i += 2;
        var html = '<div class="tablewrap"' + attrs(start, start) + "><table><thead><tr>" +
                   head.map(function (h) { return "<th>" + inline(h, opt) + "</th>"; }).join("") + "</tr></thead><tbody>";
        while (i < n && /^\|/.test(lines[i])) {
          html += "<tr" + attrs(i + 1, i + 1) + ">" + row(lines[i]).map(function (c) { return "<td>" + inline(c, opt) + "</td>"; }).join("") + "</tr>";
          i++;
        }
        html += "</tbody></table></div>";
        out.push(html.replace(attrs(start, start), attrs(start, i)));
        continue;
      }
      if (/^>\s?/.test(l)) {
        var q = [];
        while (i < n && /^>\s?/.test(lines[i])) { q.push(lines[i].replace(/^>\s?/, "")); i++; }
        out.push("<blockquote" + attrs(start, i) + ">" + render(q.join("\n"), opt) + "</blockquote>");
        continue;
      }
      if ((m = /^(\s*)([-*+]|\d+[.)])\s+/.exec(l))) {
        var ordered = /\d/.test(m[2]);
        var items = [], cur = null;
        var baseIndent = m[1].length;
        while (i < n) {
          var li = lines[i], mm = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/.exec(li);
          if (mm && mm[1].length <= baseIndent + 1) {
            cur = { l1: i + 1, l2: i + 1, text: [mm[3]], sub: [] }; items.push(cur); i++;
          } else if (cur && /^\s+\S/.test(li)) {
            (mm ? cur.sub : (cur.sub.length ? cur.sub : cur.text)).push(mm ? li : li.trim());
            if (mm) { /* nested list line */ }
            cur.l2 = i + 1; i++;
          } else break;
        }
        var tag = ordered ? "ol" : "ul";
        out.push("<" + tag + attrs(start, i) + ">" + items.map(function (it) {
          var sub = it.sub.length ? render(it.sub.map(function (s) { return s.replace(/^\s{2,4}/, ""); }).join("\n"), opt) : "";
          var t = it.text.join(" ").replace(/^\[( |x|X)\]\s+/, function (_, c) { return c.trim() ? "☑ " : "☐ "; });
          return "<li" + attrs(it.l1, it.l2) + ">" + inline(t, opt) + sub + "</li>";
        }).join("") + "</" + tag + ">");
        continue;
      }
      var p = [l]; i++;
      while (i < n && !isBlockStart(lines[i])) { p.push(lines[i]); i++; }
      out.push("<p" + attrs(start, i) + ">" + inline(p.join("\n"), opt).replace(/\n/g, " ") + "</p>");
    }
    return out.join("\n");
  }

  global.JMD = { render: render, esc: esc, inline: inline };
})(window);
