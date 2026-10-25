#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用题库加载与内容匹配。

设计原则：
1. 题库里的 A/B/C/D 只用于定位选项原文，最终必须把“答案内容”匹配到
   网页上实际选项的内容。
2. 网页选项顺序、字母前缀、标点、空格变化都不影响匹配。
3. OCR 文本允许一定误差，使用模糊匹配并保留置信度。
"""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import pandas as pd
except Exception:  # pragma: no cover - 只在缺少依赖时触发
    pd = None

try:
    from rapidfuzz import fuzz, process
except Exception:  # pragma: no cover
    fuzz = None
    process = None


LETTERS = "ABCDEFG"
LETTER_SET = set(LETTERS)
TRUE_WORDS = ("正确", "对", "是", "true", "yes", "√", "✓", "t")
FALSE_WORDS = ("错误", "错", "否", "false", "no", "×", "✗", "f", "不对")

STEM_COLUMNS = (
    "题目", "题干", "问题", "试题", "题目内容", "question", "stem",
    "title", "content", "name",
)
ANSWER_COLUMNS = (
    "答案", "正确答案", "标准答案", "answer", "key", "correctanswer",
)
TYPE_COLUMNS = ("题型", "类型", "题目类型", "qtype", "type")
OPTION_COLUMN_RE = re.compile(
    r"^(?:选项\s*)?([A-GＡ-Ｇ])(?:\s*选项)?\s*[、.．:：]?$", re.IGNORECASE
)


def normalize_text(text: object) -> str:
    """用于匹配的强归一化：只保留汉字、字母、数字。"""
    if text is None:
        return ""
    s = unicodedata.normalize("NFKC", str(text)).lower()
    s = s.replace("　", " ")
    # 去掉常见 OCR/网页符号，保留中英文和数字
    s = re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", s)
    return s


def clean_display(text: object) -> str:
    if text is None:
        return ""
    s = unicodedata.normalize("NFKC", str(text))
    s = re.sub(r"\s+", " ", s).strip()
    return s


def strip_option_prefix(text: object) -> str:
    """去掉网页/OCR 选项前的 A. / A、 / (A) 等前缀。"""
    s = clean_display(text)
    if not s:
        return ""
    s2 = re.sub(
        r"^\s*[\(（]?\s*[A-GＡ-Ｇ]\s*[\)）]?\s*[、.．:：\-—]\s*",
        "",
        s,
    )
    if s2 != s and s2.strip():
        return s2.strip()
    # OCR 有时输出 "A 选项内容"（没有点号）
    s2 = re.sub(r"^\s*[A-GＡ-Ｇ]\s+", "", s, count=1)
    if s2 != s and len(s2.strip()) >= 2:
        return s2.strip()
    return s


def option_letter(text: object) -> Optional[str]:
    s = clean_display(text)
    letter_map = str.maketrans("ＡＢＣＤＥＦＧ", "ABCDEFG")
    # “A. 内容”“A、内容”等明确带分隔符的前缀
    m = re.match(r"^[\(（]?\s*([A-GＡ-Ｇ])\s*[\)）]?\s*[、.．:：\-—]", s)
    if m:
        return m.group(1).translate(letter_map)
    # “(A) 内容”：括号包裹也算选项前缀
    m = re.match(r"^[\(（]\s*([A-GＡ-Ｇ])\s*[\)）]", s)
    if m:
        return m.group(1).translate(letter_map)
    return None


def split_answer_text(answer: object) -> List[str]:
    s = clean_display(answer)
    if not s:
        return []
    s = re.sub(r"^(?:正确答案|答案|answer|key)\s*[:：]\s*", "", s, flags=re.I)
    # 判断题特殊处理
    if s in ("√", "✓", "对", "正确", "T", "True", "true", "是"):
        return ["正确"]
    if s in ("×", "✗", "错", "错误", "F", "False", "false", "否"):
        return ["错误"]
    if re.fullmatch(r"[A-GＡ-Ｇ]{1,8}", s.replace(" ", "")):
        return []  # 由 letter 分支处理
    parts = [p.strip() for p in re.split(r"[、,，;；/|]", s) if p.strip()]
    return parts if parts else [s]


def judgment_value(text: object) -> Optional[str]:
    s = normalize_text(text)
    if not s:
        return None
    # 先判断否定词，避免“不正确”被当成“正确”
    if any(w in s for w in ("不正确", "不对", "错误", "错", "false", "no", "×", "✗")):
        return "错误"
    if any(w in s for w in ("正确", "对", "是", "true", "yes", "√", "✓")):
        return "正确"
    if s in ("t", "f"):
        return "正确" if s == "t" else "错误"
    return None


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if fuzz is None:
        import difflib
        return difflib.SequenceMatcher(None, a, b).ratio() * 100.0
    r = float(fuzz.ratio(a, b))
    p = float(fuzz.partial_ratio(a, b))
    t = float(fuzz.token_set_ratio(a, b))
    len_ratio = min(len(a), len(b)) / max(len(a), len(b))
    # 长度差异很大时，partial_ratio 容易虚高
    if len_ratio < 0.45:
        p *= 0.88
        t *= 0.90
    return max(r, p * 0.985, t * 0.965)


def text_score(a: object, b: object) -> float:
    return _ratio(normalize_text(a), normalize_text(b))


@dataclass
class BankQuestion:
    no: int
    stem: str
    answer: str
    qtype: str = ""
    options: Dict[str, str] = field(default_factory=dict)
    note: str = ""
    source: str = ""

    norm_stem: str = ""
    answer_letters: str = ""
    answer_texts: List[str] = field(default_factory=list)
    judgment: Optional[str] = None
    has_option_texts: bool = False

    def __post_init__(self) -> None:
        self.stem = clean_display(self.stem)
        self.answer = clean_display(self.answer)
        self.options = {
            str(k).upper().translate(str.maketrans("ＡＢＣＤＥＦＧ", "ABCDEFG")): clean_display(v)
            for k, v in (self.options or {}).items()
            if str(k).strip() and clean_display(v)
        }
        self.norm_stem = normalize_text(self.stem)
        self.has_option_texts = bool(self.options)
        letter_probe = re.sub(r"[\s、,，;；/|]+", "", self.answer.upper())
        letters = re.sub(r"[^A-G]", "", letter_probe)
        if letters and re.fullmatch(r"[A-G]{1,8}", letter_probe):
            self.answer_letters = letters
        self.judgment = judgment_value(self.answer)
        if self.judgment is None and self.qtype and "判断" in self.qtype:
            self.judgment = judgment_value(self.answer)
        if self.answer_letters:
            self.answer_texts = [
                self.options[ch] for ch in self.answer_letters if ch in self.options
            ]
        else:
            self.answer_texts = split_answer_text(self.answer)
            # 答案内容本身可能带逗号/顿号，且正好是某一个完整选项。
            # 这种情况下不能把它拆成多个答案去匹配多个选项。
            if len(self.answer_texts) > 1 and self.options:
                whole = normalize_text(self.answer)
                for v in self.options.values():
                    if whole and (whole == normalize_text(v) or text_score(whole, v) >= 92):
                        self.answer_texts = [self.answer]
                        break
        if not self.qtype:
            if self.judgment:
                self.qtype = "判断题"
            elif len(self.answer_letters) > 1:
                self.qtype = "多选题"
            elif self.answer_letters:
                self.qtype = "单选题"
            elif len(self.answer_texts) > 1:
                self.qtype = "多选题"
            else:
                self.qtype = "其他"

    @property
    def answer_missing(self) -> bool:
        return not self.answer

    @property
    def can_match_by_content(self) -> bool:
        if self.judgment:
            return True
        return bool(self.answer_texts)

    def option_text(self, letter: str) -> str:
        return self.options.get(letter, "")


@dataclass
class MatchResult:
    question: Optional[BankQuestion]
    score: float = 0.0
    option_score: float = 0.0
    indices: List[int] = field(default_factory=list)
    option_scores: List[float] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.question is not None and bool(self.indices)


class Bank:
    def __init__(self, questions: Sequence[BankQuestion], path: str = "", warnings: Optional[Sequence[str]] = None):
        self.path = path
        self.questions: List[BankQuestion] = list(questions)
        self.warnings: List[str] = list(warnings or [])
        self._exact: Dict[str, List[int]] = {}
        for i, q in enumerate(self.questions):
            if q.norm_stem:
                self._exact.setdefault(q.norm_stem, []).append(i)
        self._choices = [q.norm_stem for q in self.questions]

    def __len__(self) -> int:
        return len(self.questions)

    @property
    def name(self) -> str:
        return os.path.basename(self.path) if self.path else "题库"

    @property
    def with_options(self) -> int:
        return sum(1 for q in self.questions if q.options)

    @classmethod
    def load(cls, path: str) -> "Bank":
        ext = os.path.splitext(path)[1].lower()
        if ext in (".xlsx", ".xls", ".xlsm", ".csv"):
            return cls._load_table(path)
        if ext in (".docx", ".doc", ".wps", ".pdf", ".txt"):
            return cls._load_parser(path)
        # 尝试按表格读取
        try:
            return cls._load_table(path)
        except Exception:
            return cls._load_parser(path)

    @classmethod
    def _load_table(cls, path: str) -> "Bank":
        if pd is None:
            raise RuntimeError("缺少 pandas/openpyxl，无法读取 Excel 题库")
        ext = os.path.splitext(path)[1].lower()
        if ext == ".csv":
            last_error = None
            for enc in ("utf-8-sig", "gbk", "utf-8"):
                try:
                    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding=enc)
                    break
                except UnicodeDecodeError as e:
                    last_error = e
                    continue
            else:
                raise ValueError("CSV 编码无法识别：%s" % last_error)
        else:
            df = pd.read_excel(path, dtype=str, keep_default_na=False)
        if df is None or df.empty:
            raise ValueError("题库表格为空")

        raw_cols = [str(c).strip() for c in df.columns]
        df.columns = raw_cols
        norm_map = {c: normalize_text(c) for c in raw_cols}

        def find(cands: Iterable[str]) -> Optional[str]:
            for cand in cands:
                nc = normalize_text(cand)
                for col, n in norm_map.items():
                    if n == nc:
                        return col
            for cand in cands:
                nc = normalize_text(cand)
                for col, n in norm_map.items():
                    if nc and nc in n:
                        return col
            return None

        stem_col = find(STEM_COLUMNS)
        answer_col = find(ANSWER_COLUMNS)
        type_col = find(TYPE_COLUMNS)
        if not stem_col or not answer_col:
            raise ValueError("Excel 题库至少需要“题目”和“答案”两列，当前列：%s" %
                             "、".join(raw_cols))

        option_cols: Dict[str, str] = {}
        for col in raw_cols:
            m = OPTION_COLUMN_RE.match(col.strip())
            if m:
                letter = m.group(1).translate(str.maketrans("ＡＢＣＤＥＦＧ", "ABCDEFG")).upper()
                option_cols.setdefault(letter, col)
        # “选项A”这种列名
        for col in raw_cols:
            n = normalize_text(col)
            if n in ("a", "b", "c", "d", "e", "f", "g"):
                option_cols.setdefault(n.upper(), col)

        questions: List[BankQuestion] = []
        warnings: List[str] = []
        for idx, row in df.iterrows():
            stem = clean_display(row.get(stem_col, ""))
            if not stem:
                continue
            answer = clean_display(row.get(answer_col, ""))
            qtype = clean_display(row.get(type_col, "")) if type_col else ""
            opts = {
                letter: clean_display(row.get(col, ""))
                for letter, col in option_cols.items()
                if clean_display(row.get(col, ""))
            }
            if not answer:
                warnings.append("第 %d 行缺少答案：%s" % (idx + 2, stem[:38]))
            q = BankQuestion(
                no=len(questions) + 1,
                stem=stem,
                answer=answer,
                qtype=qtype,
                options=opts,
                note="",
                source=os.path.basename(path),
            )
            questions.append(q)
        if not questions:
            raise ValueError("题库中没有有效题目")
        if not option_cols:
            warnings.append(
                "该 Excel 只有题目/答案，没有 A-G 选项原文列；"
                "选项乱序时无法按内容匹配，建议用 Word/PDF 重新导入或补充选项列。"
            )
        return cls(questions, path=path, warnings=warnings)

    @classmethod
    def _load_parser(cls, path: str) -> "Bank":
        try:
            import tiku_parser
        except Exception:
            # 允许从其他目录 import
            import sys
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import tiku_parser
        data = tiku_parser.parse_file(path)
        questions: List[BankQuestion] = []
        warnings: List[str] = []
        for q in data.get("questions", []):
            stem = clean_display(q.get("stem", ""))
            if not stem:
                continue
            item = BankQuestion(
                no=int(q.get("no") or len(questions) + 1),
                stem=stem,
                answer=clean_display(q.get("answer", "")),
                qtype=clean_display(q.get("qtype", "")),
                options=dict(q.get("options") or {}),
                note=clean_display(q.get("note", "")),
                source=os.path.basename(path),
            )
            if item.answer_missing:
                warnings.append("第 %s 题缺少答案：%s" % (item.no, stem[:38]))
            questions.append(item)
        if not questions:
            raise ValueError("题库文件中没有解析到题目")
        no_opt = sum(1 for q in questions if not q.options)
        if no_opt:
            warnings.append(
                "%d 道题没有可识别的选项原文；这些题若答案只有字母，"
                "将无法在选项乱序时匹配。" % no_opt
            )
        return cls(questions, path=path, warnings=warnings)

    def stats_text(self) -> str:
        missing = sum(1 for q in self.questions if q.answer_missing)
        return "题库：%d 题，含选项原文 %d 题，缺答案 %d 题" % (
            len(self.questions), self.with_options, missing
        )

    # ------------------------------------------------------------------
    # 题目匹配
    # ------------------------------------------------------------------
    def find_question(
        self,
        page_stem: str,
        page_options: Optional[Sequence[str]] = None,
        min_score: float = 80.0,
    ) -> MatchResult:
        page_stem = clean_display(page_stem)
        if not page_stem:
            return MatchResult(None, reason="网页题干为空")
        norm = normalize_text(page_stem)
        if not norm:
            return MatchResult(None, reason="网页题干没有可匹配文字")

        candidate_ids: List[int] = []
        exact = self._exact.get(norm, [])
        if exact:
            candidate_ids = list(exact)
        else:
            candidate_ids = self._fuzzy_candidates(norm, limit=12)
        if not candidate_ids:
            return MatchResult(None, reason="题库中没有相近题目")

        page_opts = [strip_option_prefix(x) for x in (page_options or []) if clean_display(x)]
        best: Optional[Tuple[float, float, int]] = None
        for idx in candidate_ids:
            q = self.questions[idx]
            score = _ratio(norm, q.norm_stem)
            opt_score = self._option_set_score(q, page_opts) if page_opts else 0.0
            combined = score + (opt_score * 0.035 if page_opts else 0.0)
            if best is None or combined > best[0]:
                best = (combined, score, idx)
        if best is None:
            return MatchResult(None, reason="题库中没有相近题目")
        combined, score, idx = best
        q = self.questions[idx]
        opt_score = self._option_set_score(q, page_opts) if page_opts else 0.0
        # 精确题干直接通过；否则要求模糊分数线
        if not exact and score < min_score:
            return MatchResult(
                q, score=score, option_score=opt_score,
                reason="题干相似度 %.1f 低于阈值 %.1f" % (score, min_score),
            )
        return MatchResult(q, score=score, option_score=opt_score)

    def _fuzzy_candidates(self, norm: str, limit: int = 12) -> List[int]:
        if not norm:
            return []
        if process is not None and fuzz is not None and len(self.questions) > 20:
            try:
                hits = process.extract(
                    norm, self._choices, scorer=fuzz.WRatio, limit=limit,
                    score_cutoff=45,
                )
                out = []
                for _, _, idx in hits:
                    if isinstance(idx, int) and 0 <= idx < len(self.questions):
                        out.append(idx)
                if out:
                    return out
            except Exception:
                pass
        scored = []
        for i, q in enumerate(self.questions):
            if not q.norm_stem:
                continue
            s = _ratio(norm, q.norm_stem)
            if s >= 45:
                scored.append((s, i))
        scored.sort(reverse=True)
        return [i for _, i in scored[:limit]]

    @staticmethod
    def _option_set_score(q: BankQuestion, page_opts: Sequence[str]) -> float:
        if not q.options or not page_opts:
            return 0.0
        bank_opts = [strip_option_prefix(v) for v in q.options.values() if v]
        if not bank_opts:
            return 0.0
        scores = []
        for po in page_opts:
            scores.append(max((text_score(po, bo) for bo in bank_opts), default=0.0))
        # 取前 min(4, 选项数) 个平均值，避免无关选项拉低
        scores.sort(reverse=True)
        top = scores[:min(4, len(scores))]
        return sum(top) / len(top) if top else 0.0

    # ------------------------------------------------------------------
    # 答案匹配
    # ------------------------------------------------------------------
    def match_answers(
        self,
        q: BankQuestion,
        page_options: Sequence[str],
        min_option_score: float = 58.0,
        ocr: bool = False,
    ) -> MatchResult:
        opts = [clean_display(x) for x in page_options]
        stripped = [strip_option_prefix(x) for x in opts]
        if not stripped:
            return MatchResult(q, reason="网页没有可识别的选项文字")

        if q.answer_missing:
            return MatchResult(q, reason="题库中该题答案为空，已跳过")
        if q.answer_letters and q.options and any(ch not in q.options for ch in q.answer_letters):
            return MatchResult(q, reason="题库答案字母对应的选项原文不完整，已跳过")
        if not q.can_match_by_content:
            return MatchResult(
                q,
                reason="题库该题缺少选项原文，无法按内容匹配（请用带选项的题库重新导入）",
            )

        warnings: List[str] = []
        if ocr:
            min_option_score = min(min_option_score, 52.0)

        # 判断题：直接找“正确/错误”选项
        if q.judgment:
            idx = self._judgment_index(stripped, q.judgment)
            if idx is None:
                return MatchResult(q, reason="未找到与“%s”对应的判断选项" % q.judgment)
            score = text_score(stripped[idx], q.judgment)
            return MatchResult(q, option_score=score, indices=[idx],
                               option_scores=[score], warnings=warnings,
                               reason="判断题按内容匹配")

        targets = [strip_option_prefix(t) for t in q.answer_texts if clean_display(t)]
        if not targets:
            return MatchResult(
                q,
                reason="题库答案只有字母但缺少选项原文，无法在选项乱序时安全匹配",
            )

        # 多选/单选统一：每个答案内容找最相似的网页选项
        used = set()
        indices: List[int] = []
        scores: List[float] = []
        for target in targets:
            best_idx = None
            best_score = -1.0
            for i, opt in enumerate(stripped):
                if i in used:
                    continue
                s = text_score(target, opt)
                # 选项文本通常包含前缀和额外说明，partial 已经计入
                if s > best_score:
                    best_score, best_idx = s, i
            if best_idx is None or best_score < min_option_score:
                warnings.append(
                    "答案内容“%s”未匹配到选项（最高 %.1f）" % (target[:24], max(best_score, 0))
                )
                continue
            used.add(best_idx)
            indices.append(best_idx)
            scores.append(best_score)

        if not indices:
            return MatchResult(q, option_score=max(scores) if scores else 0.0,
                               warnings=warnings, reason="答案内容与网页选项都不匹配")

        # 单选题只保留最高分，防止题库答案意外包含多个内容
        if len(indices) > 1 and q.qtype in ("单选题", "判断题"):
            best_pos = max(range(len(scores)), key=lambda i: scores[i])
            indices = [indices[best_pos]]
            scores = [scores[best_pos]]

        return MatchResult(
            q, option_score=max(scores) if scores else 0.0,
            indices=indices, option_scores=scores, warnings=warnings,
            reason="按选项内容匹配",
        )

    @staticmethod
    def _judgment_index(options: Sequence[str], truth: str) -> Optional[int]:
        scores = []
        for i, opt in enumerate(options):
            val = judgment_value(opt)
            if val == truth:
                # 越短越像专门的判断选项
                scores.append((1000 - len(normalize_text(opt)), i))
        if scores:
            scores.sort(reverse=True)
            return scores[0][1]
        # 退化为内容相似度
        best = None
        for i, opt in enumerate(options):
            s = text_score(opt, truth)
            if best is None or s > best[0]:
                best = (s, i)
        return best[1] if best and best[0] >= 55 else None


def load_bank(path: str) -> Bank:
    return Bank.load(path)
