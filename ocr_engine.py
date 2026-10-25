#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地中文 OCR 封装（RapidOCR / onnxruntime）。

仅当网页题干或选项不是文字（图片、背景图、canvas）时调用。
"""

from __future__ import annotations

import hashlib
import io
import re
try:
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover
    Image = None


class OcrError(RuntimeError):
    pass


class OcrReader:
    def __init__(self) -> None:
        self._engine = None
        self._cache = {}
        self._failed = False

    @property
    def available(self) -> bool:
        return not self._failed

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        if self._failed:
            raise OcrError("OCR 初始化失败")
        try:
            from rapidocr_onnxruntime import RapidOCR
        except Exception as e:
            self._failed = True
            raise OcrError("未安装 rapidocr-onnxruntime，无法识别图片题：%s" % e)
        try:
            self._engine = RapidOCR()
        except Exception as e:
            self._failed = True
            raise OcrError("OCR 初始化失败：%s" % e)
        return self._engine

    def read_image(self, image) -> str:
        """image 可以是 bytes、PIL.Image。返回按阅读顺序拼接的文字。"""
        if Image is None:
            raise OcrError("缺少 Pillow，无法处理图片")
        if isinstance(image, (bytes, bytearray)):
            img = Image.open(io.BytesIO(bytes(image)))
        elif isinstance(image, Image.Image):
            img = image
        else:
            raise OcrError("不支持的图片类型")

        key = hashlib.sha1(img.tobytes()).hexdigest()
        if key in self._cache:
            return self._cache[key]

        img = self._prepare(img)
        import numpy as np
        arr = np.array(img)
        engine = self._get_engine()
        try:
            result, _ = engine(arr)
        except Exception as e:
            raise OcrError("OCR 识别失败：%s" % e)
        lines = []
        if result:
            # result: [[box, text, score], ...]
            items = []
            for item in result:
                try:
                    box, text, score = item[0], item[1], float(item[2])
                except Exception:
                    continue
                if score < 0.25:
                    continue
                text = re.sub(r"\s+", " ", str(text)).strip()
                if not text:
                    continue
                try:
                    ys = [p[1] for p in box]
                    xs = [p[0] for p in box]
                    y = sum(ys) / len(ys)
                    x = sum(xs) / len(xs)
                except Exception:
                    y, x = 0, 0
                items.append((y, x, text, score))
            items.sort(key=lambda t: (round(t[0] / 8.0), t[1]))
            lines = [t[2] for t in items]
        text = "\n".join(lines).strip()
        self._cache[key] = text
        return text

    @staticmethod
    def _prepare(img):
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
            img = Image.alpha_composite(bg, img).convert("RGB")
        else:
            img = img.convert("RGB")
        w, h = img.size
        if w < 20 or h < 12:
            scale = max(20.0 / max(w, 1), 12.0 / max(h, 1), 2.0)
        else:
            scale = 1.0
        if w < 900:
            scale = max(scale, min(3.0, 900.0 / max(w, 1)))
        if scale > 1.01:
            img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        # 加白边，避免文字贴边
        img = ImageOps.expand(img, border=12, fill="white")
        # 轻微增强对比度
        try:
            img = ImageOps.autocontrast(img, cutoff=1)
        except Exception:
            pass
        return img


def clean_ocr_text(text: str) -> str:
    if not text:
        return ""
    lines = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        # 去掉 OCR 常见的孤立噪声
        if len(line) == 1 and line not in "ABCDEFG对错":
            continue
        lines.append(line)
    return " ".join(lines).strip()
