#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 Nuitka 把“通用答题工具”打包成 exe。

用法（在本目录下执行）：
    python bianyi.py                # 打包成单个 exe（默认，onefile 模式）
    python bianyi.py --onedir      # 打包成目录模式（首次启动更快，体积更大）
    python bianyi.py --dry-run     # 只打印将执行的命令，不实际打包
    python bianyi.py --icon xx.ico # 指定 exe 图标（可选）

说明：
1. 优先使用本目录 .venv 里的 Python；没有 venv 时用当前 Python。
2. 如果没装 Nuitka，会询问是否自动安装（可用 --yes 跳过询问）。
3. MSVC 链接器在含中文的路径下会报 LNK1104，因此编译输出固定放在
   纯英文目录（%%LOCALAPPDATA%%\\ua_build），打包成功后自动拷回项目 build 目录。
4. 首次打包 Nuitka 会自动下载/查找 C 编译器，需要联网；
   整个打包过程大约 10~40 分钟，属于正常现象（第二次起会快很多）。
5. 打包产物在 build\\ 目录。目标电脑需要已安装 Chrome 或 Edge；
   首次打开浏览器时 Selenium Manager 会自动联网下载对应驱动。
"""

from __future__ import annotations

import argparse
import importlib.metadata
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ENTRY = os.path.join(HERE, "app.py")
EXE_NAME = "通用答题工具.exe"

DATA_FILES = ["scanner.js", "actions.js", "login.js"]
ICON_FILE = os.path.join(HERE, "app.ico")
# 图标文件也是运行时资源（窗口/任务栏图标要用），一并打包
if os.path.isfile(ICON_FILE):
    DATA_FILES.append("app.ico")
DATA_PACKAGES = [
    # RapidOCR 的模型文件（.onnx）和配置 yaml 必须一起打包
    "rapidocr_onnxruntime",
    "onnxruntime",
    # selenium 里的 selenium-manager.exe 负责自动下载浏览器驱动，必须保留
    "selenium",
]
# 项目自身用不到的大依赖，pandas 会顺带 import 到，排除后体积和编译时间都小很多
NO_FOLLOW = ["matplotlib", "numba"]


def default_build_dir() -> str:
    """Nuitka/MSVC 的链接器在含中文的路径下会报 LNK1104，
    因此编译输出固定放在纯英文路径，打完再拷回项目 build 目录。"""
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "ua_build"),
        os.path.join(tempfile.gettempdir(), "ua_build"),
        r"C:\ua_build",
    ]
    for c in candidates:
        if c and os.path.abspath(c).isascii():
            return c
    return os.path.join(tempfile.gettempdir(), "ua_build")


def venv_python() -> str:
    candidate = os.path.join(HERE, ".venv", "Scripts", "python.exe")
    if os.path.isfile(candidate):
        return candidate
    return sys.executable


def nuitka_version(python: str) -> tuple:
    r = subprocess.run(
        [python, "-m", "nuitka", "--version"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        return ()
    try:
        first = r.stdout.strip().splitlines()[0].strip()
        parts = []
        for p in first.split("."):
            if not p.isdigit():
                break
            parts.append(int(p))
        return tuple(parts) if parts else ()
    except Exception:
        return ()


def ensure_nuitka(python: str, assume_yes: bool) -> bool:
    r = subprocess.run(
        [python, "-c", "import nuitka"], capture_output=True,
    )
    if r.returncode == 0:
        return True
    print("当前 Python 环境没有安装 Nuitka。")
    if not assume_yes:
        try:
            ans = input("是否现在自动安装？[Y/n] ").strip().lower()
        except EOFError:
            ans = "n"
        if ans and ans not in ("y", "yes"):
            print("已取消。可手动执行：")
            print('  "%s" -m pip install nuitka' % python)
            return False
    print("正在安装 Nuitka …")
    r = subprocess.run([python, "-m", "pip", "install", "nuitka"])
    if r.returncode != 0:
        print("pip 安装失败，尝试国内镜像 …")
        r = subprocess.run([
            python, "-m", "pip", "install", "nuitka",
            "-i", "https://mirrors.aliyun.com/pypi/simple/",
        ])
    return r.returncode == 0


def build_command(python: str, onedir: bool, icon: str, build_dir: str) -> list:
    cmd = [
        python, "-m", "nuitka",
        "--standalone",
        # Tkinter GUI 必须带 TCL/TK 运行库，否则打出的 exe 启动即报错
        "--enable-plugin=tk-inter",
        "--assume-yes-for-downloads",
        "--output-dir=%s" % build_dir,
        "--output-filename=%s" % EXE_NAME,
        "--remove-output",
        "--lto=no",
        "--product-name=通用答题工具",
        "--file-description=通用网页答题工具（内容匹配版）",
        "--file-version=1.0.0",
    ]
    for m in NO_FOLLOW:
        cmd.append("--nofollow-import-to=%s" % m)
    ver = nuitka_version(python)
    # Nuitka 2.0 改名了控制台开关；旧版用 --disable-console
    if ver and ver >= (2, 0):
        cmd.append("--windows-console-mode=disable")
    else:
        cmd.append("--disable-console")
    if onedir:
        cmd.append("--onedir")
    else:
        # 把解压目录固定到用户缓存，避免每次启动都重新解压（加快二次启动）
        # 注意：这个规格由 exe 引导器按 ANSI 处理，不能写中文，否则解压目录名会乱码
        cmd.append("--onefile")
        cmd.append("--onefile-tempdir-spec={CACHE_DIR}\\UniversalAnswerTool")
    for f in DATA_FILES:
        cmd.append("--include-data-files=%s=%s" % (f, f))
    for pkg in DATA_PACKAGES:
        cmd.append("--include-package=%s" % pkg)
        cmd.append("--include-package-data=%s" % pkg)
    if icon:
        cmd.append("--windows-icon-from-ico=%s" % icon)
    cmd.append(ENTRY)
    return cmd


def copy_back(onedir: bool, build_dir: str) -> str:
    """把打包产物拷回项目 build 目录，返回最终路径。"""
    if onedir:
        src = os.path.join(build_dir, "app.dist")
        dst = os.path.join(HERE, "build", "app.dist")
        if os.path.isdir(dst):
            shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)
        return os.path.join(dst, EXE_NAME)
    src = os.path.join(build_dir, EXE_NAME)
    os.makedirs(os.path.join(HERE, "build"), exist_ok=True)
    dst = os.path.join(HERE, "build", EXE_NAME)
    shutil.copy2(src, dst)
    return dst


def main() -> int:
    ap = argparse.ArgumentParser(description="Nuitka 打包脚本")
    ap.add_argument("--onedir", action="store_true", help="打包成目录而不是单文件")
    ap.add_argument("--dry-run", action="store_true", help="只打印命令，不执行")
    ap.add_argument("--yes", action="store_true", help="跳过所有询问")
    ap.add_argument("--icon", default="", help="exe 图标文件（.ico），默认用本目录 app.ico")
    ap.add_argument("--output-dir", default="", help="覆盖默认的编译输出目录（需纯英文路径）")
    args = ap.parse_args()

    python = venv_python()
    print("使用 Python：%s" % python)

    if not os.path.isfile(ENTRY):
        print("找不到入口文件：%s" % ENTRY)
        return 1

    build_dir = args.output_dir or default_build_dir()
    if not os.path.abspath(build_dir).isascii():
        print("输出目录必须为纯英文路径（MSVC 链接器不支持中文路径）：%s" % build_dir)
        return 1
    os.makedirs(build_dir, exist_ok=True)

    if not args.dry_run and not ensure_nuitka(python, args.yes):
        return 1

    icon = args.icon or (ICON_FILE if os.path.isfile(ICON_FILE) else "")
    cmd = build_command(python, args.onedir, icon, build_dir)
    print("\n编译输出目录：%s（纯英文路径，避免 MSVC 链接器中文路径 bug）" % build_dir)
    print("执行命令：")
    print(" ".join('"%s"' % c if " " in c else c for c in cmd))
    print()

    if args.dry_run:
        print("（--dry-run 模式：未实际执行）")
        return 0

    try:
        r = subprocess.run(cmd, cwd=HERE)
    except KeyboardInterrupt:
        print("\n已手动中断。")
        return 130

    if r.returncode != 0:
        print("\n打包失败（退出码 %d）。" % r.returncode)
        print("常见原因：")
        print("  1. 首次运行需要联网下载编译器/依赖，检查网络后重试；")
        print("  2. 磁盘空间不足（build 目录和编译器需要 2GB 以上空间）；")
        print("  3. 杀毒软件拦截了编译过程，可把本目录和 %s 加入白名单。" % build_dir)
        return r.returncode

    out = copy_back(args.onedir, build_dir)
    print("\n打包完成：%s" % out)
    if os.path.isfile(out):
        print("文件大小：%.1f MB" % (os.path.getsize(out) / 1024 / 1024))
    print("\n注意事项：")
    print("  - 目标电脑需安装 Chrome 或 Edge，首次打开浏览器需联网下载驱动；")
    print("  - config.json 和 browser_profile 会生成在 exe 同目录；")
    print("  - 若被杀毒软件误报，把 exe 加入白名单即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
