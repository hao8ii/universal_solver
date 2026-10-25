#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用网页答题引擎（Selenium）。

流程：
1. 启动 Chrome/Edge，打开用户给的网址；
2. 尝试通用账号/密码登录；失败或遇验证码时，用户可在已打开的浏览器中手动登录；
3. 轮询当前页，发现题目后扫描题目和选项；
4. 用题库按“题干内容 + 选项内容”匹配，不依赖选项字母顺序；
5. 题干/选项是图片时，对元素截图并用本地 OCR 识别；
6. 当前页答完后自动点击“下一题/下一页”，但绝不自动点击“提交/交卷”。
"""

from __future__ import annotations

import copy
import hashlib
import io
import os
import re
import sys
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchFrameException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By

from bank import Bank, normalize_text
from ocr_engine import OcrError, OcrReader, clean_ocr_text

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None


HERE = os.path.dirname(os.path.abspath(__file__))


def app_data_dir() -> str:
    """持久化数据（浏览器配置、config.json）所在目录。

    打包成 exe 后，JS 等运行时资源仍在解压目录（HERE），但登录状态等
    需要跨次启动保留的数据必须放在 exe 旁边，而不是每次运行都变化的临时目录。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return HERE


@dataclass
class EngineConfig:
    url: str = ""
    username: str = ""
    password: str = ""
    browser: str = "chrome"
    headless: bool = False
    ocr: bool = True
    min_question_score: float = 78.0
    min_option_score: float = 56.0
    wait_login_seconds: int = 600
    max_pages: int = 200
    profile_dir: str = os.path.join(app_data_dir(), "browser_profile")


class StopRequested(Exception):
    pass


class UniversalEngine:
    def __init__(
        self,
        bank: Bank,
        config: EngineConfig,
        log_callback: Optional[Callable[[str, str], None]] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        answered_callback: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self.bank = bank
        self.config = config
        self.log_callback = log_callback or (lambda msg, level="info": None)
        self.status_callback = status_callback or (lambda msg: None)
        self.answered_callback = answered_callback or (lambda data: None)

        self.driver: Optional[webdriver.Chrome] = None
        self.stop_event = __import__("threading").Event()
        self.start_now_event = __import__("threading").Event()
        self.running = False

        self.scan_js = self._read_js("scanner.js")
        self.actions_js = self._read_js("actions.js")
        self.login_js = self._read_js("login.js")
        self.ocr = OcrReader() if config.ocr else None
        self._ocr_failed = False
        self._ocr_announced = False
        self._ocr_warned = False
        self._seen_frames: List[Tuple[int, ...]] = []
        self._last_error = ""

    # ------------------------------------------------------------------
    # 基础设施
    # ------------------------------------------------------------------
    @staticmethod
    def _read_js(name: str) -> str:
        path = os.path.join(HERE, name)
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def log(self, msg: str, level: str = "info") -> None:
        try:
            self.log_callback(str(msg), level)
        except Exception:
            pass

    def status(self, msg: str) -> None:
        try:
            self.status_callback(str(msg))
        except Exception:
            pass

    def _check_stop(self) -> None:
        if self.stop_event.is_set():
            raise StopRequested()

    def _sleep(self, seconds: float) -> None:
        end = time.time() + max(0.0, seconds)
        while time.time() < end:
            self._check_stop()
            time.sleep(min(0.12, max(0.02, end - time.time())))

    def stop(self) -> None:
        self.stop_event.set()
        self.log("收到停止指令，正在停止…", "warn")

    def close_browser(self) -> None:
        self.stop_event.set()
        d = self.driver
        self.driver = None
        if d is not None:
            try:
                d.quit()
            except Exception:
                pass

    def _launch_browser(self) -> None:
        self.status("正在启动浏览器…")
        browser = (self.config.browser or "chrome").strip().lower()
        headless = bool(self.config.headless)

        profile = self.config.profile_dir or os.path.join(app_data_dir(), "browser_profile")
        try:
            os.makedirs(profile, exist_ok=True)
        except Exception:
            pass

        if browser == "edge":
            from selenium.webdriver.edge.options import Options as EdgeOptions
            opts = EdgeOptions()
            exe = self._find_browser_path("edge")
            if exe:
                opts.binary_location = exe
            self._common_options(opts, profile, headless)
            self.log("启动 Edge%s…" % ("（无头）" if headless else ""))
            self.driver = webdriver.Edge(options=opts)
        else:
            from selenium.webdriver.chrome.options import Options as ChromeOptions
            opts = ChromeOptions()
            exe = self._find_browser_path("chrome")
            if exe:
                opts.binary_location = exe
                self.log("Chrome 路径：%s" % exe)
            self._common_options(opts, profile, headless)
            self.log("启动 Chrome%s…" % ("（无头）" if headless else ""))
            self.driver = webdriver.Chrome(options=opts)

        try:
            self.driver.set_page_load_timeout(60)
            self.driver.implicitly_wait(0)
        except Exception:
            pass
        try:
            self.driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"},
            )
        except Exception:
            pass
        self.log("浏览器已启动。", "ok")

    @staticmethod
    def _common_options(opts, profile: str, headless: bool) -> None:
        opts.add_argument("--start-maximized")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--disable-infobars")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        opts.add_argument("--disable-popup-blocking")
        opts.add_argument("--lang=zh-CN")
        opts.add_argument("--user-data-dir=%s" % profile)
        opts.add_argument("--profile-directory=Default")
        opts.add_argument("--disable-dev-shm-usage")
        if headless:
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1440,1200")
            opts.add_argument("--disable-gpu")
        try:
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
        except Exception:
            pass

    @staticmethod
    def _find_browser_path(kind: str) -> Optional[str]:
        local = os.environ.get("LOCALAPPDATA", "")
        pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        if kind == "chrome":
            paths = [
                os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
            ]
        else:
            paths = [
                os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
            ]
        for p in paths:
            if p and os.path.isfile(p):
                return p
        return None

    def _open_url(self) -> None:
        if self.driver is None:
            raise RuntimeError("浏览器尚未启动")
        url = (self.config.url or "").strip()
        if not url:
            self.log("网址为空，使用浏览器当前页面。", "warn")
            return
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
            url = "https://" + url
        self.status("正在打开网址…")
        self.log("打开：%s" % url)
        try:
            self.driver.get(url)
        except TimeoutException:
            self.log("页面加载超时，继续尝试识别当前页面。", "warn")
        except Exception as e:
            self.log("打开网址失败：%s" % e, "error")
            raise
        self._sleep(1.0)
        try:
            self.log("当前页面：%s ｜ %s" % (self.driver.title, self.driver.current_url))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 登录
    # ------------------------------------------------------------------
    def _inject_actions(self) -> None:
        try:
            self.driver.execute_script(self.actions_js + "\nreturn true;")
        except Exception:
            pass

    def _try_generic_login(self, allow_step: bool = True) -> None:
        if not self.config.username and not self.config.password:
            self.log("未填写账号/密码：请在已打开的浏览器中手动登录并进入答题页。")
            return
        try:
            self._inject_actions()
            self.driver.execute_script(self.actions_js + "\n" + self.login_js)
            info = self.driver.execute_script("return window.__uatLoginResult || null")
        except Exception as e:
            self.log("登录页识别失败：%s" % e, "warn")
            return
        if not info or not info.get("found"):
            reason = (info or {}).get("reason", "没有找到账号密码登录框")
            if info and info.get("needs_step") and allow_step and self.config.username:
                self.log("检测到分步登录，先填写账号并点击下一步…")
                if info.get("user_id"):
                    self.driver.execute_script(
                        "return window.__uat_fill(arguments[0], arguments[1])",
                        info["user_id"], self.config.username,
                    )
                if info.get("submit_id"):
                    try:
                        self.driver.execute_script(
                            "return window.__uat_click(arguments[0])", info["submit_id"]
                        )
                    except Exception as e:
                        self.log("点击下一步失败：%s" % e, "warn")
                self._sleep(2.0)
                return self._try_generic_login(allow_step=False)
            self.log("%s；请手动登录，程序会继续等待答题页。" % reason, "warn")
            return

        self.log("检测到登录框，尝试自动填写…")
        if info.get("user_id") and self.config.username:
            ok = self.driver.execute_script(
                "return window.__uat_fill(arguments[0], arguments[1])",
                info["user_id"], self.config.username,
            )
            self.log("用户名已填写。" if ok else "用户名填写失败。", "ok" if ok else "warn")
        if info.get("pwd_id") and self.config.password:
            ok = self.driver.execute_script(
                "return window.__uat_fill(arguments[0], arguments[1])",
                info["pwd_id"], self.config.password,
            )
            self.log("密码已填写。" if ok else "密码填写失败。", "ok" if ok else "warn")
        if info.get("captcha"):
            self.log("检测到验证码/人机验证，请在浏览器中手动完成。", "warn")
        old_handles = []
        try:
            old_handles = list(self.driver.window_handles)
        except Exception:
            pass
        if info.get("submit_id"):
            try:
                self.driver.execute_script(
                    "return window.__uat_click(arguments[0])", info["submit_id"]
                )
                self.log("已点击登录按钮。", "ok")
            except Exception as e:
                self.log("点击登录按钮失败：%s" % e, "warn")
        else:
            self.log("未找到明确的登录按钮，请手动点击登录。", "warn")
        self._sleep(2.0)
        try:
            handles = list(self.driver.window_handles)
            if len(handles) > len(old_handles):
                self.driver.switch_to.window(handles[-1])
                self.log("登录后打开了新窗口，已切换过去。")
        except Exception:
            pass
        try:
            remains = self.driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]')
            visible = any(e.is_displayed() for e in remains)
            if visible:
                self.log("密码框仍在，可能需要验证码/短信验证，请在浏览器中完成登录。", "warn")
            else:
                self.log("登录表单已提交。", "ok")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 页面扫描
    # ------------------------------------------------------------------
    @contextmanager
    def _frame_context(self, frame_path: Sequence[int]):
        if self.driver is None:
            raise RuntimeError("浏览器尚未启动")
        self.driver.switch_to.default_content()
        try:
            for idx in frame_path or []:
                frames = self.driver.find_elements(By.CSS_SELECTOR, "iframe,frame")
                if idx < 0 or idx >= len(frames):
                    raise NoSuchFrameException("frame index %s" % idx)
                self.driver.switch_to.frame(frames[idx])
            yield
        finally:
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass

    def _scan_frame(self, frame_path: Tuple[int, ...], depth: int = 0) -> List[dict]:
        groups: List[dict] = []
        children: List[int] = []
        try:
            with self._frame_context(frame_path):
                self.driver.execute_script(self.scan_js)
                self.driver.execute_script(self.actions_js + "\nreturn true;")
                result = self.driver.execute_script("return window.__uatScanResult || null")
                if result and isinstance(result, dict):
                    groups = list(result.get("groups") or [])
                    for g in groups:
                        g["frame"] = list(frame_path)
                if not groups and depth < 2:
                    frames = self.driver.find_elements(By.CSS_SELECTOR, "iframe,frame")
                    for i, f in enumerate(frames[:20]):
                        try:
                            if f.is_displayed() and f.size.get("width", 0) >= 80 and f.size.get("height", 0) >= 40:
                                children.append(i)
                        except Exception:
                            continue
        except (NoSuchFrameException, StaleElementReferenceException):
            return []
        except WebDriverException as e:
            msg = str(e).splitlines()[0][:160]
            if "no such frame" not in msg.lower() and "detached" not in msg.lower():
                self.log("扫描页面失败：%s" % msg, "warn")
            return []
        except Exception as e:
            self.log("扫描页面异常：%s" % e, "warn")
            return []

        if groups:
            return groups
        for i in children:
            self._check_stop()
            groups.extend(self._scan_frame(frame_path + (i,), depth + 1))
            if groups:
                break
        return groups

    def scan_page(self, strict: bool = False) -> List[dict]:
        if self.driver is None:
            return []
        self._seen_frames = []
        try:
            frames = self.driver.find_elements(By.CSS_SELECTOR, "iframe,frame")
            for i, f in enumerate(frames[:20]):
                try:
                    if f.is_displayed():
                        self._seen_frames.append((i,))
                except Exception:
                    pass
        except Exception:
            pass
        groups = self._scan_frame((), 0)
        return self._meaningful_groups(groups, strict=strict)

    def _meaningful_groups(self, groups: Sequence[dict], strict: bool = False) -> List[dict]:
        out: List[dict] = []
        for g in groups or []:
            opts = g.get("options") or []
            if len(opts) < 2:
                continue
            has_text = any(normalize_text(o.get("text")) for o in opts)
            has_img = any(o.get("has_image") for o in opts)
            if not has_text and not has_img:
                continue
            # 题干为空但有选项文字，仍可能是“题干是图片”的题
            if not normalize_text(g.get("stem")) and not has_text and not has_img:
                continue
            out.append(g)
        # 初始等待阶段更严格，避免把登录身份选择/同意条款当成题目。
        # 答题循环中不能用这个规则，否则短题干（如“1+1=?”）会被漏掉。
        if strict and len(out) == 1:
            g = out[0]
            blob = normalize_text((g.get("stem") or "") + " " + " ".join(
                str(o.get("text", "")) for o in g.get("options", [])
            ))
            if any(k in blob for k in ("记住我", "自动登录", "同意协议", "已阅读", "登录身份", "验证码")):
                return []
            if len(normalize_text(g.get("stem"))) < 6 and not g.get("stem_has_image") and not any(
                o.get("has_image") for o in g.get("options", [])
            ):
                # 短题干可能真的是题（如“1+1=?”）；只有题库能匹配时才认。
                m = self.bank.find_question(
                    g.get("stem") or "",
                    [o.get("text") or "" for o in g.get("options", [])],
                    min_score=self.config.min_question_score,
                )
                if not m.question or m.score < self.config.min_question_score:
                    return []
        return out

    # ------------------------------------------------------------------
    # OCR
    # ------------------------------------------------------------------
    def _ocr_ready(self) -> bool:
        if not self.config.ocr or self.ocr is None or self._ocr_failed:
            return False
        try:
            return self.ocr.available
        except Exception:
            return False

    def _screenshot_tag(self, tag: Optional[str], frame_path: Sequence[int]) -> Optional[bytes]:
        if not tag or self.driver is None:
            return None
        try:
            with self._frame_context(frame_path):
                el = self.driver.execute_script(
                    "return (window.__uatEls || {})[arguments[0]] || null", tag
                )
                if el is None:
                    return None
                try:
                    return el.screenshot_as_png
                except Exception:
                    pass
                # 回退：整页截图后按元素位置裁剪
                try:
                    rect = self.driver.execute_script(
                        """
                        var e = (window.__uatEls || {})[arguments[0]];
                        if (!e) return null;
                        e.scrollIntoView({block:'center', inline:'center'});
                        var r = e.getBoundingClientRect();
                        return {x:r.left, y:r.top, w:r.width, h:r.height, dpr:window.devicePixelRatio||1};
                        """, tag
                    )
                    if not rect:
                        return None
                    time.sleep(0.15)
                    png = self.driver.get_screenshot_as_png()
                    if Image is None:
                        return png
                    img = Image.open(io.BytesIO(png))
                    dpr = float(rect.get("dpr") or 1)
                    x = max(0, int(rect["x"] * dpr))
                    y = max(0, int(rect["y"] * dpr))
                    w = max(1, int(rect["w"] * dpr))
                    h = max(1, int(rect["h"] * dpr))
                    if x >= img.width or y >= img.height:
                        return png
                    return self._png_bytes(img.crop((x, y, min(img.width, x + w), min(img.height, y + h))))
                except Exception:
                    return None
        except Exception:
            return None

    @staticmethod
    def _png_bytes(img) -> Optional[bytes]:
        if Image is None or img is None:
            return None
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def _ocr_png(self, png: Optional[bytes]) -> str:
        if not png or not self._ocr_ready():
            return ""
        if not self._ocr_announced:
            self._ocr_announced = True
            self.log("正在加载本地 OCR 模型（首次较慢）…")
        try:
            return clean_ocr_text(self.ocr.read_image(png))
        except OcrError as e:
            self._ocr_failed = True
            self.log("OCR 失败：%s" % e, "warn")
            return ""
        except Exception as e:
            self.log("OCR 异常：%s" % e, "warn")
            return ""

    def _rects_for(self, container_id: str, option_id: str, frame_path: Sequence[int]) -> Optional[dict]:
        if self.driver is None:
            return None
        try:
            with self._frame_context(frame_path):
                return self.driver.execute_script(
                    """
                    var c=(window.__uatEls||{})[arguments[0]];
                    var o=(window.__uatEls||{})[arguments[1]];
                    if (!c || !o) return null;
                    function r(e){var x=e.getBoundingClientRect();return {left:x.left,top:x.top,width:x.width,height:x.height};}
                    return {container:r(c), option:r(o)};
                    """, container_id, option_id
                )
        except Exception:
            return None

    def _ocr_stem(self, group: dict) -> str:
        frame = group.get("frame") or []
        stem_id = group.get("stem_id")
        container_id = group.get("container_id")
        first_opt = (group.get("options") or [{}])[0].get("id")
        texts: List[str] = []

        if stem_id and not group.get("stem_is_container"):
            t = self._ocr_png(self._screenshot_tag(stem_id, frame))
            if t:
                texts.append(t)
        if not texts and container_id:
            png = self._screenshot_tag(container_id, frame)
            if png and Image is not None:
                try:
                    img = Image.open(io.BytesIO(png))
                    rects = self._rects_for(container_id, first_opt, frame) if first_opt else None
                    if rects and rects.get("container") and rects.get("option"):
                        cw = max(1.0, float(rects["container"]["width"]))
                        scale = img.width / cw
                        cut = int((float(rects["option"]["top"]) - float(rects["container"]["top"])) * scale) - 6
                        if 24 < cut < img.height:
                            img = img.crop((0, 0, img.width, cut))
                    t = self._ocr_png(self._png_bytes(img))
                    if t:
                        texts.append(t)
                except Exception:
                    pass
        if not texts and stem_id and group.get("stem_is_container"):
            t = self._ocr_png(self._screenshot_tag(stem_id, frame))
            if t:
                texts.append(t)
        text = "\n".join(texts).strip()
        if not text:
            return ""
        # 去掉混进来的选项文字
        for o in group.get("options", []):
            ot = clean_ocr_text(o.get("text", ""))
            if len(normalize_text(ot)) >= 3:
                text = text.replace(ot, " ")
        lines = []
        for line in text.splitlines():
            line = re.sub(r"\s+", " ", line).strip()
            if not line:
                continue
            if re.match(r"^\s*[A-GＡ-Ｇ]\s*[、.．:：)]", line):
                continue
            lines.append(line)
        return clean_ocr_text(" ".join(lines))

    def _prepare_group(self, group: dict) -> dict:
        g = copy.deepcopy(group)
        g["ocr_used"] = False
        options = g.get("options") or []
        if self._ocr_ready():
            for o in options:
                text = o.get("text") or ""
                need = len(normalize_text(text)) < 2
                if need:
                    png = self._screenshot_tag(o.get("id"), g.get("frame") or [])
                    t = self._ocr_png(png)
                    if t:
                        if len(normalize_text(t)) > len(normalize_text(text)):
                            o["text"] = t
                        elif not text:
                            o["text"] = t
                        g["ocr_used"] = True
            if len(normalize_text(g.get("stem"))) < 3:
                t = self._ocr_stem(g)
                if t:
                    g["stem"] = t
                    g["ocr_used"] = True
        else:
            if any(len(normalize_text(o.get("text"))) < 1 for o in options) and not self._ocr_failed and not self._ocr_warned:
                self._ocr_warned = True
                self.log("有选项没有文字，但 OCR 未启用或不可用，可能无法作答。", "warn")
        return g

    # ------------------------------------------------------------------
    # 点击与翻页
    # ------------------------------------------------------------------
    def _click_tag(self, tag: str, frame_path: Sequence[int]) -> dict:
        if self.driver is None:
            return {"ok": False, "error": "browser not running"}
        try:
            with self._frame_context(frame_path):
                res = self.driver.execute_script(
                    "return window.__uat_click ? window.__uat_click(arguments[0]) : null", tag
                )
            return res or {"ok": False, "error": "no result"}
        except Exception as e:
            return {"ok": False, "error": str(e).splitlines()[0][:160]}

    def _state_tag(self, tag: str, frame_path: Sequence[int]) -> Optional[bool]:
        if self.driver is None:
            return None
        try:
            with self._frame_context(frame_path):
                return self.driver.execute_script(
                    "return window.__uat_state ? window.__uat_state(arguments[0]) : null", tag
                )
        except Exception:
            return None

    def _find_next_in_frame(self, frame_path: Sequence[int]) -> Optional[dict]:
        try:
            with self._frame_context(frame_path):
                res = self.driver.execute_script(
                    "return window.__uat_find_next ? window.__uat_find_next() : null"
                )
            if res and res.get("id"):
                res["frame"] = list(frame_path)
                return res
        except Exception:
            return None
        return None

    def _find_next(self, groups: Sequence[dict]) -> Optional[dict]:
        paths: List[Tuple[int, ...]] = []
        for g in groups:
            p = tuple(g.get("frame") or ())
            if p not in paths:
                paths.append(p)
        if () not in paths:
            paths.append(())
        for p in self._seen_frames:
            if p not in paths:
                paths.append(p)
        for p in paths:
            self._check_stop()
            res = self._find_next_in_frame(p)
            if res:
                return res
        # 有些按钮在页面底部懒加载
        try:
            with self._frame_context(()):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            self._sleep(0.6)
            for p in paths:
                res = self._find_next_in_frame(p)
                if res:
                    return res
        except Exception:
            pass
        return None

    def _signature(self, groups: Sequence[dict]) -> str:
        h = hashlib.md5()
        try:
            h.update((self.driver.current_url if self.driver else "").encode("utf-8", "ignore"))
        except Exception:
            pass
        for g in groups:
            h.update((",".join(str(x) for x in (g.get("frame") or []))).encode())
            h.update(normalize_text(g.get("stem")).encode("utf-8", "ignore"))
            h.update(str(g.get("stem_image_key") or "").encode("utf-8", "ignore"))
            for o in g.get("options") or []:
                h.update(normalize_text(o.get("text")).encode("utf-8", "ignore"))
                h.update(str(o.get("image_key") or "").encode("utf-8", "ignore"))
        return h.hexdigest()

    def _wait_for_change(self, old_sig: str, old_url: str, timeout: float = 18.0) -> List[dict]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._check_stop()
            self._sleep(0.6)
            groups = self.scan_page()
            try:
                url = self.driver.current_url if self.driver else ""
            except Exception:
                url = ""
            if groups and self._signature(groups) != old_sig:
                return groups
            if url and url != old_url and not groups:
                continue
        return []

    # ------------------------------------------------------------------
    # 答题
    # ------------------------------------------------------------------
    def _apply_selection(self, group: dict, indices: Sequence[int], qtype: str) -> Tuple[bool, str]:
        opts = group.get("options") or []
        frame = group.get("frame") or []
        desired = set(int(i) for i in indices if 0 <= int(i) < len(opts))
        if not desired:
            return False, "没有可点击的选项"
        messages = []
        # 多选题先取消不该选的已选项
        if qtype == "multiple":
            for i, o in enumerate(opts):
                if i in desired:
                    continue
                cur = self._state_tag(o.get("id"), frame)
                if cur is None:
                    cur = bool(o.get("checked"))
                if cur:
                    res = self._click_tag(o.get("id"), frame)
                    if not res.get("ok"):
                        messages.append("取消第%d项失败" % (i + 1))
                    self._sleep(0.08)
        # 点击目标选项
        for i in sorted(desired):
            o = opts[i]
            cur = self._state_tag(o.get("id"), frame)
            if cur is None:
                cur = bool(o.get("checked"))
            if cur:
                continue
            res = self._click_tag(o.get("id"), frame)
            if not res.get("ok") or res.get("after") is False:
                # 回退到内部 input
                iid = o.get("input_id")
                if iid:
                    res2 = self._click_tag(iid, frame)
                    if res2.get("ok"):
                        res = res2
            if not res.get("ok"):
                messages.append("点击第%d项失败：%s" % (i + 1, res.get("error", "")))
            self._sleep(0.12)
        # 验证
        states = []
        for i, o in enumerate(opts):
            st = self._state_tag(o.get("id"), frame)
            if st is None:
                st = bool(o.get("checked"))
            states.append(bool(st))
        ok = all(states[i] for i in desired)
        if not ok:
            messages.append("选择后校验未通过")
        return ok, "；".join(messages)

    def _answer_group(self, index: int, total: int, group: dict) -> dict:
        g = self._prepare_group(group)
        stem = g.get("stem") or ""
        opts = [o.get("text") or "" for o in g.get("options") or []]
        display_stem = re.sub(r"\s+", " ", stem).strip()
        if not display_stem:
            display_stem = "（图片题干/OCR 未识别）"
        if len(display_stem) > 70:
            display_stem = display_stem[:70] + "…"

        min_q_score = self.config.min_question_score
        if g.get("ocr_used"):
            min_q_score = min(min_q_score, 72.0)
        match = self.bank.find_question(stem, opts, min_score=min_q_score)
        if not match.question:
            self.log("第 %d/%d 题：未匹配到题库 ｜ %s ｜ %s" %
                     (index, total, display_stem, match.reason), "warn")
            return {"status": "unmatched", "stem": display_stem}
        q = match.question
        qlabel = "题库第%s题" % q.no
        if match.score < min_q_score:
            self.log("第 %d/%d 题：相似度不足（%.1f） ｜ %s ｜ %s" %
                     (index, total, match.score, display_stem, qlabel), "warn")
            return {"status": "low_score", "stem": display_stem, "score": match.score}
        # 有些题干非常通用（如“下列说法正确的是？”），只靠题干会匹配到
        # 另一道题。此时用网页选项与题库选项的整体相似度做二次校验。
        if q.options and len(opts) >= 2:
            min_opt_conf = 26.0 if g.get("ocr_used") else 32.0
            if match.option_score < min_opt_conf:
                self.log(
                    "第 %d/%d 题：题干相似但选项内容差异大（%.1f），为避免选错已跳过 ｜ %s ｜ %s" %
                    (index, total, match.option_score, display_stem, qlabel), "warn"
                )
                return {"status": "option_mismatch", "stem": display_stem,
                        "score": match.score, "option_score": match.option_score}
        if q.answer_missing:
            self.log("第 %d/%d 题：题库答案为空，跳过 ｜ %s ｜ %s" %
                     (index, total, display_stem, qlabel), "warn")
            return {"status": "missing_answer", "stem": display_stem}

        ans = self.bank.match_answers(
            q, opts,
            min_option_score=self.config.min_option_score,
            ocr=bool(g.get("ocr_used")),
        )
        if not ans.ok:
            self.log("第 %d/%d 题：%s ｜ %s ｜ %s" %
                     (index, total, ans.reason, display_stem, qlabel), "warn")
            for w in ans.warnings[:3]:
                self.log("    " + w, "warn")
            return {"status": "no_answer_match", "stem": display_stem, "question": q}
        # 多选题只要有一个正确项没匹配上，就不能少选后继续，否则必错。
        if "多选" in (q.qtype or "") and any("未匹配到选项" in w for w in ans.warnings):
            self.log("第 %d/%d 题：多选题有答案项未能匹配，已跳过以免少选 ｜ %s ｜ %s" %
                     (index, total, display_stem, qlabel), "warn")
            for w in ans.warnings[:3]:
                self.log("    " + w, "warn")
            return {"status": "partial_match", "stem": display_stem, "question": q}

        qtype = q.qtype or ""
        if "多选" not in qtype and (g.get("qtype") == "multiple" or len(ans.indices) > 1):
            qtype = "多选题"
        ok, msg = self._apply_selection(g, ans.indices, qtype)
        chosen = []
        for i in ans.indices:
            if 0 <= i < len(opts):
                txt = re.sub(r"\s+", " ", opts[i]).strip()
                chosen.append(txt[:42] + ("…" if len(txt) > 42 else ""))
        detail = "；".join(chosen)
        self.log(
            "第 %d/%d 题：匹配 %.1f 分 → 选择 [%s] ｜ %s ｜ %s%s%s" %
            (index, total, match.score, detail, display_stem, qlabel,
             (" ｜ OCR" if g.get("ocr_used") else ""),
             ("" if ok else " ｜ " + msg)),
            "ok" if ok else "warn",
        )
        for w in ans.warnings[:2]:
            self.log("    " + w, "warn")
        result = {
            "status": "answered" if ok else "click_failed",
            "stem": display_stem,
            "question": q,
            "score": match.score,
            "chosen": chosen,
            "ok": ok,
        }
        try:
            self.answered_callback(result)
        except Exception:
            pass
        return result

    def answer_current_page(self, groups: Sequence[dict]) -> List[dict]:
        results = []
        total = len(groups)
        for i, g in enumerate(groups, 1):
            self._check_stop()
            try:
                results.append(self._answer_group(i, total, g))
            except StopRequested:
                raise
            except Exception as e:
                self.log("第 %d 题处理异常：%s" % (i, e), "error")
                self.log(traceback.format_exc(limit=2), "debug")
        return results

    def _answer_loop(self, groups: List[dict]) -> None:
        page = 0
        total_answered = 0
        while groups:
            self._check_stop()
            page += 1
            if page > self.config.max_pages:
                self.log("已达到最大翻页数 %d，停止。" % self.config.max_pages, "warn")
                break
            self.status("正在答第 %d 页…" % page)
            self.log("—— 第 %d 页，共 %d 题 ——" % (page, len(groups)))
            old_sig = self._signature(groups)
            try:
                old_url = self.driver.current_url if self.driver else ""
            except Exception:
                old_url = ""

            results = self.answer_current_page(groups)
            total_answered += sum(1 for r in results if r.get("status") == "answered")
            self._check_stop()

            # 有些网站选完最后一项会自动跳下一页
            after_groups = self.scan_page()
            if after_groups and self._signature(after_groups) != old_sig:
                self.log("检测到页面已自动切换。", "info")
                groups = after_groups
                continue
            if not after_groups:
                # 自动跳页后新题可能还在加载，稍等再判断一次
                maybe = self._wait_for_change(old_sig, old_url, timeout=3.5)
                if maybe:
                    self.log("检测到页面已自动切换。", "info")
                    groups = maybe
                    continue

            nxt = self._find_next(groups)
            if not nxt:
                # 有些网站选完后延迟自动跳页；再等一会儿确认，避免误判为最后一页
                self._sleep(0.9)
                late_groups = self.scan_page()
                if late_groups and self._signature(late_groups) != old_sig:
                    self.log("检测到页面已自动切换。", "info")
                    groups = late_groups
                    continue
                self.log("本页已答完，没有找到“下一题/下一页”。请手动检查并提交。", "ok")
                self.status("已到最后一页，请手动提交")
                return
            self.log("点击：%s" % (nxt.get("text") or "下一页"))
            res = self._click_tag(nxt["id"], nxt.get("frame") or [])
            if not res.get("ok"):
                self.log("点击下一页失败：%s；停止。" % res.get("error", ""), "warn")
                self.status("翻页失败，请手动翻页")
                return
            new_groups = self._wait_for_change(old_sig, old_url)
            if not new_groups:
                self.log("点击下一页后没有检测到新题目，停止。请手动检查页面。", "warn")
                self.status("翻页后未检测到新题目")
                return
            groups = new_groups

        self.log("答题结束，共成功选择 %d 题。请手动提交。" % total_answered, "ok")
        self.status("答题结束，请手动提交")

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def _wait_for_quiz(self) -> List[dict]:
        deadline = time.time() + max(10, int(self.config.wait_login_seconds or 600))
        self.status("等待进入答题页…")
        self.log("等待答题页：登录/验证码/手动导航完成后，程序会自动开始。")
        last_notice = 0.0
        while time.time() < deadline:
            self._check_stop()
            groups = self.scan_page(strict=True)
            if groups:
                if len(groups) >= 1:
                    self.log("检测到 %d 道题，开始自动答题。" % len(groups), "ok")
                    return groups
            if self.start_now_event.is_set():
                self.start_now_event.clear()
                groups = self.scan_page(strict=False)
                if groups:
                    self.log("手动触发：检测到 %d 道题。" % len(groups), "ok")
                    return groups
                self.log("当前页仍未检测到题目；请确认已进入答题页。", "warn")
            now = time.time()
            if now - last_notice > 20:
                last_notice = now
                try:
                    self.log("仍在等待答题页… 当前：%s" % self.driver.title)
                except Exception:
                    pass
            self._sleep(1.8)
        self.log("等待答题页超时。可在进入答题页后点击“立即开始当前页”。", "warn")
        self.status("等待答题页超时")
        return []

    def answer_existing_page(self) -> None:
        """不重新打开网址，直接扫描浏览器当前页并开始答题。"""
        self.running = True
        self.stop_event.clear()
        self.status("正在扫描当前页…")
        try:
            if self.driver is None:
                self.log("浏览器尚未启动。", "error")
                self.status("浏览器未启动")
                return
            groups = self.scan_page(strict=False)
            if not groups:
                self.log("当前页没有检测到题目。", "warn")
                self.status("当前页没有题目")
                return
            self.log("当前页检测到 %d 道题，开始答题。" % len(groups), "ok")
            self._answer_loop(groups)
        except StopRequested:
            self.log("已停止。", "warn")
            self.status("已停止")
        except Exception as e:
            self._last_error = str(e)
            self.log("运行失败：%s" % e, "error")
            self.log(traceback.format_exc(limit=4), "debug")
            self.status("运行失败")
        finally:
            self.running = False
            try:
                self.stop_event.clear()
            except Exception:
                pass

    def run(self) -> None:
        self.running = True
        self.stop_event.clear()
        self.status("启动中…")
        try:
            if self.driver is None:
                self._launch_browser()
            self._open_url()
            self._try_generic_login()
            groups = self._wait_for_quiz()
            if not groups:
                return
            self._answer_loop(groups)
        except StopRequested:
            self.log("已停止。", "warn")
            self.status("已停止")
        except Exception as e:
            self._last_error = str(e)
            self.log("运行失败：%s" % e, "error")
            self.log(traceback.format_exc(limit=4), "debug")
            self.status("运行失败")
        finally:
            self.running = False
            try:
                self.stop_event.clear()
            except Exception:
                pass
