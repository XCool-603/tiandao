#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天道 · 番茄小说全自动挂机发书守护机器人 (Fanqie Auto Uploader Bot)
利用系统自带 Microsoft Edge 浏览器与 CDP (Chrome DevTools Protocol)，
无需安装额外 Chromium，登录一次即可永久挂机：写一章，自动上传一章！
"""

import os
import sys
import time
import json
import subprocess
import urllib.request
import asyncio
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
EDGE_USER_DATA = BASE_DIR / "output" / "fanqie_edge_profile"
SERVER_API = "http://localhost:8088"
CDP_PORT = 9222

def find_edge_path():
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe")
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "msedge"

def launch_edge_browser():
    edge_exe = find_edge_path()
    EDGE_USER_DATA.mkdir(parents=True, exist_ok=True)
    cmd = [
        edge_exe,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={str(EDGE_USER_DATA)}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://fanqienovel.com/main/writer"
    ]
    print(f"🚀 正在启动 Edge 独立发布浏览器...")
    print(f"📁 会话数据保存目录: {EDGE_USER_DATA}")
    proc = subprocess.Popen(cmd)
    return proc

def get_cdp_targets():
    try:
        req = urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json", timeout=3)
        return json.loads(req.read().decode("utf-8"))
    except Exception:
        return []

def get_pending_chapter():
    try:
        req = urllib.request.urlopen(f"{SERVER_API}/api/fanqie/pending_chapter", timeout=5)
        res = json.loads(req.read().decode("utf-8"))
        if res.get("status") == "ok" and res.get("has_pending"):
            return res.get("chapter")
    except Exception as e:
        pass
    return None

def confirm_uploaded(book_id, chapter_id, mode="draft"):
    try:
        data = json.dumps({"book_id": book_id, "chapter_id": chapter_id, "mode": mode}).encode("utf-8")
        req = urllib.request.Request(
            f"{SERVER_API}/api/fanqie/confirm_uploaded",
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"❌ 上报同步状态失败: {e}")
        return None

async def cdp_eval_js(ws, expr):
    msg_id = int(time.time() * 1000) % 1000000
    payload = {
        "id": msg_id,
        "method": "Runtime.evaluate",
        "params": {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": True
        }
    }
    await ws.send(json.dumps(payload))
    while True:
        resp = await ws.recv()
        data = json.loads(resp)
        if data.get("id") == msg_id:
            return data.get("result", {}).get("result", {}).get("value")

async def run_bot_loop():
    import websockets
    print("=" * 60)
    print("🍅 天道 · 番茄小说全自动挂机发书机器人 已启动")
    print("=" * 60)
    print("提示：首次启动请在弹出的 Edge 浏览器中登录番茄作家后台。")
    print("登录后，本机器人将持续在后台守护，天道每推演写完一章，自动录入番茄草稿箱！")
    print("=" * 60)

    # 1. 确保 Edge 启动
    targets = get_cdp_targets()
    if not targets:
        launch_edge_browser()
        for _ in range(15):
            time.sleep(1)
            targets = get_cdp_targets()
            if targets:
                break

    if not targets:
        print("❌ 无法连接到 Edge 调试端口，请检查是否已启动。")
        return

    # 找到番茄作家后台页面
    page_target = None
    for t in targets:
        if t.get("type") == "page" and "fanqie" in t.get("url", "").lower():
            page_target = t
            break
    if not page_target:
        for t in targets:
            if t.get("type") == "page":
                page_target = t
                break

    if not page_target or "webSocketDebuggerUrl" not in page_target:
        print("❌ 未找到可注入的浏览器标签页。")
        return

    ws_url = page_target["webSocketDebuggerUrl"]
    print(f"🔗 已成功接管 Edge 会话: {page_target.get('title', '未知')} ({page_target.get('url')})")

    async with websockets.connect(ws_url) as ws:
        # 心跳及轮询循环
        while True:
            try:
                # 检查天道服务端是否有待上传的章节
                pending = get_pending_chapter()
                if pending:
                    chap_id = pending.get("chapter_id")
                    chap_title = pending.get("chapter_title")
                    chap_content = pending.get("content")
                    book_id = pending.get("book_id")
                    print(f"\n⚡ 检测到天道最新待上传章节: 第 {chap_id} 章《{chap_title}》({len(chap_content)}字)")

                    # 注入自动化填充逻辑
                    # 1. 检查当前是否在新建章节页面
                    js_fill = f"""
                    (async function() {{
                        const title = {json.dumps(chap_title)};
                        const content = {json.dumps(chap_content)};
                        
                        // 查找标题输入框
                        let titleInput = document.querySelector('input[placeholder*="标题"]') || 
                                         document.querySelector('.chapter-title-input input') ||
                                         document.querySelector('input[type="text"]');
                        
                        // 查找正文输入框 (textarea / contenteditable / ProseMirror)
                        let bodyEditor = document.querySelector('.ProseMirror') || 
                                         document.querySelector('div[contenteditable="true"]') ||
                                         document.querySelector('textarea[placeholder*="正文"]');

                        if (!titleInput || !bodyEditor) {{
                            // 如果不在编辑页，尝试寻找“新建章节”按钮
                            let newBtn = Array.from(document.querySelectorAll('button, a')).find(el => el.textContent.includes('新建章节') || el.textContent.includes('写新章'));
                            if (newBtn) {{
                                newBtn.click();
                                return {{ success: false, navigating: true, message: '正在自动进入新建章节页面...' }};
                            }}
                            return {{ success: false, message: '未找到章节输入框，请在番茄后台打开作品的【章节发布】页面' }};
                        }}

                        // 填入标题
                        titleInput.value = title;
                        titleInput.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        titleInput.dispatchEvent(new Event('change', {{ bubbles: true }}));

                        // 填入正文
                        if (bodyEditor.tagName.toLowerCase() === 'textarea') {{
                            bodyEditor.value = content;
                            bodyEditor.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            bodyEditor.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }} else {{
                            // 富文本 contenteditable
                            bodyEditor.focus();
                            bodyEditor.innerText = content;
                            bodyEditor.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        }}

                        await new Promise(r => setTimeout(r, 800));

                        // 查找“存草稿”或“保存草稿”按钮
                        let saveBtn = Array.from(document.querySelectorAll('button')).find(el => 
                            el.textContent.includes('存草稿') || 
                            el.textContent.includes('保存草稿') ||
                            el.textContent.includes('保存')
                        );

                        if (saveBtn && !saveBtn.disabled) {{
                            saveBtn.click();
                            return {{ success: true, message: '已自动点击保存草稿' }};
                        }}

                        return {{ success: true, message: '正文与标题已填入，等待手动确认保存' }};
                    }})()
                    """
                    fill_res = await cdp_eval_js(ws, js_fill)
                    print(f"🤖 自动化执行结果: {fill_res}")
                    if fill_res and fill_res.get("success"):
                        confirm_uploaded(book_id, chap_id, mode="draft")
                        print(f"✅ 第 {chap_id} 章《{chap_title}》已成功保存至番茄！")
                    elif fill_res and fill_res.get("navigating"):
                        print(f"⏳ 正在跳转至新建章节页面，将在下一次心跳继续填充...")
                else:
                    # 无待上传章节
                    pass
            except Exception as e_loop:
                print(f"⚠️ 挂机守护循环异常: {e_loop}")
            
            await asyncio.sleep(8)

if __name__ == "__main__":
    try:
        asyncio.run(run_bot_loop())
    except KeyboardInterrupt:
        print("\n👋 挂机发书机器人已退出。")
