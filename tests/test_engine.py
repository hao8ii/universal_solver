#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用答题引擎集成测试（本地模拟网站 + 无头 Chrome）。"""

from __future__ import annotations

import glob
import html
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from bank import Bank, BankQuestion  # noqa: E402
from engine import EngineConfig, UniversalEngine  # noqa: E402
from mock_server import MockServer  # noqa: E402


BANK = Bank([
    BankQuestion(
        1, "全面依法治国要坚持什么？", "A", "单选题",
        {"A": "坚持依法治国和以德治国相结合", "B": "放弃党的领导",
         "C": "只依靠群众运动", "D": "仅依靠道德教化"},
    ),
    BankQuestion(
        2, "下列哪些属于全面依法治国的要求？", "ABD", "多选题",
        {"A": "科学立法", "B": "严格执法", "C": "只强调效率", "D": "全民守法"},
    ),
    BankQuestion(
        3, "依法治国是党领导人民治理国家的基本方略。", "正确", "判断题",
        {"A": "正确", "B": "错误"},
    ),
])


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.server = MockServer()
        self.profile = tempfile.mkdtemp(prefix="uat_profile_")
        self.engine = None
        self.logs = []

    def tearDown(self):
        if self.engine is not None:
            try:
                self.engine.close_browser()
            except Exception:
                pass
        self.server.close()

    def make_engine(self, path: str, **kwargs):
        cfg = EngineConfig(
            url=self.server.base + path,
            headless=True,
            ocr=kwargs.pop("ocr", True),
            wait_login_seconds=kwargs.pop("wait_login_seconds", 15),
            profile_dir=self.profile,
            **kwargs,
        )
        self.engine = UniversalEngine(
            BANK, cfg,
            log_callback=lambda m, l="info": self.logs.append((l, m)),
        )
        return self.engine

    def test_standard_page_answer_and_verify(self):
        eng = self.make_engine("/quiz")
        eng._launch_browser()
        eng._open_url()
        groups = eng.scan_page(strict=True)
        self.assertEqual(len(groups), 3)
        results = eng.answer_current_page(groups)
        self.assertTrue(all(r["status"] == "answered" for r in results), results)
        states = [
            [eng._state_tag(o["id"], g.get("frame") or []) for o in g["options"]]
            for g in groups
        ]
        # q1 正确选项在第二个；q2 选 2/3/4；q3 正确在第二个
        self.assertEqual(states[0], [False, True, False, False])
        self.assertEqual(states[1], [False, True, True, True])
        self.assertEqual(states[2], [False, True])
        # 未点击提交
        self.assertNotIn("已提交", eng.driver.find_element("tag name", "body").text)

    def test_custom_aria_controls(self):
        eng = self.make_engine("/custom", ocr=False)
        eng._launch_browser()
        eng._open_url()
        groups = eng.scan_page(strict=True)
        self.assertEqual(len(groups), 2)
        results = eng.answer_current_page(groups)
        self.assertTrue(all(r["status"] == "answered" for r in results), results)
        states = [
            [eng._state_tag(o["id"], g.get("frame") or []) for o in g["options"]]
            for g in groups
        ]
        self.assertEqual(states[0], [False, True, False, False])
        self.assertEqual(states[1], [False, True, True, True])

    def test_aria_pressed_buttons(self):
        eng = self.make_engine("/pressed", ocr=False)
        eng._launch_browser()
        eng._open_url()
        groups = eng.scan_page(strict=True)
        self.assertEqual(len(groups), 1)
        results = eng.answer_current_page(groups)
        self.assertEqual(results[0]["status"], "answered", results)
        states = [eng._state_tag(o["id"], groups[0].get("frame") or []) for o in groups[0]["options"]]
        self.assertEqual(states, [False, True, False, False])

    def test_table_layout(self):
        eng = self.make_engine("/table", ocr=False)
        eng._launch_browser()
        eng._open_url()
        groups = eng.scan_page(strict=True)
        self.assertEqual(len(groups), 1)
        results = eng.answer_current_page(groups)
        self.assertEqual(results[0]["status"], "answered", results)
        states = [eng._state_tag(o["id"], groups[0].get("frame") or []) for o in groups[0]["options"]]
        self.assertEqual(states, [False, True, False, False])

    def test_image_options_ocr(self):
        eng = self.make_engine("/images", ocr=True)
        eng._launch_browser()
        eng._open_url()
        groups = eng.scan_page(strict=True)
        self.assertEqual(len(groups), 1)
        self.assertTrue(any(o.get("has_image") for o in groups[0]["options"]))
        results = eng.answer_current_page(groups)
        self.assertEqual(results[0]["status"], "answered", results)
        states = [eng._state_tag(o["id"], groups[0].get("frame") or []) for o in groups[0]["options"]]
        self.assertEqual(states, [False, True, False, False])

    def test_image_stem_ocr(self):
        eng = self.make_engine("/image_stem", ocr=True)
        eng._launch_browser()
        eng._open_url()
        groups = eng.scan_page(strict=True)
        self.assertEqual(len(groups), 1)
        results = eng.answer_current_page(groups)
        self.assertEqual(results[0]["status"], "answered", results)
        states = [eng._state_tag(o["id"], groups[0].get("frame") or []) for o in groups[0]["options"]]
        self.assertEqual(states, [False, True, False, False])

    def test_iframe(self):
        eng = self.make_engine("/frame")
        eng._launch_browser()
        eng._open_url()
        groups = eng.scan_page(strict=True)
        self.assertEqual(len(groups), 1)
        self.assertTrue(groups[0].get("frame"))
        results = eng.answer_current_page(groups)
        self.assertEqual(results[0]["status"], "answered", results)

    def test_shadow_dom(self):
        eng = self.make_engine("/shadow")
        eng._launch_browser()
        eng._open_url()
        groups = eng.scan_page(strict=True)
        self.assertEqual(len(groups), 1)
        results = eng.answer_current_page(groups)
        self.assertEqual(results[0]["status"], "answered", results)

    def test_structural_div_options(self):
        """class 名不含 opt/option 等关键词的纯 div 选项，靠结构识别。"""
        eng = self.make_engine("/divopt", ocr=False)
        eng._launch_browser()
        eng._open_url()
        groups = eng.scan_page(strict=True)
        self.assertEqual(len(groups), 1)
        results = eng.answer_current_page(groups)
        self.assertEqual(results[0]["status"], "answered", results)
        states = [eng._state_tag(o["id"], groups[0].get("frame") or []) for o in groups[0]["options"]]
        self.assertEqual(states, [False, True, False, False])
        # 选中后页面给该项加了 selected 类，选项组不能被拆成“已选 1 + 未选 3”
        again = eng.scan_page(strict=True)
        self.assertEqual(len(again), 1, [g.get("stem") for g in again])
        self.assertEqual(len(again[0]["options"]), 4)

    def test_anchor_options(self):
        """选项是 <a> 链接。"""
        eng = self.make_engine("/anchors", ocr=False)
        eng._launch_browser()
        eng._open_url()
        groups = eng.scan_page(strict=True)
        self.assertEqual(len(groups), 1)
        results = eng.answer_current_page(groups)
        self.assertEqual(results[0]["status"], "answered", results)
        states = [eng._state_tag(o["id"], groups[0].get("frame") or []) for o in groups[0]["options"]]
        self.assertEqual(states, [False, True, False, False])

    def test_select_options(self):
        """原生 <select> 下拉框。"""
        eng = self.make_engine("/select", ocr=False)
        eng._launch_browser()
        eng._open_url()
        groups = eng.scan_page(strict=True)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["qtype"], "select")
        self.assertEqual(len(groups[0]["options"]), 4)
        results = eng.answer_current_page(groups)
        self.assertEqual(results[0]["status"], "answered", results)
        self.assertEqual(
            eng.driver.execute_script("return document.getElementById('ans-sel').value"), "A"
        )

    def test_navigation_not_mistaken_for_options(self):
        """顶部导航不能被当成一组选项。"""
        eng = self.make_engine("/noise", ocr=False)
        eng._launch_browser()
        eng._open_url()
        groups = eng.scan_page(strict=True)
        self.assertEqual(len(groups), 1, [g.get("stem") for g in groups])
        self.assertIn("全面依法治国", groups[0]["stem"])
        results = eng.answer_current_page(groups)
        self.assertEqual(results[0]["status"], "answered", results)

    def test_entry_form_then_answer(self):
        """“姓名 + 进入考试”的入场页要能自动填名并进入。"""
        eng = self.make_engine("/entry")
        eng.config.username = "张三"
        eng.run()
        self.assertIn("/quiz", eng.driver.current_url)
        logs = "\n".join(m for _, m in self.logs)
        self.assertIn("入场表单", logs)
        self.assertIn("检测到 3 道题", logs)

    def test_answer_card_jump(self):
        """一题一页、没有“下一题”按钮，只有右侧答题卡 → 靠题号跳题。"""
        eng = self.make_engine("/card", ocr=False)
        eng.run()
        logs = "\n".join(m for _, m in self.logs)
        self.assertIn("答题卡：跳到第 2 题", logs)
        self.assertIn("答题卡：跳到第 3 题", logs)
        # 三题都答过（答题卡上 3 个题号都带 no-done）
        done = eng.driver.execute_script(
            "return Array.from(document.querySelectorAll('.no')).map(function(e){return e.classList.contains('no-done')})"
        )
        self.assertEqual(done, [True, True, True])
        # 答题卡题号不能被当成选项
        groups = eng.scan_page(strict=True)
        self.assertEqual(len(groups), 1, [g.get("stem") for g in groups])

    def test_auto_next_stops_before_submit(self):
        eng = self.make_engine("/page1")
        eng.run()
        self.assertEqual(eng.driver.current_url, self.server.base + "/page2")
        body = eng.driver.find_element("tag name", "body").text
        self.assertNotIn("已提交", body)
        self.assertIn("提交", body)
        logs = "\n".join(m for _, m in self.logs)
        self.assertIn("点击：下一题", logs)
        self.assertIn("没有找到“下一题/下一页”", logs)

    def test_auto_advance_after_selection(self):
        eng = self.make_engine("/auto1")
        eng.run()
        self.assertEqual(eng.driver.current_url, self.server.base + "/page2")
        groups = eng.scan_page()
        self.assertEqual(len(groups), 1)
        states = [eng._state_tag(o["id"], groups[0].get("frame") or []) for o in groups[0]["options"]]
        self.assertEqual(states, [False, True])
        logs = "\n".join(m for _, m in self.logs)
        self.assertIn("检测到页面已自动切换", logs)

    def test_two_step_login_then_answer(self):
        eng = self.make_engine("/login_step")
        eng.config.username = "u"
        eng.config.password = "p"
        eng.run()
        self.assertIn("/quiz", eng.driver.current_url)
        logs = "\n".join(m for _, m in self.logs)
        self.assertIn("分步登录", logs)
        self.assertIn("检测到 3 道题", logs)

    def test_generic_login_then_answer(self):
        eng = self.make_engine("/login")
        eng.config.username = "u"
        eng.config.password = "p"
        eng.run()
        self.assertIn("/quiz", eng.driver.current_url)
        body = eng.driver.find_element("tag name", "body").text
        self.assertNotIn("已提交", body)
        logs = "\n".join(m for _, m in self.logs)
        self.assertIn("用户名已填写", logs)
        self.assertIn("密码已填写", logs)
        self.assertIn("检测到 3 道题", logs)


class RealBankEngineTest(unittest.TestCase):
    """用真实 Word 题库中的一道题生成网页，验证 2162 题规模下的匹配。"""

    def setUp(self):
        self.server = MockServer()
        self.profile = tempfile.mkdtemp(prefix="uat_profile_real_")
        self.engine = None
        self.logs = []

    def tearDown(self):
        if self.engine is not None:
            try:
                self.engine.close_browser()
            except Exception:
                pass
        self.server.close()

    def test_real_question_with_shuffled_options(self):
        paths = glob.glob(os.path.join(os.path.dirname(ROOT), "tiku", "2023*.docx"))
        if not paths:
            self.skipTest("2023 docx not found")
        bank = Bank.load(paths[0])
        from collections import Counter
        stem_counts = Counter(q.norm_stem for q in bank.questions)
        candidates = [
            q for q in bank.questions
            if q.options and q.answer_letters and 3 <= len(q.options) <= 4
            and q.qtype in ("单选题", "多选题")
            and stem_counts[q.norm_stem] == 1
        ]
        self.assertTrue(candidates)
        q = candidates[0]
        letters = [ch for ch in q.answer_letters if ch in q.options]
        # 逆序，模拟网页选项顺序与题库完全不同
        order = list(reversed(letters + [ch for ch in q.options if ch not in letters]))
        qtype = "checkbox" if q.qtype == "多选题" else "radio"
        labels = "\n".join(
            '<label><input type="%s" name="q" value="%s"> %s. %s</label>' % (
                qtype, ch, ch, html.escape(q.options[ch])
            )
            for ch in order
        )
        page = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<div class="question"><div class="question-stem">%s</div>%s</div>
<button onclick="document.body.innerHTML='已提交'">提交</button>
</body></html>""" % (html.escape(q.stem), labels)
        self.server.set_dynamic(page)

        cfg = EngineConfig(
            url=self.server.base + "/dynamic",
            headless=True,
            ocr=False,
            wait_login_seconds=15,
            profile_dir=self.profile,
        )
        self.engine = UniversalEngine(
            bank, cfg,
            log_callback=lambda m, l="info": self.logs.append((l, m)),
        )
        self.engine.run()
        body = self.engine.driver.find_element("tag name", "body").text
        self.assertNotIn("已提交", body)
        # 检查所有正确选项都被选中，错误选项都未选中
        groups = self.engine.scan_page()
        self.assertEqual(len(groups), 1)
        states = [self.engine._state_tag(o["id"], groups[0].get("frame") or []) for o in groups[0]["options"]]
        expected = [bool(ch in letters) for ch in order]
        self.assertEqual(states, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
