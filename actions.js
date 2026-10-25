/* 与 scanner.js 配合的点击/状态/翻页动作。 */
(function () {
  "use strict";

  window.__uatEls = window.__uatEls || {};
  window.__uatNextSeq = window.__uatNextSeq || 0;

  function stateOf(el) {
    if (!el) return false;
    let inp = null;
    if (el.tagName === "INPUT") inp = el;
    else {
      try { inp = el.querySelector && el.querySelector("input[type=radio],input[type=checkbox]"); } catch (e) {}
    }
    if (inp) return !!inp.checked;
    const a = el.getAttribute && el.getAttribute("aria-checked");
    if (a === "true" || a === "mixed") return true;
    const p = el.getAttribute && el.getAttribute("aria-pressed");
    if (p === "true") return true;
    const s = el.getAttribute && el.getAttribute("aria-selected");
    if (s === "true") return true;
    try {
      if (el.classList && (el.classList.contains("checked") || el.classList.contains("selected") || el.classList.contains("active"))) return true;
    } catch (e) {}
    return false;
  }

  window.__uat_state = function (id) {
    const el = window.__uatEls && window.__uatEls[id];
    if (!el) return null;
    return stateOf(el);
  };

  window.__uat_click = function (id) {
    const el = window.__uatEls && window.__uatEls[id];
    if (!el) return { ok: false, error: "element not found" };
    try { el.scrollIntoView({ block: "center", inline: "center" }); } catch (e) {}
    const before = stateOf(el);
    let clicked = false;
    try {
      el.click();
      clicked = true;
    } catch (e) {
      try {
        const ev = new MouseEvent("click", { bubbles: true, cancelable: true, view: window });
        el.dispatchEvent(ev);
        clicked = true;
      } catch (e2) {}
    }
    let after = stateOf(el);
    // 自定义控件有时只监听 pointer/mouse 事件
    if (clicked && before === after && el.tagName !== "INPUT" && el.tagName !== "LABEL") {
      try {
        ["pointerdown", "mousedown", "pointerup", "mouseup"].forEach(function (name) {
          const Ctor = name.indexOf("pointer") === 0 && window.PointerEvent ? PointerEvent : MouseEvent;
          el.dispatchEvent(new Ctor(name, { bubbles: true, cancelable: true, view: window }));
        });
        after = stateOf(el);
      } catch (e) {}
    }
    return { ok: true, before: before, after: after, tag: el.tagName };
  };

  window.__uat_find_next = function () {
    const selector = "button,a,[role=button],input[type=button],input[type=submit],input[type=image],[onclick],[class*=next i],[id*=next i]";
    const els = Array.from(document.querySelectorAll(selector));
    // 穿透开放的 shadow DOM
    const seen = new Set();
    function addDeep(root) {
      let all = [];
      try { all = Array.from(root.querySelectorAll("*")); } catch (e) {}
      all.forEach(function (el) {
        if (el.shadowRoot) {
          try {
            Array.from(el.shadowRoot.querySelectorAll(selector)).forEach(function (x) { els.push(x); });
          } catch (e) {}
          addDeep(el.shadowRoot);
        }
      });
    }
    addDeep(document);

    function txt(el) {
      let t = "";
      try { t = el.innerText || ""; } catch (e) {}
      if (!t) t = el.value || "";
      if (!t) t = el.getAttribute("aria-label") || el.getAttribute("title") || el.getAttribute("alt") || "";
      return String(t).replace(/\s+/g, " ").trim();
    }
    function visible(el) {
      if (!el || !el.isConnected) return false;
      const st = window.getComputedStyle(el);
      if (!st || st.display === "none" || st.visibility === "hidden" || parseFloat(st.opacity || "1") === 0) return false;
      const r = el.getBoundingClientRect();
      return r.width >= 1 && r.height >= 1;
    }
    const bad = /(提交|交卷|完成|结束|保存|返回|退出|上一|上一步|prev|back|submit|finish)/i;
    const good = /(下一题|下一页|下一步|下一部分|下一章|下一节|继续答题|继续|next|continue)/i;
    const candidates = [];
    seen.clear();
    els.forEach(function (el) {
      if (!el || seen.has(el) || !visible(el)) return;
      seen.add(el);
      if (el.disabled) return;
      if (el.getAttribute("aria-disabled") === "true") return;
      try { if (el.classList && (el.classList.contains("disabled") || el.classList.contains("is-disabled"))) return; } catch (e) {}
      const t = txt(el);
      if (!t && !/(next|下一)/i.test((el.className || "") + " " + (el.id || ""))) return;
      if (bad.test(t)) return;
      if (!good.test(t) && !/(next|下一)/i.test((el.className || "") + " " + (el.id || ""))) return;
      let priority = 20;
      if (/下一题/.test(t)) priority = 100;
      else if (/下一页|下一部分|下一章|下一节/.test(t)) priority = 90;
      else if (/继续/.test(t)) priority = 60;
      else if (/next|continue/i.test(t)) priority = 50;
      candidates.push({ el: el, text: t, priority: priority });
    });
    candidates.sort(function (a, b) {
      if (b.priority !== a.priority) return b.priority - a.priority;
      return a.el.getBoundingClientRect().top - b.el.getBoundingClientRect().top;
    });
    if (!candidates.length) return null;
    const c = candidates[0];
    let id = null;
    try {
      window.__uatNextSeq += 1;
      id = "next" + window.__uatNextSeq;
      c.el.setAttribute("data-uat-id", id);
      window.__uatEls[id] = c.el;
      c.el.__uatTag = id;
    } catch (e) {}
    return { id: id, text: c.text, priority: c.priority, count: candidates.length };
  };
})();
