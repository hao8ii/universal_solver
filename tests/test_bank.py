#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""题库解析与内容匹配测试。"""

from __future__ import annotations

import glob
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from bank import Bank, BankQuestion  # noqa: E402


PARENT = os.path.dirname(ROOT)
TIKU = os.path.join(PARENT, "tiku")


class BankMatchTests(unittest.TestCase):
    def setUp(self):
        self.bank = Bank([
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

    def test_option_order_does_not_matter(self):
        q = self.bank.questions[0]
        page = [
            "D. 仅依靠道德教化",
            "A. 坚持依法治国和以德治国相结合",
            "C. 只依靠群众运动",
            "B. 放弃党的领导",
        ]
        ans = self.bank.match_answers(q, page)
        self.assertTrue(ans.ok)
        self.assertEqual(ans.indices, [1])
        self.assertEqual(ans.option_scores[0], 100.0)

    def test_multiple_choice_reordered(self):
        q = self.bank.questions[1]
        page = [
            "C. 只强调效率",
            "A. 科学立法",
            "B. 严格执法",
            "D. 全民守法",
        ]
        ans = self.bank.match_answers(q, page)
        self.assertTrue(ans.ok)
        self.assertEqual(sorted(ans.indices), [1, 2, 3])

    def test_judgment(self):
        q = self.bank.questions[2]
        page = ["B. 错误", "A. 正确"]
        ans = self.bank.match_answers(q, page)
        self.assertTrue(ans.ok)
        self.assertEqual(ans.indices, [1])

    def test_fuzzy_question_and_ocr_noise(self):
        page_stem = "1、全面依法治国 要坚持什么?"
        page_opts = [
            "D. 仅依靠道德教化",
            "A. 坚持依法治国和以德治国相结合",
            "C. 只依靠群众运动",
            "B. 放弃党的领导",
        ]
        m = self.bank.find_question(page_stem, page_opts)
        self.assertIsNotNone(m.question)
        self.assertEqual(m.question.no, 1)
        self.assertGreater(m.score, 80)

    def test_answer_content_without_letters(self):
        q = BankQuestion(
            4, "全面依法治国要坚持什么？", "坚持依法治国和以德治国相结合", "单选题",
            {"A": "坚持依法治国和以德治国相结合", "B": "放弃党的领导"},
        )
        b = Bank([q])
        ans = b.match_answers(q, ["B. 放弃党的领导", "A. 坚持依法治国和以德治国相结合"])
        self.assertTrue(ans.ok)
        self.assertEqual(ans.indices, [1])

    def test_answer_content_with_commas_is_not_split_when_it_is_one_option(self):
        q = BankQuestion(
            9, "全面依法治国要坚持什么？",
            "坚持依法治国、以德治国相结合", "单选题",
            {"A": "坚持依法治国、以德治国相结合", "B": "只依靠道德教化"},
        )
        b = Bank([q])
        ans = b.match_answers(q, ["B. 只依靠道德教化", "A. 坚持依法治国、以德治国相结合"])
        self.assertTrue(ans.ok)
        self.assertEqual(ans.indices, [1])

    def test_answer_letters_with_separators(self):
        q = BankQuestion(
            5, "下列哪些属于全面依法治国的要求？", "A、C", "多选题",
            {"A": "科学立法", "B": "只强调效率", "C": "严格执法", "D": "放弃党的领导"},
        )
        b = Bank([q])
        ans = b.match_answers(q, ["C. 严格执法", "B. 只强调效率", "A. 科学立法", "D. 放弃党的领导"])
        self.assertTrue(ans.ok)
        self.assertEqual(sorted(ans.indices), [0, 2])

    def test_duplicate_stem_uses_options(self):
        q1 = BankQuestion(
            6, "下列说法正确的是？", "A", "单选题",
            {"A": "科学立法", "B": "只强调效率"},
        )
        q2 = BankQuestion(
            7, "下列说法正确的是？", "B", "单选题",
            {"A": "只强调效率", "B": "严格执法"},
        )
        b = Bank([q1, q2])
        m = b.find_question("下列说法正确的是？", ["A. 只强调效率", "B. 严格执法"])
        self.assertIsNotNone(m.question)
        self.assertEqual(m.question.no, 7)

    def test_missing_option_text_does_not_guess(self):
        q = BankQuestion(8, "全面依法治国要坚持什么？", "A", "单选题", {})
        b = Bank([q])
        ans = b.match_answers(q, ["D. 仅依靠道德教化", "A. 坚持依法治国和以德治国相结合"])
        self.assertFalse(ans.ok)
        self.assertIn("缺少选项原文", ans.reason)

    def test_excel_options_with_punctuated_headers(self):
        try:
            from openpyxl import Workbook
        except Exception:
            self.skipTest("openpyxl not installed")
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            wb = Workbook()
            ws = wb.active
            ws.append(["题目", "答案", "A.", "B、", "C：", "D"])
            ws.append([
                "全面依法治国要坚持什么？", "A",
                "坚持依法治国和以德治国相结合", "放弃党的领导",
                "只依靠群众运动", "仅依靠道德教化",
            ])
            wb.save(path)
            b = Bank.load(path)
            self.assertEqual(len(b), 1)
            self.assertEqual(
                b.questions[0].options.get("A"),
                "坚持依法治国和以德治国相结合",
            )
            ans = b.match_answers(b.questions[0], [
                "D. 仅依靠道德教化", "A. 坚持依法治国和以德治国相结合",
            ])
            self.assertTrue(ans.ok)
            self.assertEqual(ans.indices, [1])
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    def test_option_letter_requires_separator_or_parentheses(self):
        from bank import option_letter
        self.assertEqual(option_letter("A. 坚持依法治国"), "A")
        self.assertEqual(option_letter("B、放弃党的领导"), "B")
        self.assertEqual(option_letter("(C) 只依靠群众运动"), "C")
        self.assertEqual(option_letter("（D）仅依靠道德教化"), "D")
        self.assertIsNone(option_letter("Apple juice"))
        self.assertIsNone(option_letter("坚持依法治国"))

    def test_incomplete_letter_options_are_skipped(self):
        q = BankQuestion(
            10, "下列哪些属于全面依法治国的要求？", "AB", "多选题",
            {"A": "科学立法"},
        )
        b = Bank([q])
        ans = b.match_answers(q, ["A. 科学立法", "B. 严格执法"])
        self.assertFalse(ans.ok)
        self.assertIn("不完整", ans.reason)

    def test_excel_options(self):
        try:
            from openpyxl import Workbook
        except Exception:
            self.skipTest("openpyxl not installed")
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        try:
            wb = Workbook()
            ws = wb.active
            ws.append(["题目", "答案", "A", "B", "C", "D"])
            ws.append([
                "全面依法治国要坚持什么？", "A",
                "坚持依法治国和以德治国相结合", "放弃党的领导",
                "只依靠群众运动", "仅依靠道德教化",
            ])
            wb.save(path)
            b = Bank.load(path)
            self.assertEqual(len(b), 1)
            self.assertTrue(b.questions[0].options)
            ans = b.match_answers(b.questions[0], [
                "D. 仅依靠道德教化", "A. 坚持依法治国和以德治国相结合",
            ])
            self.assertTrue(ans.ok)
            self.assertEqual(ans.indices, [1])
        finally:
            try:
                os.remove(path)
            except Exception:
                pass


class RealBankTests(unittest.TestCase):
    def test_word_bank_retains_options_if_present(self):
        paths = glob.glob(os.path.join(TIKU, "2023*.docx"))
        if not paths:
            self.skipTest("2023 docx not found")
        b = Bank.load(paths[0])
        self.assertGreater(len(b), 1000)
        self.assertGreater(b.with_options, 1000)

    def test_pdf_bank_retains_options_if_present(self):
        paths = glob.glob(os.path.join(TIKU, "2025*.pdf"))
        if not paths:
            self.skipTest("2025 pdf not found")
        b = Bank.load(paths[0])
        self.assertGreater(len(b), 500)
        self.assertGreater(b.with_options, 500)


if __name__ == "__main__":
    unittest.main(verbosity=2)
