/* Institution Finder: a small widget shared by both portals (no framework).
 *
 *   InstitutionFinder.mount(element, { hubUrl, onConfirm(result), onUnlisted(details) })
 *
 * Flow: type a name -> suggestions from the hub registry -> confirm card (details + map pin) -> "Yes".
 * Not sure? Answer a few guided questions. Not found? "My institution isn't listed".
 * The widget only SUGGESTS. The reporter makes the final choice by pressing "Yes".
 */
(function () {
  // Tiny DOM helper: h("div", {class: "x"}, "text", childNode). Text is inserted as text, never as HTML.
  function h(tag, attrs) {
    var el = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), attrs[k]);
      else if (k === "class") el.className = attrs[k];
      else if (attrs[k] !== undefined && attrs[k] !== null && attrs[k] !== false) el.setAttribute(k, attrs[k]);
    });
    for (var i = 2; i < arguments.length; i++) {
      var kid = arguments[i];
      if (kid === null || kid === undefined || kid === false) continue;
      el.appendChild(typeof kid === "object" ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }

  var GUIDED_FIELDS = [
    ["state", "State", "states"], ["district", "District", "districts"], ["type", "Type of institution", "types"],
    ["area", "Area", "areas"], ["program", "Programme offered", "programs"],
  ];

  function mount(root, opts) {
    var hub = opts.hubUrl.replace(/\/$/, "");
    var state = { mode: "search", query: "", result: null, picked: null, method: "REPORTER_CONFIRMED", answers: null,
                  guided: { picks: {}, data: null }, typed: { typed_name: "", district: "", state: "", details: "" } };
    var requestNo = 0, timer = null;

    function getJson(path) {
      return fetch(hub + path).then(function (r) {
        if (!r.ok) throw new Error("Registry error " + r.status);
        return r.json();
      });
    }

    function render() {
      root.textContent = "";
      var box = h("div", { class: "panel" });
      ({ search: renderSearch, confirm: renderConfirm, guided: renderGuided, unlisted: renderUnlisted })[state.mode](box);
      root.appendChild(box);
    }

    // ---------- search ----------
    function renderSearch(box) {
      var input = h("input", { type: "text", id: "finder-input", autocomplete: "off", value: state.query,
        placeholder: "College name, short name (e.g. SVU) or AICTE ID" });
      var results = h("div", { id: "finder-results" });
      box.appendChild(h("h2", null, "Which institution is your complaint about?"));
      box.appendChild(h("p", { class: "hint" }, "Start typing. You will confirm the institution before you can continue."));
      box.appendChild(input);
      box.appendChild(results);
      box.appendChild(h("div", { class: "row" },
        h("button", { class: "link", onclick: function () { state.mode = "guided"; loadGuided(); render(); } }, "Not sure? Answer a few questions"),
        h("button", { class: "link", onclick: function () { state.mode = "unlisted"; render(); } }, "My institution isn't listed")));
      input.addEventListener("input", function () {
        state.query = input.value;
        clearTimeout(timer);
        timer = setTimeout(function () { runSearch(results); }, 250);
      });
      showResults(results);
      input.focus();
    }

    function runSearch(results) {
      var q = state.query.trim(), mine = ++requestNo;
      if (q.length < 2) { state.result = null; showResults(results); return; }
      getJson("/api/institutions/search?q=" + encodeURIComponent(q)).then(function (r) {
        if (mine !== requestNo) return; // an older answer arriving late is ignored
        state.result = r;
        showResults(results);
      }).catch(function () {
        results.textContent = "";
        results.appendChild(h("div", { class: "error" }, "Cannot reach the institution registry. Is the hub running?"));
      });
    }

    function showResults(results) {
      results.textContent = "";
      var r = state.result;
      if (!r) return;
      var more = r.suggestions || [];  // from the hub's shared search engine: initials, typos, partial words
      if (r.outcome === "NOT_LISTED") {
        if (!more.length) {
          results.appendChild(h("div", { class: "fmsg" }, "No institution in the registry matches \"" + r.query + "\". Check the spelling, try the short name, or choose \"My institution isn't listed\"."));
          return;
        }
        results.appendChild(h("div", { class: "fmsg" }, "Closest matches. Is your institution one of these?"));
        results.appendChild(cardList(more, "REPORTER_CONFIRMED", null));
        return;
      }
      results.appendChild(h("div", { class: "fmsg" }, r.outcome === "RESOLVED" ? "Is this your institution?" : r.reason));
      results.appendChild(cardList(r.candidates, "REPORTER_CONFIRMED", null));
      var shown = r.candidates.map(function (c) { return c.aicte_id; });
      var extra = more.filter(function (c) { return shown.indexOf(c.aicte_id) < 0; });
      if (extra.length) {
        results.appendChild(h("div", { class: "fmsg" }, "Other possible matches"));
        results.appendChild(cardList(extra, "REPORTER_CONFIRMED", null));
      }
    }

    function cardList(items, method, answers) {
      var list = h("div", { class: "fcards" });
      items.forEach(function (c) {
        list.appendChild(h("button", { class: "fcard", onclick: function () {
          state.picked = c; state.method = method; state.answers = answers; state.mode = "confirm"; render();
        } },
          h("div", { class: "n" }, c.official_name),
          h("div", { class: "m" }, [c.aicte_id, [c.district, c.state].filter(Boolean).join(", "), c.type].filter(Boolean).join(" · ")),
          c.parent_name ? h("div", { class: "m" }, "Part of " + c.parent_name) : null));
      });
      return list;
    }

    // ---------- confirm card ----------
    function renderConfirm(box) {
      var c = state.picked;
      var address = [c.address_line, c.area, c.district, c.state, c.pincode].filter(Boolean).join(", ");
      box.className = "panel fdetail";
      box.appendChild(h("h2", null, "Please confirm this is your institution"));
      var rows = [["Official name", c.official_name], ["AICTE ID", c.aicte_id], ["Address", address],
                  ["Location", c.lat && c.lng ? c.lat.toFixed(4) + ", " + c.lng.toFixed(4) + " (from the official registry)" : ""], ["Region", c.region], ["Type", c.type], ["Programmes", c.programs && c.programs.split(";").join(", ")],
                  ["Part of", c.parent_name]];
      var dl = h("dl");
      rows.forEach(function (r) { if (r[1]) { dl.appendChild(h("dt", null, r[0])); dl.appendChild(h("dd", null, r[1])); } });
      box.appendChild(dl);
      if (c.lat && c.lng) {  // OpenStreetMap embed with a pin (needs internet; the rest works offline)
        var dx = 0.012, dy = 0.007;
        var bbox = [c.lng - dx, c.lat - dy, c.lng + dx, c.lat + dy].join(",");
        // Behind the live map sits a plain location panel (pin + coordinates), so the location is still visible offline.
        box.appendChild(h("div", { class: "fmapwrap" },
          h("div", { class: "fmapfallback" }, h("div", { class: "pin" }, "\uD83D\uDCCD"),
            h("div", { class: "coords" }, Math.abs(c.lat).toFixed(4) + "\u00B0 " + (c.lat >= 0 ? "N" : "S") + ", " + Math.abs(c.lng).toFixed(4) + "\u00B0 " + (c.lng >= 0 ? "E" : "W")),
            h("div", { class: "where" }, [c.district, c.state].filter(Boolean).join(", "))),
          h("iframe", { class: "fmap", title: "Map", loading: "lazy",
            src: "https://www.openstreetmap.org/export/embed.html?bbox=" + bbox + "&layer=mapnik&marker=" + c.lat + "," + c.lng })));
        box.appendChild(h("a", { class: "link", target: "_blank", rel: "noopener",
          href: "https://www.openstreetmap.org/?mlat=" + c.lat + "&mlon=" + c.lng + "#map=16/" + c.lat + "/" + c.lng },
          "Open larger map"));
      }
      box.appendChild(h("div", { class: "row" },
        h("button", { class: "primary", id: "finder-yes", onclick: function () {
          opts.onConfirm({ institution: c, resolution_method: state.method, finder_answers: state.answers });
        } }, "Yes, this is my institution"),
        h("button", { onclick: function () { state.mode = state.method === "GUIDED" ? "guided" : "search"; render(); } }, "No, go back")));
    }

    // ---------- guided questions ----------
    // Ask the hub what still matches. If changing one answer makes another answer impossible (for example a
    // district of another state), that answer is dropped automatically and we ask again.
    function loadGuided(attempt) {
      attempt = attempt || 0;
      var p = state.guided.picks, qs = Object.keys(p).filter(function (k) { return p[k]; })
        .map(function (k) { return k + "=" + encodeURIComponent(p[k]); }).join("&");
      getJson("/api/institutions/filters" + (qs ? "?" + qs : "")).then(function (d) {
        var stale = GUIDED_FIELDS.filter(function (f) { return p[f[0]] && d.facets[f[2]].indexOf(p[f[0]]) < 0; });
        if (stale.length && attempt < 5) {
          stale.forEach(function (f) { delete p[f[0]]; });
          return loadGuided(attempt + 1);
        }
        state.guided.data = d;
        if (state.mode === "guided") render();
      }).catch(function () { state.guided.data = { error: true }; render(); });
    }

    function renderGuided(box) {
      box.appendChild(h("h2", null, "Let's narrow it down"));
      box.appendChild(h("p", { class: "hint" }, "Answer what you know, in any order. You can change an answer at any time."));
      var d = state.guided.data;
      if (!d) { box.appendChild(h("div", { class: "fmsg" }, "Loading…")); }
      else if (d.error) { box.appendChild(h("div", { class: "error" }, "Cannot reach the institution registry.")); }
      else {
        var grid = h("div", { class: "fgrid" });
        GUIDED_FIELDS.forEach(function (f) {
          var key = f[0], sel = h("select", { id: "guided-" + key, onchange: function () {
            state.guided.picks[key] = sel.value; loadGuided();
          } }, h("option", { value: "" }, "(any)"));
          d.facets[f[2]].forEach(function (v) { sel.appendChild(h("option", { value: v }, v)); });
          sel.value = state.guided.picks[key] || "";
          grid.appendChild(h("div", null, h("label", null, f[1]), sel));
        });
        box.appendChild(grid);
        box.appendChild(h("div", { class: "fmsg" }, d.count + " institution" + (d.count === 1 ? "" : "s") + " match" +
          (d.count > d.candidates.length ? " (showing " + d.candidates.length + ")" : "")));
        box.appendChild(cardList(d.candidates, "GUIDED", JSON.parse(JSON.stringify(state.guided.picks))));
      }
      box.appendChild(h("div", { class: "row" },
        h("button", { onclick: function () { state.guided.picks = {}; loadGuided(); } }, "Reset answers"),
        h("button", { class: "link", onclick: function () { state.mode = "search"; render(); } }, "Back to search"),
        h("button", { class: "link", onclick: function () { state.mode = "unlisted"; render(); } }, "My institution isn't listed")));
    }

    // ---------- not listed ----------
    function renderUnlisted(box) {
      box.appendChild(h("h2", null, "My institution isn't listed"));
      box.appendChild(h("p", { class: "hint" }, "Tell us what you know. An officer will identify the institution; your complaint will show as \"pending verification\"."));
      var fields = [["typed_name", "Name of the institution *", "input"], ["district", "City / district", "input"],
                    ["state", "State", "input"], ["details", "Anything else that helps (address, programmes)", "textarea"]];
      fields.forEach(function (f) {
        var el = h(f[2], { id: "unlisted-" + f[0], maxlength: f[2] === "input" ? "120" : "500" });
        el.value = state.typed[f[0]];
        el.addEventListener("input", function () { state.typed[f[0]] = el.value; });
        box.appendChild(h("label", null, f[1]));
        box.appendChild(el);
      });
      var error = h("div");
      box.appendChild(error);
      box.appendChild(h("div", { class: "row" },
        h("button", { class: "primary", id: "unlisted-go", onclick: function () {
          if (state.typed.typed_name.trim().length < 3) { error.className = "error"; error.textContent = "Please type the name of the institution."; return; }
          opts.onUnlisted(JSON.parse(JSON.stringify(state.typed)));
        } }, "Continue without a verified institution"),
        h("button", { onclick: function () { state.mode = "search"; render(); } }, "Back to search")));
    }

    render();
  }

  window.InstitutionFinder = { mount: mount };
})();
