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
    // 纯 div 伪选项靠 class 表示选中，如 <div class="opt selected">
    try {
      if (el.classList && (el.classList.contains("selected") || el.classList.contains("checked") ||
          el.classList.contains("active") || el.classList.contains("is-selected") ||
          el.classList.contains("is-checked"))) return true;
    } catch (e) {}
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
      ".question-stem", ".stem", ".question-title", ".q-title", ".q-stem", ".title",
      ".topic", ".question-name", ".question-content", ".subject",
      ".question-text", ".exam-question", "legend", "h1", "h2", "h3", "h4", "h5", "h6",
      // 属性模糊匹配，覆盖 qs-stem / exam_question_title / subject-txt 等命名
      "[class*=stem]", "[id*=stem]", "[class*=subject]", "[id*=subject]",
      "[class*=question][class*=text]", "[class*=question][class*=title]",
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
    if (g) {
      groups.push(g);
      controls.forEach(function (c) { usedControls.add(c.el); });
    }
  });

  // 3. 没有任何标准控件、纯 div/li 的“伪选项”
  //    自研答题系统常见写法：<div class="opt"><span class="key">A</span><span class="txt">…</span></div>，
  //    选项上只挂了 click 事件，既没有 input，也没有 role/aria 属性。
  const FAKE_CLASS_RE = /(^|[\s_-])(opt|option|choice|answeritem|optionitem|selectitem|optitem|radio|checkbox)([\s_-]|$)/i;
  function fakeKey(el) {
    const cls = String((el && el.className) || "");
    const m = cls.match(FAKE_CLASS_RE);
    return m ? String(m[2] || "").toLowerCase() : "";
  }
  const fakeByRoot = new Map();
  try {
    deepQueryAll("[class]").forEach(function (el) {
      if (!el || !el.isConnected || usedControls.has(el)) return;
      if (/^(INPUT|LABEL|BUTTON|SELECT|TEXTAREA|OPTION|A|OPTGROUP)$/.test(el.tagName)) return;
      if (!isVisible(el)) return;
      try {
        if (el.closest && el.closest("nav,header,footer,select")) return;
      } catch (e) {}
      const key = fakeKey(el);
      if (!key) return;
      // 内部还并列着同类子元素的是“选项列表容器”，不是选项本身
      let innerSame = 0;
      Array.from(el.children || []).forEach(function (c) {
        if (fakeKey(c) === key) innerSame++;
      });
      if (innerSame >= 2) return;
      const p = el.parentElement;
      if (!p) return;
      // 必须和至少一个同类兄弟并列，才说明它是一组选项中的一项
      let sameSib = 0;
      Array.from(p.children || []).forEach(function (c) {
        if (c !== el && fakeKey(c) === key) sameSib++;
      });
      if (sameSib < 1) return;
      const t = textOf(el);
      if (!t || t.length > 400) return;
      // 纯数字（1/2/3…）是答题卡题号，不是选项
      if (/^\d{1,3}$/.test(t.trim())) return;
      if (!fakeByRoot.has(p)) fakeByRoot.set(p, []);
      fakeByRoot.get(p).push({ el: el });
    });
  } catch (e) {}

  fakeByRoot.forEach(function (controls) {
    if (controls.length < 2 || controls.length > 12) return;
    if (controls.some(function (c) { return usedControls.has(c.el); })) return;
    const g = makeGroup(controls, "role");
    if (g) {
      groups.push(g);
      controls.forEach(function (c) { usedControls.add(c.el); });
    }
  });

  // 4. 结构启发式：完全不看 class 名字
  //    很多系统用 <div class="item"> / <a class="ans"> / <li> 之类命名，
  //    只要“同一个父节点下有 2~8 个同 tag + 同 class 的兄弟、且上方有题干文字”，
  //    就当作一组选项。前三种精确策略没结果时才启用，避免误伤。
  const NAV_WORDS = /^(首页|主页|上一页|下一页|上一题|下一题|返回|登录|注册|退出|菜单|更多|搜索|收藏|分享|确定|取消|提交|交卷)$/;
  // 选项一定是“可点”的：鼠标手型、或者本身就是 a/li/button、或带 onclick/tabindex/role。
  // 用它把成绩表格、统计列表这类纯文本行挡在外面。
  function clicky(el) {
    if (!el) return false;
    try {
      const st = window.getComputedStyle(el);
      if (st && st.cursor === "pointer") return true;
    } catch (e) {}
    if (/^(A|LI|BUTTON|LABEL|SUMMARY|DT|DD)$/.test(el.tagName)) return true;
    try {
      if (el.hasAttribute("onclick") || el.hasAttribute("tabindex") || el.getAttribute("role")) return true;
      const p = el.parentElement;
      if (p && (p.hasAttribute("onclick") || p.getAttribute("role"))) return true;
    } catch (e) {}
    return false;
  }
  // 选项被选中后，页面常给它加一个状态 class（selected/active/checked…）。
  // 分组时要把这类状态 class 忽略掉，否则一组选项会被拆成“已选 1 个 + 未选 3 个”。
  const STATE_CLS_RE = /^(selected|active|checked|current|cur|on|off|hover|focus|focused|disabled|enabled|is-selected|is-active|is-checked|is-current|right|wrong|correct|incorrect|error|ok|done|chosen|picked|true|false|readonly|visited|marked)$/i;
  function stableClass(el) {
    let raw = "";
    try {
      raw = el.className && el.className.baseVal !== undefined ? el.className.baseVal : (el.className || "");
    } catch (e) {}
    return String(raw).split(/\s+/).filter(function (t) {
      return t && !STATE_CLS_RE.test(t);
    }).join(" ");
  }
  function structuralGroups() {
    const found = [];
    let parents = [];
    try { parents = deepQueryAll("div,ul,ol,dl,section,article,form,td,table"); } catch (e) { parents = []; }
    for (let pi = 0; pi < parents.length; pi++) {
      const p = parents[pi];
      if (!p || !p.isConnected || !isVisible(p)) continue;
      try {
        if (p.closest && p.closest("nav,header,footer,aside,select,[class*=menu],[class*=nav],[class*=sidebar],[class*=breadcrumb]")) continue;
      } catch (e) {}
      const kids = Array.from(p.children || []);
      if (kids.length < 2 || kids.length > 10) continue;
      const buckets = new Map();
      kids.forEach(function (k) {
        if (!isVisible(k)) return;
        if (/^(SCRIPT|STYLE|INPUT|SELECT|TEXTAREA|IFRAME|BR|HR)$/.test(k.tagName)) return;
        const key = k.tagName + "|" + stableClass(k);
        if (!buckets.has(key)) buckets.set(key, []);
        buckets.get(key).push(k);
      });
      buckets.forEach(function (els) {
        if (els.length < 2 || els.length > 8) return;
        if (els.some(function (e) { return usedControls.has(e); })) return;
        const texts = els.map(textOf);
        if (texts.some(function (t) { return t.length > 260; })) return;
        const filled = texts.filter(function (t) { return t.length >= 1; });
        if (filled.length < 2) return;
        // 一半以上是纯数字 → 这是答题卡题号列表，不是选项
        const numeric = filled.filter(function (t) { return /^\d{1,3}$/.test(t.trim()); }).length;
        if (numeric * 2 >= filled.length) return;
        // 每一项都得是“可点”的，否则只是普通列表/统计行
        if (!els.every(clicky)) return;
        // 一半以上是“首页/下一页/提交”这类导航词，说明不是选项
        const navLike = filled.filter(function (t) { return NAV_WORDS.test(t.trim()); }).length;
        if (navLike * 2 >= filled.length) return;
        const g = makeGroup(els.map(function (e) { return { el: e }; }), "role");
        if (!g) return;
        // 必须有像样的题干，否则多半是工具栏/列表
        if (norm(g.stem).length < 6) return;
        // 题干和选项必须属于同一块区域；否则会把“顶部导航 + 下方题干”错拼成一道题
        const stemEl = g.stem_id ? ELS[g.stem_id] : null;
        const anc = stemEl ? lca([stemEl, p]) : null;
        if (!anc || anc === document.body || anc === document.documentElement) return;
        found.push({ g: g, els: els });
      });
    }
    return found;
  }

  if (!groups.length) {
    structuralGroups().forEach(function (item) {
      groups.push(item.g);
      item.els.forEach(function (e) { usedControls.add(e); });
    });
  }

  // 5. 原生下拉框 <select>（选项文字在 option 里，没有可点击的控件）
  try {
    deepQueryAll("select").forEach(function (sel) {
      if (!sel || !sel.isConnected || !isVisible(sel) || sel.disabled || sel.multiple) return;
      const values = [];
      Array.from(sel.options || []).forEach(function (o) {
        const t = String(o.text || "").trim();
        if (!t || o.disabled) return;
        if (!o.value && /^(请选择|请选择…|--|—)/.test(t)) return;
        values.push({ text: t, value: o.value, index: o.index });
      });
      if (values.length < 2) return;
      const optNorm = norm(values.map(function (v) { return v.text; }).join(""));
      let container = sel.parentElement;
      for (let i = 0; container && container !== document.body && i < 6; i++) {
        const extra = norm(textOf(container)).length - optNorm.length;
        if (extra >= 4) break;
        container = container.parentElement;
      }
      const stem = findStem(container || sel.parentElement, [sel]);
      if (norm(stem.text || "").length < 4) return;
      const stemEl = stem.el || null;
      const anc = stemEl ? lca([stemEl, sel]) : null;
      if (!anc || anc === document.body || anc === document.documentElement) return;
      const selId = tag(sel);
      groups.push({
        qid: "q" + seq,
        container_id: tag(container || sel.parentElement),
        stem_id: stem.el ? tag(stem.el) : null,
        stem_is_container: !!stem.is_container,
        stem_has_image: !!stem.has_image,
        stem_image_key: stem.el ? imageKey(stem.el) : "",
        stem: stem.text || "",
        qtype: "select",
        options: values.map(function (v) {
          return {
            id: selId,
            input_id: selId,
            text: v.text,
            has_image: false,
            image_key: "",
            checked: sel.selectedIndex === v.index,
            index: v.index,
            value: v.value,
          };
        }),
        top: (function () {
          try { return sel.getBoundingClientRect().top + window.scrollY; } catch (e) { return 0; }
        })(),
      });
    });
  } catch (e) {}

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
