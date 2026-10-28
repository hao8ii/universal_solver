#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""页面诊断：打开一个答题页，打印扫描器实际识别到的题目/选项，并截图。

用法：
    python page_diag.py                      # 用 config.json 里的网址
    python page_diag.py http://xxx/exam      # 指定网址
    python page_diag.py <url> --show         # 打开可见浏览器，便于手动登录后按回车再扫描

遇到“工具没反应/识别不到题目”时，把这里的输出发给开发者即可定位。
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from bank import Bank  # noqa: E402
from engine import EngineConfig, UniversalEngine  # noqa: E402


def load_config_url() -> str:
    path = os.path.join(HERE, "config.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return str(json.load(f).get("url") or "")
    except Exception:
        return ""


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show = "--show" in sys.argv
    url = args[0] if args else load_config_url()
    if not url:
        print("请提供网址：python page_diag.py http://example.com/exam")
        return 2

    cfg = EngineConfig(url=url, headless=not show, ocr=False, wait_login_seconds=30)
    eng = UniversalEngine(Bank([]), cfg, log_callback=lambda m, l="info": print("  [%s] %s" % (l, m)))
    try:
        eng._launch_browser()
        eng._open_url()
        if show:
            input("\n浏览器已打开。手动登录/进入答题页后按回车开始扫描…")
        else:
            eng._sleep(2.0)

        groups = eng.scan_page(strict=False)
        print("\n=== 扫描结果 ===")
        print("标题：%s" % eng.driver.title)
        print("识别到题组：%d" % len(groups))
        for i, g in enumerate(groups, 1):
            stem = (g.get("stem") or "").replace("\n", " ")
            print("\n  [%d] %s ｜ 题型=%s ｜ 题干：%s" % (
                i, "iframe" if g.get("frame") else "主文档", g.get("qtype"), stem[:80] or "（空）"))
            for j, o in enumerate(g.get("options") or [], 1):
                mark = "图" if o.get("has_image") else "文"
                print("       %d.%s %s%s" % (
                    j, mark, (o.get("text") or "")[:60],
                    "（已选）" if o.get("checked") else ""))

        print("\n=== 翻页能力 ===")
        nxt = eng._find_next(groups)
        print("  “下一题/下一页”按钮：%s" % (("有 → %s" % nxt.get("text")) if nxt else "没有"))
        qmap = eng._find_question_map(groups)
        if qmap:
            items = qmap.get("items") or []
            cur = [it["no"] for it in items if it.get("current")]
            print("  答题卡/题号列表：%d 个题号（%s）%s" % (
                len(items),
                " ".join(str(it["no"]) for it in items[:30]),
                "｜当前第 %d 题" % cur[0] if cur else "",
            ))
        else:
            print("  答题卡/题号列表：未识别到")

        print("\n=== 页面结构统计 ===")
        stats = eng.driver.execute_script("""
            return {
              'input[type=radio/checkbox]': document.querySelectorAll('input[type=radio],input[type=checkbox]').length,
              '[role/aria 控件]': document.querySelectorAll('[role=radio],[role=checkbox],[aria-checked],[aria-pressed],[aria-selected]').length,
              'label': document.querySelectorAll('label').length,
              'select 下拉框': document.querySelectorAll('select').length,
              'iframe': document.querySelectorAll('iframe,frame').length,
              'canvas': document.querySelectorAll('canvas').length
            };
        """)
        for k, v in stats.items():
            print("  %-28s %s" % (k, v))

        shot = os.path.join(HERE, "page_diag.png")
        try:
            eng.driver.save_screenshot(shot)
            print("\n截图已保存：%s" % shot)
        except Exception:
            pass

        if not groups:
            print("\n没有识别到题目。常见原因：")
            print("  1) 还没进入答题页（仍是登录页/说明页）；")
            print("  2) 题目在跨域封闭 iframe 里；")
            print("  3) 整题画在 canvas 上；")
            print("  4) 选项结构特殊，需要补充识别规则（把上面的结构统计发出来）。")
        return 0
    finally:
        try:
            eng.close_browser()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
