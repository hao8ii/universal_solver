#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地模拟答题网站，用于自动化测试，不依赖外网。"""

from __future__ import annotations

import base64
import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = None


def _image_data(text: str, w: int = 620, h: int = 70) -> str:
    if Image is None:
        return ""
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 30)
    except Exception:
        font = ImageFont.load_default()
    d.text((12, 16), text, font=font, fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _page(body: str, script: str = "") -> bytes:
    html = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>模拟答题系统</title>
<style>
body{font-family:"Microsoft YaHei UI",Arial,sans-serif;margin:30px;background:#f5f7fa}
.question{background:#fff;border:1px solid #ddd;border-radius:8px;padding:18px;margin:18px 0}
.question-stem{font-weight:600;margin-bottom:10px}
label{display:block;padding:8px;margin:4px 0;border:1px solid #eee;border-radius:5px;cursor:pointer}
label img{vertical-align:middle;max-width:640px}
button{padding:8px 20px;margin-top:20px}
.custom-option{padding:8px;margin:5px 0;border:1px solid #ccc;cursor:pointer}
.custom-option[aria-checked=true]{background:#cde8ff}
</style></head><body>
%s
<script>%s</script>
</body></html>""" % (body, script)
    return html.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    dynamic_html = ""

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/dynamic":
            self._send(self.dynamic_html.encode("utf-8") if self.dynamic_html else b"<html></html>")
            return
        if path in ("/", "/quiz"):
            body = """
<h2>模拟通用答题</h2>
<div class="question">
  <div class="question-stem">1. 全面依法治国要坚持什么？</div>
  <label><input type="radio" name="q1" value="D"> D. 仅依靠道德教化</label>
  <label><input type="radio" name="q1" value="A"> A. 坚持依法治国和以德治国相结合</label>
  <label><input type="radio" name="q1" value="C"> C. 只依靠群众运动</label>
  <label><input type="radio" name="q1" value="B"> B. 放弃党的领导</label>
</div>
<div class="question">
  <div class="question-stem">2. 下列哪些属于全面依法治国的要求？</div>
  <label><input type="checkbox" name="q2" value="C"> C. 只强调效率</label>
  <label><input type="checkbox" name="q2" value="A"> A. 科学立法</label>
  <label><input type="checkbox" name="q2" value="B"> B. 严格执法</label>
  <label><input type="checkbox" name="q2" value="D"> D. 全民守法</label>
</div>
<div class="question">
  <div class="question-stem">3. 依法治国是党领导人民治理国家的基本方略。</div>
  <label><input type="radio" name="q3" value="B"> B. 错误</label>
  <label><input type="radio" name="q3" value="A"> A. 正确</label>
</div>
<button id="submit" onclick="document.getElementById('result').textContent='已提交'">提交</button>
<div id="result"></div>
"""
            self._send(_page(body))
        elif path == "/custom":
            body = """
<h2>自定义控件</h2>
<div class="question">
  <div class="question-stem">1. 自定义单选：全面依法治国要坚持什么？</div>
  <div class="custom-option" role="radio" aria-checked="false" data-value="D">D. 仅依靠道德教化</div>
  <div class="custom-option" role="radio" aria-checked="false" data-value="A">A. 坚持依法治国和以德治国相结合</div>
  <div class="custom-option" role="radio" aria-checked="false" data-value="C">C. 只依靠群众运动</div>
  <div class="custom-option" role="radio" aria-checked="false" data-value="B">B. 放弃党的领导</div>
</div>
<div class="question">
  <div class="question-stem">2. 自定义多选：下列哪些属于全面依法治国的要求？</div>
  <div class="custom-option" role="checkbox" aria-checked="false">C. 只强调效率</div>
  <div class="custom-option" role="checkbox" aria-checked="false">A. 科学立法</div>
  <div class="custom-option" role="checkbox" aria-checked="false">B. 严格执法</div>
  <div class="custom-option" role="checkbox" aria-checked="false">D. 全民守法</div>
</div>
"""
            script = """
document.querySelectorAll('[role=radio]').forEach(function(el){
  el.addEventListener('click', function(){
    var p=el.parentElement;
    p.querySelectorAll('[role=radio]').forEach(function(x){x.setAttribute('aria-checked','false')});
    el.setAttribute('aria-checked','true');
  });
});
document.querySelectorAll('[role=checkbox]').forEach(function(el){
  el.addEventListener('click', function(){
    el.setAttribute('aria-checked', el.getAttribute('aria-checked')==='true'?'false':'true');
  });
});
"""
            self._send(_page(body, script))
        elif path == "/images":
            body = """
<h2>图片选项</h2>
<div class="question">
  <div class="question-stem">1. 全面依法治国要坚持什么？</div>
  <label><input type="radio" name="q1" value="D"><img src="%s"></label>
  <label><input type="radio" name="q1" value="A"><img src="%s"></label>
  <label><input type="radio" name="q1" value="C"><img src="%s"></label>
  <label><input type="radio" name="q1" value="B"><img src="%s"></label>
</div>
""" % (
                _image_data("D. 仅依靠道德教化"),
                _image_data("A. 坚持依法治国和以德治国相结合"),
                _image_data("C. 只依靠群众运动"),
                _image_data("B. 放弃党的领导"),
            )
            self._send(_page(body))
        elif path == "/page1":
            body = """
<h2>翻页测试</h2>
<div class="question">
  <div class="question-stem">1. 全面依法治国要坚持什么？</div>
  <label><input type="radio" name="q1" value="D"> D. 仅依靠道德教化</label>
  <label><input type="radio" name="q1" value="A"> A. 坚持依法治国和以德治国相结合</label>
  <label><input type="radio" name="q1" value="C"> C. 只依靠群众运动</label>
  <label><input type="radio" name="q1" value="B"> B. 放弃党的领导</label>
</div>
<button onclick="location.href='/page2'">下一题</button>
<button onclick="this.textContent='已提交'">提交</button>
"""
            self._send(_page(body))
        elif path == "/page2":
            body = """
<h2>翻页测试 2</h2>
<div class="question">
  <div class="question-stem">2. 依法治国是党领导人民治理国家的基本方略。</div>
  <label><input type="radio" name="q2" value="B"> B. 错误</label>
  <label><input type="radio" name="q2" value="A"> A. 正确</label>
</div>
<button onclick="document.body.innerHTML='<h2>已提交</h2>'">提交</button>
"""
            self._send(_page(body))
        elif path == "/login_step":
            body = """
<h2>分步登录 1</h2>
<div>
  <input type="text" name="username" placeholder="手机号/账号">
  <button type="button" onclick="location.href='/login_step2'">下一步</button>
</div>
"""
            self._send(_page(body))
        elif path == "/login_step2":
            body = """
<h2>分步登录 2</h2>
<form action="/quiz" method="get">
  <div><input type="hidden" name="username" value="u"></div>
  <div><input type="password" name="password" placeholder="密码"></div>
  <button type="submit">登录</button>
</form>
"""
            self._send(_page(body))
        elif path == "/login":
            body = """
<h2>模拟登录</h2>
<form action="/quiz" method="get">
  <div><input type="text" name="username" placeholder="用户名/手机号"></div>
  <div><input type="password" name="password" placeholder="密码"></div>
  <button type="submit">登录</button>
</form>
"""
            self._send(_page(body))
        elif path == "/pressed":
            body = """
<h2>按钮选项</h2>
<div class="question">
  <div class="question-stem">1. 全面依法治国要坚持什么？</div>
  <button type="button" aria-pressed="false">D. 仅依靠道德教化</button>
  <button type="button" aria-pressed="false">A. 坚持依法治国和以德治国相结合</button>
  <button type="button" aria-pressed="false">C. 只依靠群众运动</button>
  <button type="button" aria-pressed="false">B. 放弃党的领导</button>
</div>
"""
            script = """
document.querySelectorAll('button[aria-pressed]').forEach(function(el){
  el.addEventListener('click', function(){
    el.parentElement.querySelectorAll('button[aria-pressed]').forEach(function(x){x.setAttribute('aria-pressed','false')});
    el.setAttribute('aria-pressed','true');
  });
});
"""
            self._send(_page(body, script))
        elif path == "/auto1":
            body = """
<h2>自动跳页测试</h2>
<div class="question">
  <div class="question-stem">1. 全面依法治国要坚持什么？</div>
  <label><input type="radio" name="q1" value="D"> D. 仅依靠道德教化</label>
  <label><input type="radio" name="q1" value="A"> A. 坚持依法治国和以德治国相结合</label>
  <label><input type="radio" name="q1" value="C"> C. 只依靠群众运动</label>
  <label><input type="radio" name="q1" value="B"> B. 放弃党的领导</label>
</div>
"""
            script = """
document.querySelectorAll('input[name=q1]').forEach(function(el){
  el.addEventListener('change', function(){
    setTimeout(function(){ location.href='/page2'; }, 300);
  });
});
"""
            self._send(_page(body, script))
        elif path == "/table":
            body = """
<h2>表格布局</h2>
<div class="question">
  <div class="question-stem">1. 全面依法治国要坚持什么？</div>
  <table>
    <tr><td><input type="radio" name="q1" value="D"></td><td>D. 仅依靠道德教化</td></tr>
    <tr><td><input type="radio" name="q1" value="A"></td><td>A. 坚持依法治国和以德治国相结合</td></tr>
    <tr><td><input type="radio" name="q1" value="C"></td><td>C. 只依靠群众运动</td></tr>
    <tr><td><input type="radio" name="q1" value="B"></td><td>B. 放弃党的领导</td></tr>
  </table>
</div>
"""
            self._send(_page(body))
        elif path == "/image_stem":
            body = """
<h2>图片题干</h2>
<div class="question">
  <img src="%s" style="max-width:760px">
  <label><input type="radio" name="q1" value="D"> D. 仅依靠道德教化</label>
  <label><input type="radio" name="q1" value="A"> A. 坚持依法治国和以德治国相结合</label>
  <label><input type="radio" name="q1" value="C"> C. 只依靠群众运动</label>
  <label><input type="radio" name="q1" value="B"> B. 放弃党的领导</label>
</div>
""" % _image_data("1. 全面依法治国要坚持什么？", w=760, h=80)
            self._send(_page(body))
        elif path == "/frame":
            body = """
<h2>iframe 测试</h2>
<iframe src="/frame_quiz" style="width:100%;height:520px;border:1px solid #999"></iframe>
"""
            self._send(_page(body))
        elif path == "/frame_quiz":
            body = """
<div class="question">
  <div class="question-stem">1. 全面依法治国要坚持什么？</div>
  <label><input type="radio" name="q1" value="D"> D. 仅依靠道德教化</label>
  <label><input type="radio" name="q1" value="A"> A. 坚持依法治国和以德治国相结合</label>
  <label><input type="radio" name="q1" value="C"> C. 只依靠群众运动</label>
  <label><input type="radio" name="q1" value="B"> B. 放弃党的领导</label>
</div>
"""
            self._send(_page(body))
        elif path == "/shadow":
            body = """
<h2>Shadow DOM 测试</h2>
<div id="host"></div>
"""
            script = """
const root = document.getElementById('host').attachShadow({mode:'open'});
root.innerHTML = `
<div class="question">
  <div class="question-stem">1. 全面依法治国要坚持什么？</div>
  <label><input type="radio" name="q1" value="D"> D. 仅依靠道德教化</label>
  <label><input type="radio" name="q1" value="A"> A. 坚持依法治国和以德治国相结合</label>
  <label><input type="radio" name="q1" value="C"> C. 只依靠群众运动</label>
  <label><input type="radio" name="q1" value="B"> B. 放弃党的领导</label>
</div>`;
"""
            self._send(_page(body, script))
        elif path == "/content":
            # 返回纯文本，便于测试
            self._send(b"ok")
        else:
            self.send_error(404)

    def _send(self, data: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class MockServer:
    def __init__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base(self) -> str:
        return "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def set_dynamic(self, html: str) -> None:
        Handler.dynamic_html = html

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


if __name__ == "__main__":
    s = MockServer()
    print(s.base)
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        s.close()
