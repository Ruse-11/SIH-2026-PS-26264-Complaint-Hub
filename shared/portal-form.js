/* The complaint journey shared by both mock portals:
 *   1 Find institution (Institution Finder) -> 2 Verify phone (mock OTP) -> 3 Complaint details -> 4 Receipt
 * The portal backend (shared/portal_core.py) signs a token at step 1 and step 2; /submit needs both.
 */
(function () {
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

  // POST/GET JSON to this portal; errors become Error(message) using the server's "detail".
  function call(path, body) {
    return fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (data) {
          if (!r.ok) {
            var d = data.detail;
            throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map(function (x) { return x.msg; }).join("; ") : "Request failed (" + r.status + ")");
          }
          return data;
        });
      });
  }

  var STEPS = ["1  Find institution", "2  Verify phone", "3  Complaint details", "4  Receipt"];
  var app = document.getElementById("app");
  var cfg, S;

  function reset() { S = { step: 1, inst: null, instToken: null, contact: "", verifToken: null, otp: null, receipt: null, error: "" }; }

  function stepsBar() {
    var bar = h("div", { class: "steps" });
    STEPS.forEach(function (t, i) { bar.appendChild(h("span", { class: i + 1 === S.step ? "on" : i + 1 < S.step ? "done" : "" }, t)); });
    return bar;
  }

  function show(content) {
    app.textContent = "";
    app.appendChild(stepsBar());
    app.appendChild(content);
  }

  function errorBox() { return S.error ? h("div", { class: "error" }, S.error) : null; }
  function fail(e) { S.error = e.message; draw(); }
  function draw() { ({ 1: step1, 2: step2, 3: step3, 4: step4 })[S.step](); }

  // ---------- step 1: institution ----------
  function step1() {
    var holder = h("div");
    show(h("div", null, holder, errorBox()));
    InstitutionFinder.mount(holder, {
      hubUrl: cfg.hub_url,
      onConfirm: function (res) {
        call("/institution/confirm", { institution_id: res.institution.aicte_id, resolution_method: res.resolution_method, finder_answers: res.finder_answers })
          .then(function (d) { S.inst = d; S.instToken = d.institution_token; S.error = ""; S.step = 2; draw(); }).catch(fail);
      },
      onUnlisted: function (details) {
        call("/institution/confirm", { institution_id: null, resolution_method: "UNLISTED", finder_answers: details })
          .then(function (d) { S.inst = d; S.instToken = d.institution_token; S.unlistedName = details.typed_name; S.error = ""; S.step = 2; draw(); }).catch(fail);
      },
    });
  }

  // ---------- step 2: verify phone (MOCK OTP) ----------
  function step2() {
    var contact = h("input", { id: "contact", type: "text", placeholder: "10-digit mobile number or email", value: S.contact });
    var panel = h("div", { class: "panel" }, h("h2", null, "Verify your phone number"),
      h("p", { class: "hint" }, "We send a one-time code. (Prototype: no SMS is sent; the code is shown on this page.)"),
      h("label", null, "Mobile number or email"), contact);
    var otpBox = h("div");
    var send = h("button", { class: "primary", id: "send-otp", onclick: function () {
      S.contact = contact.value;
      call("/otp/request", { contact: contact.value }).then(function (d) { S.otp = d; S.error = ""; draw(); }).catch(fail);
    } }, S.otp ? "Send a new code" : "Send code");
    panel.appendChild(h("div", { class: "row" }, send, h("button", { class: "link", onclick: function () { S.step = 1; S.error = ""; draw(); } }, "Change institution")));
    if (S.otp) {
      var code = h("input", { id: "otp-code", type: "text", inputmode: "numeric", maxlength: "6", placeholder: "6-digit code" });
      otpBox.appendChild(h("div", { class: "demo" }, "Demo mode. Your code is ", h("b", null, S.otp.demo_otp), " ",
        h("button", { class: "link", id: "use-code", onclick: function () { code.value = S.otp.demo_otp; } }, "use this code")));
      otpBox.appendChild(h("label", null, "Enter the code"));
      otpBox.appendChild(code);
      otpBox.appendChild(h("div", { class: "row" }, h("button", { class: "primary", id: "verify-otp", onclick: function () {
        call("/otp/verify", { contact: S.contact, code: code.value })
          .then(function (d) { S.verifToken = d.verification_token; S.error = ""; S.step = 3; draw(); }).catch(fail);
      } }, "Verify")));
    }
    panel.appendChild(otpBox);
    if (S.error) panel.appendChild(errorBox());  // errorBox() is null when there is no error
    show(panel);
  }

  // ---------- step 3: complaint form ----------
  function step3() {
    var inst = S.inst.institution;
    var banner = inst
      ? h("div", { class: "banner" }, h("b", null, inst.official_name), " (" + inst.aicte_id + ") ",
          h("button", { class: "link", id: "change-inst", onclick: function () { S.step = 1; draw(); } }, "Change"))
      : h("div", { class: "banner warn" }, "Institution not verified: \"" + S.unlistedName + "\". Your complaint will show as pending verification. ",
          h("button", { class: "link", id: "change-inst", onclick: function () { S.step = 1; draw(); } }, "Change"));
    var type = h("select", { id: "f-type" }); cfg.reporter_types.forEach(function (t) { type.appendChild(h("option", { value: t }, t)); });
    var cat = h("select", { id: "f-category" }, h("option", { value: "" }, "Select…")); cfg.categories.forEach(function (c) { cat.appendChild(h("option", { value: c }, c)); });
    var title = h("input", { id: "f-title", type: "text", maxlength: "200", placeholder: "Short summary" });
    var desc = h("textarea", { id: "f-description", maxlength: "4000", placeholder: "What happened? Include dates and what you want done." });
    var sev = h("select", { id: "f-severity" }); [1, 2, 3, 4, 5].forEach(function (n) {
      sev.appendChild(h("option", { value: n }, n + (n === 1 ? " (low)" : n === 5 ? " (very serious)" : ""))); });
    sev.value = "3";
    var go = h("button", { class: "primary", id: "submit-complaint", onclick: function () {
      if (!cat.value) { S.error = "Please choose a category."; draw(); return; }
      go.disabled = true;
      call("/submit", { institution_token: S.instToken, verification_token: S.verifToken, reporter_type: type.value, category: cat.value,
                        title: title.value, description: desc.value, severity: Number(sev.value) })
        .then(function (d) { S.receipt = d; S.error = ""; S.step = 4; draw(); pollIfPending(); }).catch(function (e) { go.disabled = false; fail(e); });
    } }, "Submit complaint");
    show(h("div", { class: "panel" }, h("h2", null, "Complaint details"), banner,
      h("div", { class: "fgrid" }, h("div", null, h("label", null, "You are a"), type), h("div", null, h("label", null, "Category *"), cat)),
      h("label", null, "Title *"), title, h("label", null, "Description *"), desc,
      h("label", null, "How serious is it?"), sev, errorBox(), h("div", { class: "row" }, go)));
  }

  // ---------- step 4: receipt ----------
  function step4() {
    var r = S.receipt, inst = r.institution;
    var where = inst ? inst.official_name + " (" + inst.aicte_id + ")" : "Not yet verified (an officer will identify the institution)";
    var sync = r.sync_status === "synced" ? "Forwarded to the central monitoring hub as " + r.hub_case_id + "."
      : r.sync_status === "pending" ? "Saved. It will be forwarded to the central hub automatically (the hub is not reachable right now)."
      : "Saved, but the hub could not accept it: " + (r.last_error || r.sync_status);
    show(h("div", { class: "panel" }, h("h2", null, "Complaint received"), h("div", { class: "receipt-no", id: "receipt-no" }, r.portal_case_no),
      h("p", null, h("b", null, "Institution: "), where),
      r.pending_verification ? h("div", { class: "banner warn" }, "Status: pending verification of the institution.") : null,
      h("p", { id: "receipt-sync" }, sync),
      h("div", { class: "row" }, h("button", { class: "primary", id: "again", onclick: function () { reset(); draw(); } }, "File another complaint"))));
  }

  // If the hub was down, check again every few seconds and update the receipt line.
  function pollIfPending() {
    if (!S.receipt || S.receipt.sync_status !== "pending") return;
    var no = S.receipt.portal_case_no;
    var t = setInterval(function () {
      call("/submission/" + no).then(function (d) {
        if (!S.receipt || S.receipt.portal_case_no !== no) return clearInterval(t);
        if (d.sync_status !== "pending") { clearInterval(t); S.receipt = d; if (S.step === 4) draw(); }
      }).catch(function () {});
    }, 5000);
  }

  call("/config").then(function (c) {
    cfg = c; reset();
    document.title = c.portal_code + " Portal (mock) - File a complaint";
    document.getElementById("portal-name").textContent = c.portal_name + " (" + c.portal_code + ")";
    draw();
  }).catch(function (e) { app.textContent = "Cannot load the portal: " + e.message; });
})();
