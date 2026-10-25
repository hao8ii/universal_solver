#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用答题工具 GUI（Tkinter）。"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Optional

from bank import Bank
from engine import EngineConfig, UniversalEngine, app_data_dir
from ocr_engine import OcrReader

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(app_data_dir(), "config.json")
FONT_NAME = "Microsoft YaHei UI"
FONT_SIZE = 10


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.bank: Optional[Bank] = None
        self.engine: Optional[UniversalEngine] = None
        self.worker: Optional[threading.Thread] = None
        self.events: "queue.Queue[tuple]" = queue.Queue()
        self.answered_count = 0
        self._closing = False

        self._init_window()
        self._build_style()
        self._build_ui()
        self._load_config()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(120, self._poll_events)

    # ------------------------------------------------------------------
    # 界面
    # ------------------------------------------------------------------
    def _init_window(self) -> None:
        self.root.title("通用答题工具 · 内容匹配版")
        self.root.geometry("920x790")
        self.root.minsize(820, 700)
        self._set_window_icon()

    def _set_window_icon(self) -> None:
        """设置窗口标题栏和任务栏图标（不加这行，任务栏会显示 Tk 默认图标）。"""
        path = os.path.join(HERE, "app.ico")
        if not os.path.isfile(path):
            return
        try:
            self.root.iconbitmap(path)
        except Exception:
            pass

    def _build_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except Exception:
            try:
                style.theme_use("clam")
            except Exception:
                pass
        default_font = (FONT_NAME, FONT_SIZE)
        self.root.option_add("*Font", default_font)
        for named in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
                      "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont"):
            try:
                tkfont.nametofont(named).configure(family=FONT_NAME, size=FONT_SIZE)
            except Exception:
                pass
        for name in ("TLabel", "TButton", "TEntry", "TCombobox", "TCheckbutton",
                     "TLabelframe.Label", "TNotebook.Tab"):
            try:
                style.configure(name, font=default_font)
            except Exception:
                pass
        style.configure("Title.TLabel", font=(FONT_NAME, 16, "bold"))
        style.configure("Sub.TLabel", font=(FONT_NAME, 9), foreground="#666666")
        style.configure("Status.TLabel", font=(FONT_NAME, 9), foreground="#333333")
        style.configure("Primary.TButton", font=(FONT_NAME, 10, "bold"))
        style.configure("Danger.TButton", font=(FONT_NAME, 10))

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=(14, 10, 14, 4))
        top.pack(fill="x")
        ttk.Label(top, text="通用网页答题工具", style="Title.TLabel").pack(side="left")
        ttk.Label(
            top,
            text="按题干和选项内容匹配 · 不依赖 A/B/C/D 顺序 · 图片题可 OCR",
            style="Sub.TLabel",
        ).pack(side="left", padx=(16, 0), pady=(6, 0))

        main = ttk.Frame(self.root, padding=(14, 6, 14, 6))
        main.pack(fill="both", expand=True)

        # 题库
        bank_box = ttk.LabelFrame(main, text=" 1. 选择题库 ", padding=(10, 8))
        bank_box.pack(fill="x")
        bank_box.columnconfigure(1, weight=1)
        ttk.Label(bank_box, text="题库文件：").grid(row=0, column=0, sticky="w")
        self.bank_var = tk.StringVar()
        ttk.Entry(bank_box, textvariable=self.bank_var).grid(
            row=0, column=1, sticky="ew", padx=(4, 6)
        )
        ttk.Button(bank_box, text="浏览…", command=self.browse_bank).grid(row=0, column=2, padx=2)
        self.load_btn = ttk.Button(bank_box, text="加载题库", command=self.load_bank_async)
        self.load_btn.grid(row=0, column=3, padx=2)
        self.bank_status_var = tk.StringVar(value="尚未加载题库")
        ttk.Label(bank_box, textvariable=self.bank_status_var, style="Sub.TLabel").grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(6, 0)
        )

        # 登录信息
        login_box = ttk.LabelFrame(main, text=" 2. 登录信息（可只填网址，手动登录） ", padding=(10, 8))
        login_box.pack(fill="x", pady=(10, 0))
        login_box.columnconfigure(1, weight=1)
        ttk.Label(login_box, text="网址：").grid(row=0, column=0, sticky="w", pady=2)
        self.url_var = tk.StringVar()
        ttk.Entry(login_box, textvariable=self.url_var).grid(
            row=0, column=1, columnspan=3, sticky="ew", padx=(4, 4), pady=2
        )
        ttk.Label(login_box, text="账号：").grid(row=1, column=0, sticky="w", pady=2)
        self.user_var = tk.StringVar()
        ttk.Entry(login_box, textvariable=self.user_var).grid(
            row=1, column=1, sticky="ew", padx=(4, 4), pady=2
        )
        ttk.Label(login_box, text="密码：").grid(row=1, column=2, sticky="e", padx=(8, 2), pady=2)
        self.pwd_var = tk.StringVar()
        self.pwd_entry = ttk.Entry(login_box, textvariable=self.pwd_var, show="*")
        self.pwd_entry.grid(row=1, column=3, sticky="ew", padx=(2, 4), pady=2)
        login_box.columnconfigure(3, weight=1)

        opt_row = ttk.Frame(login_box)
        opt_row.grid(row=2, column=0, columnspan=4, sticky="w", pady=(4, 0))
        ttk.Label(opt_row, text="浏览器：").pack(side="left")
        self.browser_var = tk.StringVar(value="Chrome")
        ttk.Combobox(
            opt_row, textvariable=self.browser_var, values=("Chrome", "Edge"),
            width=9, state="readonly",
        ).pack(side="left", padx=(2, 18))
        self.show_pwd_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opt_row, text="显示密码", variable=self.show_pwd_var,
            command=self.toggle_password,
        ).pack(side="left", padx=(0, 18))
        self.ocr_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opt_row, text="图片题干/选项使用本地 OCR", variable=self.ocr_var,
        ).pack(side="left")
        ttk.Label(
            login_box,
            text="登录有验证码/短信验证时，请在打开的浏览器里手动完成；程序会自动等待并开始。",
            style="Sub.TLabel",
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(6, 0))

        # 操作
        action = ttk.Frame(main)
        action.pack(fill="x", pady=(10, 0))
        self.start_btn = ttk.Button(
            action, text="启动并自动答题", style="Primary.TButton", command=self.start
        )
        self.start_btn.pack(side="left", padx=(0, 8))
        self.now_btn = ttk.Button(
            action, text="立即开始当前页", command=self.start_current, state="disabled"
        )
        self.now_btn.pack(side="left", padx=(0, 8))
        self.stop_btn = ttk.Button(
            action, text="停止", style="Danger.TButton", command=self.stop, state="disabled"
        )
        self.stop_btn.pack(side="left", padx=(0, 8))
        self.close_browser_btn = ttk.Button(
            action, text="关闭浏览器", command=self.close_browser
        )
        self.close_browser_btn.pack(side="left", padx=(0, 8))
        self.answer_count_var = tk.StringVar(value="本次已答：0 题")
        ttk.Label(action, textvariable=self.answer_count_var, style="Sub.TLabel").pack(
            side="right", pady=(4, 0)
        )

        # 日志
        log_box = ttk.LabelFrame(main, text=" 运行日志 ", padding=(6, 4))
        log_box.pack(fill="both", expand=True, pady=(10, 0))
        self.log_text = ScrolledText(
            log_box, height=18, wrap="word", font=(FONT_NAME, 9),
            state="disabled", borderwidth=0, relief="flat",
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.tag_configure("info", foreground="#222222")
        self.log_text.tag_configure("ok", foreground="#0a7a2f")
        self.log_text.tag_configure("warn", foreground="#a15c00")
        self.log_text.tag_configure("error", foreground="#b00020")
        self.log_text.tag_configure("debug", foreground="#777777")
        self.log_text.tag_configure("time", foreground="#888888")

        status = ttk.Frame(self.root, padding=(14, 2, 14, 6))
        status.pack(fill="x")
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(status, textvariable=self.status_var, style="Status.TLabel").pack(side="left")
        ttk.Label(
            status,
            text="只自动翻页，不自动提交 · 提交前请自行核对",
            style="Sub.TLabel",
        ).pack(side="right")

    def toggle_password(self) -> None:
        self.pwd_entry.configure(show="" if self.show_pwd_var.get() else "*")

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------
    def _load_config(self) -> None:
        if not os.path.isfile(CONFIG_PATH):
            return
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.bank_var.set(cfg.get("bank", ""))
            self.url_var.set(cfg.get("url", ""))
            self.user_var.set(cfg.get("username", ""))
            self.browser_var.set(cfg.get("browser", "Chrome"))
            self.ocr_var.set(bool(cfg.get("ocr", True)))
            if self.bank_var.get() and os.path.isfile(self.bank_var.get()):
                self.load_bank_async()
        except Exception:
            pass

    def _save_config(self) -> None:
        try:
            cfg = {
                "bank": self.bank_var.get().strip(),
                "url": self.url_var.get().strip(),
                "username": self.user_var.get(),
                "browser": self.browser_var.get(),
                "ocr": bool(self.ocr_var.get()),
            }
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 题库
    # ------------------------------------------------------------------
    def browse_bank(self) -> None:
        path = filedialog.askopenfilename(
            title="选择题库文件",
            filetypes=[
                ("题库文件", "*.xlsx *.xls *.docx *.doc *.wps *.pdf *.csv"),
                ("Excel", "*.xlsx *.xls"),
                ("Word/WPS/PDF", "*.docx *.doc *.wps *.pdf"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self.bank_var.set(path)
            self.load_bank_async()

    def load_bank_async(self) -> None:
        path = self.bank_var.get().strip().strip('"')
        if not path:
            messagebox.showwarning("提示", "请先选择题库文件。")
            return
        if not os.path.isfile(path):
            messagebox.showerror("错误", "题库文件不存在：\n%s" % path)
            return
        self.load_btn.configure(state="disabled", text="加载中…")
        self.bank_status_var.set("正在解析题库，请稍候…")
        self.status_var.set("正在解析题库…")
        threading.Thread(target=self._load_bank_worker, args=(path,), daemon=True).start()

    def _load_bank_worker(self, path: str) -> None:
        try:
            bank = Bank.load(path)
            self.events.put(("bank_ok", bank))
        except Exception as e:
            self.events.put(("bank_error", str(e)))

    # ------------------------------------------------------------------
    # 启动/停止
    # ------------------------------------------------------------------
    def _make_engine(self) -> UniversalEngine:
        cfg = self._engine_config()
        return UniversalEngine(
            self.bank, cfg,
            log_callback=lambda msg, level="info": self.events.put(("log", msg, level)),
            status_callback=lambda msg: self.events.put(("status", msg)),
            answered_callback=lambda data: self.events.put(("answered", data)),
        )

    def _engine_config(self) -> EngineConfig:
        return EngineConfig(
            url=self.url_var.get().strip(),
            username=self.user_var.get(),
            password=self.pwd_var.get(),
            browser=self.browser_var.get().strip().lower(),
            ocr=bool(self.ocr_var.get()),
            headless=False,
        )

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("提示", "程序正在运行中。")
            return
        if self.bank is None:
            messagebox.showwarning("提示", "请先加载题库。")
            return
        chosen = self.bank_var.get().strip().strip('"')
        if chosen and self.bank.path and os.path.abspath(chosen) != os.path.abspath(self.bank.path):
            messagebox.showwarning("提示", "题库文件已更改，请先点击“加载题库”。")
            return
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请填写答题网址或登录网址。")
            return
        self._save_config()
        self.answered_count = 0
        self.answer_count_var.set("本次已答：0 题")
        cfg = self._engine_config()
        if self.engine is None:
            self.engine = self._make_engine()
        else:
            self.engine.bank = self.bank
            self.engine.config = cfg
            self.engine.answered_callback = lambda data: self.events.put(("answered", data))
            self.engine.log_callback = lambda msg, level="info": self.events.put(("log", msg, level))
            self.engine.status_callback = lambda msg: self.events.put(("status", msg))
            self.engine.ocr = OcrReader() if cfg.ocr else None
            self.engine._ocr_failed = False
            self.engine._ocr_announced = False
            self.engine._ocr_warned = False
        self.engine.stop_event.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.now_btn.configure(state="normal")
        self.status_var.set("正在启动…")
        self.worker = threading.Thread(target=self._run_worker, args=(self.engine, False), daemon=True)
        self.worker.start()

    def start_current(self) -> None:
        if not self.engine:
            messagebox.showinfo("提示", "请先点击“启动并自动答题”。")
            return
        if self.worker and self.worker.is_alive():
            self.engine.start_now_event.set()
            self.append_log("已请求立即扫描当前页。", "info")
            return
        if self.engine.driver is None:
            messagebox.showinfo("提示", "浏览器尚未启动，请先点击“启动并自动答题”。")
            return
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.now_btn.configure(state="normal")
        self.worker = threading.Thread(target=self._run_worker, args=(self.engine, True), daemon=True)
        self.worker.start()

    def _run_worker(self, engine: UniversalEngine, current_only: bool) -> None:
        try:
            if current_only:
                engine.answer_existing_page()
            else:
                engine.run()
        finally:
            self.events.put(("done", None))

    def stop(self) -> None:
        if self.engine:
            self.engine.stop()
            self.status_var.set("正在停止…")

    def close_browser(self) -> None:
        if self.engine:
            self.engine.close_browser()
            self.engine = None
        self.now_btn.configure(state="disabled")
        self.status_var.set("浏览器已关闭")
        self.append_log("浏览器已关闭。", "info")

    # ------------------------------------------------------------------
    # 事件循环
    # ------------------------------------------------------------------
    def _poll_events(self) -> None:
        if self._closing:
            return
        try:
            while True:
                item = self.events.get_nowait()
                kind = item[0]
                if kind == "log":
                    self.append_log(item[1], item[2] if len(item) > 2 else "info")
                elif kind == "status":
                    self.status_var.set(item[1])
                elif kind == "answered":
                    if item[1].get("status") == "answered":
                        self.answered_count += 1
                        self.answer_count_var.set("本次已答：%d 题" % self.answered_count)
                elif kind == "bank_ok":
                    self.bank = item[1]
                    self.bank_status_var.set(self.bank.stats_text())
                    self.load_btn.configure(state="normal", text="加载题库")
                    self.status_var.set("题库已加载")
                    self.append_log(self.bank.stats_text(), "ok")
                    for w in self.bank.warnings[:3]:
                        self.append_log("题库提示：" + w, "warn")
                elif kind == "bank_error":
                    self.bank = None
                    self.bank_status_var.set("题库加载失败")
                    self.load_btn.configure(state="normal", text="加载题库")
                    self.status_var.set("题库加载失败")
                    self.append_log("题库加载失败：" + item[1], "error")
                    messagebox.showerror("题库加载失败", item[1])
                elif kind == "done":
                    self.start_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self.now_btn.configure(
                        state="normal" if (self.engine and self.engine.driver) else "disabled"
                    )
                    if self.status_var.get().startswith("正在"):
                        self.status_var.set("已结束")
        except queue.Empty:
            pass
        except Exception as e:
            self.append_log("界面事件错误：%s" % e, "error")
        self.root.after(120, self._poll_events)

    def append_log(self, msg: str, level: str = "info") -> None:
        if level == "debug":
            return
        self.log_text.configure(state="normal")
        ts = time.strftime("%H:%M:%S")
        self.log_text.insert("end", "[%s] " % ts, ("time",))
        self.log_text.insert("end", str(msg) + "\n", (level if level in ("info", "ok", "warn", "error") else "info",))
        # 限制日志长度
        try:
            if int(self.log_text.index("end-1c").split(".")[0]) > 4000:
                self.log_text.delete("1.0", "800.0")
        except Exception:
            pass
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # 关闭
    # ------------------------------------------------------------------
    def on_close(self) -> None:
        if self.engine and self.engine.running and not messagebox.askyesno(
            "确认退出", "程序正在答题。确定要停止并关闭吗？"
        ):
            return
        self._closing = True
        self._save_config()
        if self.engine:
            self.engine.stop()
            try:
                self.engine.close_browser()
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass


def main() -> None:
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
