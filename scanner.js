/* 通用答题页面扫描器。
 *
 * 该脚本只做“找题、找选项、打标签”，不直接决定答案。
 * Python 端根据题库内容匹配后，再调用 __uat_click。
 */
window.__uatScanResult = (function () {
  "use strict";

  const TAG = "data-uat-id";
  const ELS = (window.__uatEls = {});
  let seq = 0;

  // 清理上一次扫描的标签
  try {
    document.querySelectorAll("[" + TAG + "]").forEach(function (el) {
      el.removeAttribute(TAG);
    });
  } catch (e) {}

  function tag(el) {
    if (!el) return null;
    if (el.__uatTag && ELS[el.__uatTag] === el) return el.__uatTag;
    const id = "uat" + (++seq);
    try {
      el.setAttribute(TAG, id);
      el.__uatTag = id;
      ELS[id] = el;
    } catch (e) {
      return null;
    }
    return id;
  }

  function norm(s) {
    return String(s == null ? "" : s)
      .toLowerCase()
      .replace(/[^0-9a-z\u3400-\u9fff]+/g, "");
  }

  function textOf(el) {
    if (!el) return "";
    let t = "";
    try {
      t = el.innerText || "";
    } catch (e) {}
    if (!t) {
      try {
        t = el.textContent || "";
      } catch (e) {}
    }
    return String(t).replace(/\s+/g, " ").trim();
  }

  function isVisible(el) {
    if (!el || !el.isConnected) return false;
    let st;
    try {
      st = window.getComputedStyle(el);
    } catch (e) {
      return false;
    }
    if (!st || st.display === "none" || st.visibility === "hidden") return false;
    if (parseFloat(st.opacity || "1") === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width >= 1 && r.height >= 1;
  }

  function hasImage(el) {
    if (!el) return false;
    try {
      if (el.querySelector && el.querySelector("img,svg,canvas,picture")) return true;
      const st = window.getComputedStyle(el);
      if (st && /url\(/i.test(st.backgroundImage || "")) return true;
      if (el.tagName === "IMG" || el.tagName === "CANVAS") return true;
    } catch (e) {}
    return false;
  }

  function imageKey(el) {
    if (!el) return "";
    try {
      const img = el.tagName === "IMG" ? el : (el.querySelector && el.querySelector("img"));
      if (img) {
        const s = img.getAttribute("src") || img.getAttribute("data-src") || "";
        return (s || "").slice(0, 120) + ":" + (s || "").length;
      }
      const st = window.getComputedStyle(el);
      const bg = (st && st.backgroundImage) || "";
      return bg ? bg.slice(0, 120) + ":" + bg.length : "";
    } catch (e) {
      return "";
    }
  }

  function deepQueryAll(selector, root) {
    root = root || document;
    const out = [];
    const seen = new Set();
    function visit(node) {
      let nodes = [];
      try {
        nodes = Array.from(node.querySelectorAll(selector));
      } catch (e) {}
      nodes.forEach(function (n) {
        if (!seen.has(n)) {
          seen.add(n);
          out.push(n);
        }
      });
      let all = [];
      try {
        all = Array.from(node.querySelectorAll("*"));
      } catch (e) {}
      for (let i = 0; i < all.length; i++) {
        const el = all[i];
        if (el.shadowRoot) visit(el.shadowRoot);
      }
    }
    visit(root);
    return out;
  }

  function rootOf(el) {
    try {
      return el.getRootNode ? el.getRootNode() : document;
    } catch (e) {
      return document;
    }
  }

  function labelFor(inp) {
    if (!inp) return null;
    const root = rootOf(inp);
    try {
      if (inp.id) {
        const l = root.querySelector('label[for="' + CSS.escape(inp.id) + '"]');
        if (l) return l;
      }
      const l = inp.closest ? inp.closest("label") : null;
      if (l) return l;
      const by = inp.getAttribute && inp.getAttribute("aria-labelledby");
      if (by && root.querySelector) {
        const parts = by.split(/\s+/).map(function (x) {
          try { return root.querySelector("#" + CSS.escape(x)); } catch (e) { return null; }
        }).filter(Boolean);
        if (parts.length) return parts[0];
      }
    } catch (e) {}
    return null;
  }

  function nearbyText(inp, label) {
    const candidates = [];
    if (label) candidates.push(label);
    const parent = inp.parentElement;
    if (parent) {
      let n = 0;
      try {
        n = parent.querySelectorAll("input[type=radio],input[type=checkbox],[role=radio],[role=checkbox],[aria-pressed],[aria-selected]").length;
      } catch (e) {}
      if (n <= 1) candidates.push(parent);
    }
    let sib = inp.nextElementSibling;
    if (sib && !(sib.querySelector && sib.querySelector("input[type=radio],input[type=checkbox]"))) {
      candidates.push(sib);
    }
    // 表格布局：input 在第一个 td，选项文字在下一个 td
    if (parent && /^(TD|TH)$/.test(parent.tagName) && parent.nextElementSibling) {
      const td = parent.nextElementSibling;
      if (!(td.querySelector && td.querySelector("input[type=radio],input[type=checkbox]"))) {
        candidates.push(td);
      }
    }
    // label 后面的兄弟节点可能是选项说明；但若它包含另一个 input，
    // 它通常就是下一个选项，不能拿来做当前选项文字。
    if (label && label.nextElementSibling) {
      const ls = label.nextElementSibling;
      if (!(ls.querySelector && ls.querySelector("input[type=radio],input[type=checkbox]"))) {
        candidates.push(ls);
      }
    }

    let best = "";
    candidates.forEach(function (el) {
      if (!el || !isVisible(el)) return;
      const t = textOf(el);
      if (t.length > best.length) best = t;
    });
    return best;
  }

  function optionTarget(inp, label) {
    if (label && isVisible(label)) return label;
    if (isVisible(inp)) return inp;
    const p = inp.parentElement;
    if (p && isVisible(p)) return p;
    return label || inp;
  }

  function checkedState(el) {
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
    const sel = el.getAttribute && el.getAttribute("aria-selected");
    if (sel === "true") return true;
    return false;
  }

  function groupRoot(el) {
    let p = el.parentElement;
    for (let i = 0; p && p !== document.body && i < 10; i++, p = p.parentElement) {
      let n = 0;
      try {
        n = p.querySelectorAll("input[type=radio],input[type=checkbox],[role=radio],[role=checkbox],[aria-pressed],[aria-selected]").length;
      } catch (e) {}
      if (n >= 2) return p;
    }
    return el.parentElement || el;
  }

  function lca(elements) {
    if (!elements.length) return null;
    let cur = elements[0];
    function contains(a, b) {
      try { return a === b || a.contains(b); } catch (e) { return false; }
    }
    for (let i = 1; i < elements.length; i++) {
      const b = elements[i];
      while (cur && !contains(cur, b)) cur = cur.parentElement;
      if (!cur) return null;
    }
    return cur;
  }

  function countControls(el) {
    try {
      return el.querySelectorAll("input[type=radio],input[type=checkbox],[role=radio],[role=checkbox],[aria-pressed],[aria-selected]").length;
    } catch (e) {
      return 0;
    }
  }

  function containsElement(parent, child) {
    try { return parent === child || parent.contains(child); } catch (e) { return false; }
  }

  function isBadRegion(el) {
    try {
      if (el.closest && el.closest("nav,header,footer")) return true;
    } catch (e) {}
    return false;
  }

  function findStem(container, optionEls) {
    if (!container) return { el: null, text: "", is_container: false };
    const selectors = [
      ".question-stem", ".stem", ".question-title", ".q-title", ".title",
      ".topic", ".question-name", ".question-content", ".subject",
      ".question-text", ".exam-question", "legend", "h1", "h2", "h3", "h4", "h5", "h6",
    ];
    let best = null;
    for (let si = 0; si < selectors.length; si++) {
      let nodes = [];
      try { nodes = Array.from(container.querySelectorAll(selectors[si])); } catch (e) {}
      // 加入 shadow root 内部节点
      try {
        deepQueryAll(selectors[si], container).forEach(function (n) {
          if (nodes.indexOf(n) < 0) nodes.push(n);
        });
      } catch (e) {}
      for (let i = 0; i < nodes.length; i++) {
        const el = nodes[i];
        if (el === container || !isVisible(el)) continue;
        let containsOpt = false;
        for (let j = 0; j < optionEls.length; j++) {
          if (containsElement(el, optionEls[j])) { containsOpt = true; break; }
        }
        if (containsOpt) continue;
        const t = textOf(el);
        if (t.length < 2) continue;
        const score = t.length + (selectors[si].indexOf("stem") >= 0 ? 40 : 0);
        if (!best || score > best.score) best = { el: el, text: t, score: score };
      }
      if (best && best.score >= 40) break;
    }

    if (!best) {
      // 找选项之前、包含文字最多的块
      let nodes = [];
      try { nodes = Array.from(container.querySelectorAll("div,p,span,section,article")); } catch (e) {}
      for (let i = 0; i < nodes.length; i++) {
        const el = nodes[i];
        if (el === container || !isVisible(el)) continue;
        let containsOpt = false;
        for (let j = 0; j < optionEls.length; j++) {
          if (containsElement(el, optionEls[j])) { containsOpt = true; break; }
        }
        if (containsOpt) continue;
        const t = textOf(el);
        if (t.length < 4) continue;
        const score = t.length;
        if (!best || score > best.score) best = { el: el, text: t, score: score };
      }
    }

    function largestStemImage() {
      try {
        let imgs = Array.from(container.querySelectorAll("img,canvas,picture"));
        let bestImg = null;
        let bestArea = 0;
        imgs.forEach(function (img) {
          for (let j = 0; j < optionEls.length; j++) {
            if (containsElement(optionEls[j], img)) return;
          }
          if (!isVisible(img)) return;
          const r = img.getBoundingClientRect();
          const area = r.width * r.height;
          if (area > bestArea) { bestArea = area; bestImg = img; }
        });
        if (bestImg && bestArea >= 900) return bestImg;
      } catch (e) {}
      return null;
    }

    if (best && best.text) {
      // 只有“1.”这种题号文字时，真正题干很可能是下面的大图
      if (norm(best.text).length < 5) {
        const img = largestStemImage();
        if (img) return { el: img, text: "", is_container: false, has_image: true };
      }
      return { el: best.el, text: best.text, is_container: best.el === container };
    }

    // 题干可能是图片：找容器里最大的、不属于选项区域的图片
    const stemImg = largestStemImage();
    if (stemImg) {
      return { el: stemImg, text: "", is_container: false, has_image: true };
    }

    // 整个容器减去选项文字
    let full = textOf(container);
    optionEls.forEach(function (el) {
      const t = textOf(el);
      if (t) full = full.replace(t, " ");
    });
    full = full.replace(/\s+/g, " ").trim();
    return { el: container, text: full, is_container: true };
  }

  function makeGroup(controls, kind) {
    const seen = new Set();
    const items = [];
    for (let i = 0; i < controls.length; i++) {
      const c = controls[i];
      if (!c || seen.has(c.el)) continue;
      seen.add(c.el);
      let target = c.el;
      let label = null;
      let text = "";
      if (kind === "input") {
        label = labelFor(c.el);
        target = optionTarget(c.el, label);
        text = nearbyText(c.el, label);
      } else {
        text = textOf(c.el);
      }
      items.push({
        el: c.el,
        target: target || c.el,
        text: text || "",
        checked: checkedState(c.el),
      });
    }
    // 去掉完全重复的点击目标
    const seenTargets = new Set();
    const uniq = [];
    items.forEach(function (it) {
      if (seenTargets.has(it.target)) return;
      seenTargets.add(it.target);
      uniq.push(it);
    });
    if (uniq.length < 2) return null;

    const allEls = uniq.map(function (x) { return x.target || x.el; });
    let container = lca(allEls) || groupRoot(controls[0].el);
    let cur = container;
    for (let i = 0; cur && cur !== document.body && i < 7; i++) {
      const inside = countControls(cur);
      if (inside > uniq.length + 1) break;
      const optText = norm(uniq.map(function (x) { return x.text; }).join(""));
      const total = norm(textOf(cur));
      let extra = total.length - optText.length;
      if (extra < 4 && !hasImage(cur)) {
        cur = cur.parentElement;
      } else {
        break;
      }
    }
    container = cur || container;
    if (!container || isBadRegion(container)) return null;

    const optionEls = uniq.map(function (x) { return x.target || x.el; });
    const stem = findStem(container, optionEls);
    const isMultiple = kind === "input"
      ? controls.some(function (c) { return c.el.type === "checkbox"; })
      : controls.some(function (c) { return (c.el.getAttribute("role") || "").toLowerCase() === "checkbox"; });

    const options = uniq.map(function (x) {
      const targetId = tag(x.target || x.el);
      const inputId = tag(x.el);
      return {
        id: targetId,
        input_id: inputId,
        text: x.text || "",
        has_image: hasImage(x.target || x.el),
        image_key: imageKey(x.target || x.el),
        checked: !!x.checked,
      };
    }).filter(function (o) { return o.id; });

    if (options.length < 2) return null;
    const anyText = options.some(function (o) { return norm(o.text).length >= 1; });
    const anyImage = options.some(function (o) { return o.has_image; });
    const stemText = stem.text || "";
    if (!anyText && !anyImage && !norm(stemText)) return null;

    return {
      qid: "q" + seq,
      container_id: tag(container),
      stem_id: stem.el ? tag(stem.el) : null,
      stem_is_container: !!stem.is_container,
      stem_has_image: !!stem.has_image,
      stem_image_key: stem.el ? imageKey(stem.el) : "",
      stem: stemText,
      qtype: isMultiple ? "multiple" : "single",
      options: options,
      top: (function () {
        try { return container.getBoundingClientRect().top + window.scrollY; } catch (e) { return 0; }
      })(),
    };
  }

  const groups = [];
  const usedControls = new Set();

  // 1. 标准 radio / checkbox
  const inputs = deepQueryAll("input[type=radio],input[type=checkbox]");
  const byRoot = new Map();
  inputs.forEach(function (inp) {
    if (!inp || inp.disabled || usedControls.has(inp)) return;
    const label = labelFor(inp);
    if (!isVisible(inp) && !(label && isVisible(label))) return;
    let region = inp.parentElement;
    try { if (inp.closest && inp.closest("nav,header,footer")) return; } catch (e) {}
    const root = groupRoot(inp);
    if (!byRoot.has(root)) byRoot.set(root, []);
    byRoot.get(root).push({ el: inp });
  });
  byRoot.forEach(function (controls) {
    if (controls.length < 2 || controls.length > 30) return;
    const g = makeGroup(controls, "input");
    if (g) {
      groups.push(g);
      controls.forEach(function (c) { usedControls.add(c.el); });
    }
  });

  // 2. ARIA / 自定义单选、多选
  const roles = deepQueryAll('[role="radio"],[role="checkbox"],[aria-checked],[aria-pressed],[aria-selected]');
  const roleByRoot = new Map();
  roles.forEach(function (el) {
    if (!el || el.tagName === "INPUT" || usedControls.has(el) || !isVisible(el)) return;
    if (el.closest && el.closest("select")) return;
    try {
      if (el.closest("label") && el.closest("label").querySelector("input[type=radio],input[type=checkbox]")) return;
    } catch (e) {}
    const root = groupRoot(el);
    if (!roleByRoot.has(root)) roleByRoot.set(root, []);
    roleByRoot.get(root).push({ el: el });
  });
  roleByRoot.forEach(function (controls) {
    if (controls.length < 2 || controls.length > 30) return;
    const g = makeGroup(controls, "role");
    if (g) groups.push(g);
  });

  // 按页面位置排序并去重
  const out = [];
  const signatures = new Set();
  groups.sort(function (a, b) { return a.top - b.top; });
  groups.forEach(function (g) {
    const sig = norm(g.stem) + "|" + g.options.map(function (o) {
      return norm(o.text) + (o.has_image ? "#img" : "");
    }).join("|");
    if (signatures.has(sig)) return;
    signatures.add(sig);
    out.push(g);
  });

  return {
    url: location.href,
    title: document.title,
    groups: out,
    has_password: !!document.querySelector('input[type="password"]'),
    body_text: (document.body ? textOf(document.body).slice(0, 500) : ""),
  };
})();
