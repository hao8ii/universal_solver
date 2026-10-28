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
    // 页面重绘后旧元素已脱离文档，读它的状态没有意义
    if (el.isConnected === false) return null;
    return stateOf(el);
  };

  // 下拉框选择：直接设置 selectedIndex 并派发 input/change
  window.__uat_select_option = function (id, index, value) {
    const el = window.__uatEls && window.__uatEls[id];
    if (!el || el.tagName !== "SELECT") return { ok: false, error: "select not found" };
    try {
      let idx = typeof index === "number" ? index : -1;
      if ((idx < 0 || idx >= el.options.length) && value != null && value !== "") {
        idx = Array.from(el.options).findIndex(function (o) { return o.value === String(value); });
      }
      if (idx < 0 || idx >= el.options.length) return { ok: false, error: "option index out of range" };
      el.selectedIndex = idx;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return { ok: true, selected: el.selectedIndex, text: String(el.options[idx].text || "").trim() };
    } catch (e) {
      return { ok: false, error: String(e) };
    }
  };

  window.__uat_click = function (id) {    const el = window.__uatEls && window.__uatEls[id];
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

  // ------------------------------------------------------------------
  // 答题卡 / 题号列表
  // 一题一页、又只有左侧题号列表（没有“下一题”按钮）的系统靠它跳题。
  // 识别方式：一组并列元素，文本是纯数字 1..N，尺寸相近、可点击。
  // excludeIds 传入当前已识别为选项的元素，避免把“1 2 3”选项当成题号。
  // ------------------------------------------------------------------
  const MAP_DONE_RE = /(done|answered|finished|complete|filled|success|hasanswer)/i;
  const MAP_CUR_RE = /(current|active|selected|focus|now)/i;

  function mapVisible(el) {
    if (!el || el.isConnected === false) return false;
    const st = window.getComputedStyle(el);
    if (!st || st.display === "none" || st.visibility === "hidden" || parseFloat(st.opacity || "1") === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width >= 4 && r.height >= 4;
  }

  function mapClass(el) {
    if (!el) return "";
    let s = "";
    try { s += el.className && el.className.baseVal !== undefined ? el.className.baseVal : (el.className || ""); } catch (e) {}
    try { s += " " + (el.id || ""); } catch (e) {}
    return String(s).toLowerCase();
  }

  function mapClickable(el) {
    const tag = (el.tagName || "").toUpperCase();
    if (tag === "A" || tag === "BUTTON" || tag === "LI" || tag === "TD") return true;
    try {
      if (el.hasAttribute("onclick") || el.hasAttribute("tabindex") || el.getAttribute("role")) return true;
    } catch (e) {}
    try { if (window.getComputedStyle(el).cursor === "pointer") return true; } catch (e) {}
    return false;
  }

  function mapCandidates(excl) {
    let all = [];
    try { all = Array.from(document.querySelectorAll("a,button,li,td,div,span,i,em,b,label,p")); } catch (e) { all = []; }
    // 穿透开放的 shadow DOM
    try {
      Array.from(document.querySelectorAll("*")).forEach(function (el) {
        if (!el.shadowRoot) return;
        try { Array.from(el.shadowRoot.querySelectorAll("a,button,li,td,div,span,i,em,b")).forEach(function (x) { all.push(x); }); } catch (e) {}
      });
    } catch (e) {}
    const seen = new Set();
    const cands = [];
    all.forEach(function (el) {
      if (!el || seen.has(el)) return;
      seen.add(el);
      if (excl.has(el)) return;
      const t = String(el.textContent || "").replace(/\s+/g, "");
      if (!/^\d{1,3}$/.test(t)) return;
      if (!mapVisible(el)) return;
      if (!mapClickable(el)) return;
      const r = el.getBoundingClientRect();
      if (r.width > 160 || r.height > 120) return;
      cands.push({ el: el, no: parseInt(t, 10), rect: r });
    });
    // 嵌套时只保留最内层（<li><span>5</span></li> 只留 span）
    return cands.filter(function (a) {
      return !cands.some(function (b) { return b !== a && a.el.contains(b.el); });
    });
  }

  function groupByDepth(cands, depth) {
    const groups = new Map();
    cands.forEach(function (c) {
      let p = c.el;
      for (let i = 0; i < depth && p; i++) p = p.parentElement;
      if (!p) return;
      if (!groups.has(p)) groups.set(p, []);
      groups.get(p).push(c);
    });
    return groups;
  }

  window.__uat_question_map = function (excludeIds) {
    const excl = new Set();
    (excludeIds || []).forEach(function (id) {
      const e = window.__uatEls && window.__uatEls[id];
      if (e) excl.add(e);
    });
    const cands = mapCandidates(excl);
    if (cands.length < 3) return null;

    let best = null;
    [1, 2].forEach(function (depth) {
      groupByDepth(cands, depth).forEach(function (items) {
        if (items.length < 3 || items.length > 200) return;
        const nos = items.map(function (x) { return x.no; });
        const uniq = new Set(nos);
        if (uniq.size !== nos.length) return;
        const mn = Math.min.apply(null, nos);
        const mx = Math.max.apply(null, nos);
        if (mx - mn + 1 > items.length * 1.6 + 2) return;   // 不连续，多半不是题号
        if (mn < 1) return;
        // DOM 顺序应大致递增
        let asc = 0;
        for (let i = 1; i < nos.length; i++) if (nos[i] > nos[i - 1]) asc++;
        if (asc < items.length * 0.6) return;
        // 尺寸应接近（题号是小方块/小圆点）
        const ws = items.map(function (x) { return x.rect.width; });
        const hs = items.map(function (x) { return x.rect.height; });
        const spread = (Math.max.apply(null, ws) - Math.min.apply(null, ws)) +
                       (Math.max.apply(null, hs) - Math.min.apply(null, hs));
        if (spread > 40) return;
        // 不能和选项区域重叠
        const box = items[0].el.parentElement;
        for (const e of excl) {
          if (!e || !box) continue;
          try {
            if (box.contains(e) || e.contains(box) || e.contains(items[0].el)) return;
          } catch (err) {}
        }
        let score = items.length * 2 + (spread < 20 ? 15 : 0);
        const pcls = mapClass(items[0].el.parentElement);
        if (/(card|sheet|answer|nav|num|no|list|grid|tab|palette|basket|circle)/.test(pcls)) score += 30;
        if (depth === 2) score += 4;   // 更内层优先，避免抓到外层大容器
        if (!best || score > best.score) best = { items: items, score: score };
      });
    });
    if (!best) return null;

    const out = [];
    best.items.forEach(function (c) {
      const el = c.el;
      let id = null;
      try {
        window.__uatNextSeq += 1;
        id = "map" + window.__uatNextSeq;
        el.setAttribute("data-uat-id", id);
        window.__uatEls[id] = el;
        el.__uatTag = id;
      } catch (e) {}
      const cls = mapClass(el) + " " + mapClass(el.parentElement) + " " + mapClass(el.firstElementChild);
      let answered = null;
      if (MAP_DONE_RE.test(cls)) answered = true;
      else if (/(undone|unanswered|notanswer|empty|blank)/.test(cls)) answered = false;
      const cur = MAP_CUR_RE.test(cls) ||
        (el.getAttribute && (el.getAttribute("aria-current") === "true" || el.getAttribute("aria-selected") === "true"));
      out.push({
        id: id,
        no: c.no,
        answered: answered,
        current: !!cur,
        text: String(el.textContent || "").trim().slice(0, 12),
      });
    });
    return { total: out.length, items: out };
  };
})();
