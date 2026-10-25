/* 通用登录页识别：只处理最常见的账号 + 密码 + 登录按钮。 */
window.__uatLoginResult = (function () {
  "use strict";
  window.__uatEls = window.__uatEls || {};
  let seq = 0;
  function tag(el) {
    if (!el) return null;
    if (el.__uatLoginTag && window.__uatEls[el.__uatLoginTag] === el) return el.__uatLoginTag;
    seq += 1;
    const id = "login" + seq;
    try {
      el.setAttribute("data-uat-login-id", id);
      el.__uatLoginTag = id;
      window.__uatEls[id] = el;
    } catch (e) {
      return null;
    }
    return id;
  }
  function visible(el) {
    if (!el || !el.isConnected) return false;
    const st = getComputedStyle(el);
    if (!st || st.display === "none" || st.visibility === "hidden" || parseFloat(st.opacity || "1") === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width >= 1 && r.height >= 1;
  }
  function deepQueryAll(selector, root) {
    root = root || document;
    const out = [];
    const seen = new Set();
    (function visit(node) {
      let nodes = [];
      try { nodes = Array.from(node.querySelectorAll(selector)); } catch (e) {}
      nodes.forEach(function (n) { if (!seen.has(n)) { seen.add(n); out.push(n); } });
      let all = [];
      try { all = Array.from(node.querySelectorAll("*")); } catch (e) {}
      all.forEach(function (el) { if (el.shadowRoot) visit(el.shadowRoot); });
    })(root);
    return out;
  }
  function labelText(el) {
    let parts = [];
    try {
      if (el.id) {
        const root = el.getRootNode ? el.getRootNode() : document;
        const l = root.querySelector('label[for="' + CSS.escape(el.id) + '"]');
        if (l) parts.push(l.innerText || "");
      }
      const l = el.closest && el.closest("label");
      if (l) parts.push(l.innerText || "");
    } catch (e) {}
    return parts.join(" ").replace(/\s+/g, " ").trim();
  }
  function attrText(el) {
    return [
      el.getAttribute("name"), el.id, el.getAttribute("placeholder"),
      el.getAttribute("aria-label"), el.getAttribute("autocomplete"),
      el.getAttribute("class"), labelText(el)
    ].filter(Boolean).join(" ").replace(/\s+/g, " ").trim();
  }
  function setValue(el, value) {
    if (!el) return false;
    try { el.focus(); } catch (e) {}
    try {
      const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const desc = Object.getOwnPropertyDescriptor(proto, "value");
      if (desc && desc.set) desc.set.call(el, value);
      else el.value = value;
    } catch (e) {
      try { el.value = value; } catch (e2) { return false; }
    }
    try {
      el.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
      el.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    } catch (e) {}
    return true;
  }
  window.__uat_fill = function (id, value) {
    const el = window.__uatEls[id];
    if (!el) return false;
    return setValue(el, value);
  };

  const pwds = deepQueryAll('input[type="password"]').filter(function (el) {
    return !el.disabled && visible(el);
  });
  if (!pwds.length) {
    // 分步登录：第一屏只有账号/手机号，点“下一步/继续”后才出现密码框
    const cands = deepQueryAll("input").filter(function (el) {
      if (!visible(el) || el.disabled) return false;
      const t = (el.type || "text").toLowerCase();
      if (["hidden", "password", "submit", "button", "checkbox", "radio", "file", "image", "search"].indexOf(t) >= 0) return false;
      return true;
    });
    let best = null;
    cands.forEach(function (el) {
      const t = attrText(el).toLowerCase();
      let score = 0;
      if (/(user|account|login|email|phone|mobile|uname|账号|用户名|手机|邮箱|工号)/i.test(t)) score += 60;
      const type = (el.type || "").toLowerCase();
      if (type === "email" || type === "tel") score += 20;
      if (/(search|搜索|captcha|验证码)/i.test(t)) score -= 80;
      if (!best || score > best.score) best = { el: el, score: score };
    });
    const stepButtons = deepQueryAll("button,input[type=submit],input[type=button],[role=button],a,[onclick]", document)
      .filter(function (el) { return visible(el) && !el.disabled; });
    let step = null;
    let stepScore = -1;
    stepButtons.forEach(function (el) {
      let t = "";
      try { t = (el.innerText || el.value || el.getAttribute("aria-label") || "").trim(); } catch (e) {}
      let score = 0;
      if (/(下一步|继续|next|continue)/i.test(t)) score += 100;
      else if (/(登录|登入|sign\s*in|log\s*in)/i.test(t)) score += 60;
      if (score > stepScore) { stepScore = score; step = el; }
    });
    if (best && best.score >= 60 && step && stepScore > 0) {
      return {
        found: false, needs_step: true,
        user_id: tag(best.el), submit_id: tag(step),
        reason: "检测到分步登录，先填写账号", captcha: false,
      };
    }
    return { found: false, reason: "没有可见密码框", captcha: false };
  }
  const pwd = pwds[0];
  const form = pwd.closest ? pwd.closest("form") : null;
  let scope = form || document;
  const candidates = deepQueryAll("input", scope).filter(function (el) {
    if (!visible(el) || el.disabled) return false;
    const t = (el.type || "text").toLowerCase();
    if (["hidden", "password", "submit", "button", "checkbox", "radio", "file", "image"].indexOf(t) >= 0) return false;
    return true;
  });
  let best = null;
  candidates.forEach(function (el) {
    const t = attrText(el).toLowerCase();
    let score = 0;
    if (/(user|account|login|email|phone|mobile|uname|账号|用户名|手机|邮箱|工号)/i.test(t)) score += 60;
    const type = (el.type || "").toLowerCase();
    if (type === "email" || type === "tel") score += 20;
    if (/(search|搜索|captcha|验证码)/i.test(t)) score -= 80;
    try {
      if (pwd.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING) score += 5;
    } catch (e) {}
    if (!best || score > best.score) best = { el: el, score: score };
  });
  if (!best || best.score < 0) {
    // 退化：取密码框前最近的一个文本输入框
    const all = deepQueryAll("input", scope);
    for (let i = 0; i < all.length; i++) {
      if (all[i] === pwd) break;
      const t = (all[i].type || "text").toLowerCase();
      if (t === "text" || t === "email" || t === "tel" || t === "number") best = { el: all[i], score: 0 };
    }
  }

  const buttons = deepQueryAll("button,input[type=submit],input[type=button],input[type=image],[role=button],a,[onclick]", form || document)
    .filter(function (el) { return visible(el) && !el.disabled; });
  let submit = null;
  let submitScore = -1;
  buttons.forEach(function (el) {
    let t = "";
    try { t = (el.innerText || el.value || el.getAttribute("aria-label") || "").trim(); } catch (e) {}
    let score = 0;
    if (/(登录|登入|立即登录|sign\s*in|log\s*in|submit)/i.test(t)) score += 100;
    if ((el.type || "").toLowerCase() === "submit") score += 20;
    if (/(submit|login|btn)/i.test((el.className || "") + " " + (el.id || ""))) score += 10;
    if (score > submitScore) { submitScore = score; submit = el; }
  });
  if (!submit || submitScore <= 0) {
    // 表单内第一个 submit 按钮
    const first = deepQueryAll('button[type="submit"],input[type="submit"]', form || document)
      .filter(function (el) { return visible(el); })[0];
    if (first) submit = first;
  }

  const captchaEls = deepQueryAll('img[src*="captcha" i],iframe[src*="captcha" i],[class*="captcha" i],[id*="captcha" i]')
    .filter(visible);

  return {
    found: true,
    user_id: best ? tag(best.el) : null,
    pwd_id: tag(pwd),
    submit_id: submit ? tag(submit) : null,
    captcha: captchaEls.length > 0,
    url: location.href,
  };
})();
