# -*- coding: utf-8 -*-
"""
====================================================================
天道 · 原生番茄小说创作专区直推引擎 (Fanqie Novel Native Sync)
融合 hchcx/fanqie_auto_publish 核心机制：
1. 空间物理坐标弹窗斩杀（Y 坐标过滤消除新手引导与干扰浮层）
2. 小说卡片悬停探测 (Card Hover -> 章节管理)
3. 多标签页智能跟随 (New Tab Tracking)
4. ProseMirror / 富文本原生事件触发与空格激活字数统计
5. 智能断点续传（草稿扫描防重）与 AI 合规声明自动处理
====================================================================
"""

import os
import sys
import time
import json
import re
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List

# 数据持久化目录
OUTPUT_DIR = Path(__file__).parent / "output"
FANQIE_DIR = OUTPUT_DIR / "fanqie_sync"
FANQIE_DIR.mkdir(parents=True, exist_ok=True)

AUTH_STATE_PATH = FANQIE_DIR / "auth_state.json"
CONFIG_PATH = FANQIE_DIR / "config.json"
QR_CODE_PATH = FANQIE_DIR / "login_qr.png"

LOGIN_URL = "https://fanqienovel.com/main/writer/login"
BOOK_MANAGE_URL = "https://fanqienovel.com/main/writer/book-manage"
AUTHOR_ZONE_URL = "https://fanqienovel.com/writer/zone"

# 全局登录任务锁与状态
_login_lock = threading.Lock()
_login_status = {
    "is_logging_in": False,
    "qr_ready": False,
    "qr_path": "",
    "logged_in": False,
    "author_name": "",
    "last_error": "",
    "started_at": 0
}

def save_cookie_auth(raw_cookie: str, author_name: str = "") -> dict:
    """
    通过手动填入的 Cookie 或 sessionid 快速完成番茄作家登录授权：
    适用于任何无头 Docker、云服务器及受反爬阻断的环境。
    永久持久化保存至 auth_state.json。
    """
    raw_cookie = (raw_cookie or "").strip()
    if not raw_cookie:
        return {"status": "error", "message": "Cookie 内容不能为空！"}

    cookies_list = []
    # 如果用户只粘贴了一个单独的 token（无 = 号），假定为 sessionid
    if "=" not in raw_cookie and len(raw_cookie) > 10:
        cookies_list.append({
            "name": "sessionid",
            "value": raw_cookie,
            "domain": ".fanqienovel.com",
            "path": "/"
        })
    else:
        # 解析 cookie 键值对
        for part in raw_cookie.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                cookies_list.append({
                    "name": k.strip(),
                    "value": v.strip(),
                    "domain": ".fanqienovel.com",
                    "path": "/"
                })

    has_session = any(c["name"] in ("sessionid", "sid_tt", "passport_csrf_token") for c in cookies_list)
    if not has_session:
        return {
            "status": "error",
            "message": "粘贴的 Cookie 中未检测到 sessionid 或 sid_tt 核心登录凭据！请确保在已登录番茄作家专区状态下完整复制。"
        }

    FANQIE_DIR.mkdir(parents=True, exist_ok=True)
    state_data = {
        "cookies": cookies_list,
        "origins": []
    }
    with open(AUTH_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state_data, f, ensure_ascii=False, indent=2)

    cfg = load_fanqie_config()
    cfg["author_name"] = author_name or cfg.get("author_name") or "番茄签约作家"
    cfg["last_sync_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    cfg["cookies"] = raw_cookie
    save_fanqie_config(cfg)

    global _login_status
    _login_status["logged_in"] = True
    _login_status["author_name"] = cfg["author_name"]

    return {
        "status": "ok",
        "message": f"Cookie 凭证已成功保存！当前作者名：{cfg['author_name']}，直推通道已永久激活。",
        "author_name": cfg["author_name"]
    }

def load_fanqie_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    default_cfg = {
        "auto_upload": False,
        "publish_mode": "drafts",
        "author_name": "",
        "last_sync_time": "",
        "cookies": ""
    }
    save_fanqie_config(default_cfg)
    return default_cfg

def save_fanqie_config(cfg: dict) -> dict:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg

def is_playwright_available() -> bool:
    """检查当前 Python 环境是否已安装并可用 playwright"""
    try:
        import playwright
        return True
    except ImportError:
        return False

def get_auth_status() -> dict:
    """检查当前番茄作家账号登录态"""
    global _login_status
    cfg = load_fanqie_config()
    logged_in = False
    author_name = cfg.get("author_name", "")

    if AUTH_STATE_PATH.exists() and AUTH_STATE_PATH.stat().st_size > 50:
        try:
            with open(AUTH_STATE_PATH, "r", encoding="utf-8") as f:
                state_data = json.load(f)
                cookies = state_data.get("cookies", [])
                for c in cookies:
                    if c.get("name") in ("sessionid", "sid_tt", "passport_csrf_token"):
                        logged_in = True
                        break
        except Exception:
            logged_in = False

    return {
        "logged_in": logged_in,
        "author_name": author_name or ("番茄签约作家" if logged_in else "未登录"),
        "auth_file_exists": AUTH_STATE_PATH.exists(),
        "is_logging_in": _login_status.get("is_logging_in", False),
        "qr_ready": _login_status.get("qr_ready", False),
        "qr_url": "/api/fanqie/qr_code" if _login_status.get("qr_ready") else "",
        "playwright_available": is_playwright_available(),
        "publish_mode": cfg.get("publish_mode", "drafts"),
        "auto_upload": cfg.get("auto_upload", False),
        "last_sync_time": cfg.get("last_sync_time", ""),
        "last_error": _login_status.get("last_error", "")
    }

def clean_chapter_for_fanqie(title: str, content: str) -> str:
    """
    番茄作家后台排版格式化：
    1. 首行空两格 (全角空格)
    2. 移除 Markdown 杂乱语法（#、**、```等）
    3. 清洗空行与尾部空白
    """
    text = content.strip()
    text = re.sub(r"^#+\s*.*?\n", "", text)
    text = re.sub(r"```[a-zA-Z]*", "", text)
    text = text.replace("```", "")
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)

    lines = [line.strip() for line in text.splitlines()]
    cleaned_lines = []
    for line in lines:
        if not line:
            continue
        cleaned_lines.append(f"　　{line}")
    return "\n\n".join(cleaned_lines)

def launch_browser(p, headless: bool = True):
    """
    智能优选浏览器驱动：
    1. 优先尝试系统原生 Microsoft Edge（毫秒级拉起，无需单独下载 200MB Chromium）
    2. 其次尝试系统原生 Google Chrome
    3. 最后回退至 Playwright 自带 Chromium
    """
    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage"
    ]
    errors = []
    for channel in ["msedge", "chrome", None]:
        try:
            if channel:
                return p.chromium.launch(channel=channel, headless=headless, args=args)
            else:
                return p.chromium.launch(headless=headless, args=args)
        except Exception as e:
            errors.append(f"{channel or 'default'}: {e}")
    raise RuntimeError(f"未能启动可用浏览器内核: {'; '.join(errors)}")

def dismiss_popups(page):
    """
    神级弹窗斩杀机制（基于物理坐标与特定弹窗文案）：
    1. 连续按 Escape 键消除模态遮罩
    2. 空间坐标打击：只要 Y 坐标 > 100，必是乱入的新手向导浮层（非顶部发布按钮）
    3. 错别字提示弹窗自动确认
    4. 内容风险检测弹窗自动取消（节约检测次数）
    """
    # 1. 连续按 Escape 键消除模态遮罩
    for _ in range(3):
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(150)
        except Exception:
            pass

    # 2. 空间坐标精确打击：消灭新手教学浮层
    for _ in range(8):
        clicked = False
        for target_text in ["下一步", "完成", "我知道了", "跳过"]:
            try:
                btns = page.get_by_text(target_text, exact=True).element_handles()
                for btn in btns:
                    box = btn.bounding_box()
                    if box and box["y"] > 100:
                        btn.click()
                        page.wait_for_timeout(350)
                        clicked = True
            except Exception:
                pass
        if not clicked:
            break

    # 3. 错别字未修改弹窗 -> 强制提交
    try:
        submit_btn = page.get_by_role("button", name="提交").first
        if submit_btn.is_visible():
            submit_btn.click(force=True)
            page.wait_for_timeout(500)
    except Exception:
        pass

    # 4. 内容风险检测弹窗 -> 取消节约额度
    try:
        cancel_btn = page.get_by_role("button", name="取消").last
        if cancel_btn.is_visible():
            cancel_btn.click(force=True)
            page.wait_for_timeout(500)
    except Exception:
        pass

def start_browser_login_async(headless: bool = False) -> dict:
    """
    异步启动番茄作家专区扫码登录流程：
    在后台拉起 Chromium/Edge，打开登录页，截图二维码供前端扫码，
    用户扫码成功后，自动落盘 auth_state.json。
    """
    global _login_status
    if not is_playwright_available():
        msg = "当前运行环境未安装 Playwright 浏览器组件。强烈推荐直接使用下方【粘贴 Cookie / sessionid】快速完成免密绑定！"
        _login_status["last_error"] = msg
        return {"status": "error", "message": msg}

    with _login_lock:
        if _login_status["is_logging_in"]:
            return {
                "status": "busy",
                "message": "正在等待扫码登录中，请直接使用手机扫码。",
                "qr_ready": _login_status["qr_ready"]
            }
        _login_status["is_logging_in"] = True
        _login_status["qr_ready"] = False
        _login_status["last_error"] = ""
        _login_status["started_at"] = time.time()

    def _login_worker():
        global _login_status
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                # Windows 桌面环境下优先使用有界面，方便直接扫码
                use_headless = headless if os.name != 'nt' else False
                browser = launch_browser(p, headless=use_headless)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
                context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                page = context.new_page()
                page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=25000)

                # 寻找并截图二维码区域
                time.sleep(3)
                try:
                    qr_el = page.query_selector(".qrcode-img, .qrcode-wrap, canvas, img[src*='qr'], img[src*='login'], [class*='qr'], [class*='Qr'], [id*='qrcode']")
                    if qr_el:
                        qr_el.screenshot(path=str(QR_CODE_PATH))
                    else:
                        page.screenshot(path=str(QR_CODE_PATH))
                    _login_status["qr_ready"] = True
                    _login_status["qr_path"] = str(QR_CODE_PATH)
                except Exception:
                    page.screenshot(path=str(QR_CODE_PATH))
                    _login_status["qr_ready"] = True

                # 轮询等待登录成功（最多等待 180 秒）
                for _ in range(90):
                    time.sleep(2)
                    cur_url = page.url
                    if "zone" in cur_url or "book" in cur_url or "home" in cur_url or ("author" in cur_url and "login" not in cur_url):
                        context.storage_state(path=str(AUTH_STATE_PATH))
                        cfg = load_fanqie_config()
                        try:
                            name_el = page.query_selector(".author-name, .user-name, [class*='authorName']")
                            if name_el:
                                cfg["author_name"] = name_el.inner_text().strip()
                        except Exception:
                            cfg["author_name"] = "番茄签约作家"
                        cfg["last_sync_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        save_fanqie_config(cfg)

                        _login_status["logged_in"] = True
                        _login_status["author_name"] = cfg["author_name"]
                        break
                browser.close()
        except Exception as e_worker:
            err_msg = f"拉起浏览器扫码失败 ({e_worker})。建议直接在控制台使用【粘贴 Cookie】秒级完成绑定！"
            _login_status["last_error"] = err_msg
        finally:
            _login_status["is_logging_in"] = False

    th = threading.Thread(target=_login_worker, daemon=True)
    th.start()
    return {
        "status": "ok",
        "message": "已拉起番茄作家登录服务，请刷新获取最新扫码界面。"
    }

def native_upload_chapter(book_title: str, chapter_title: str, chapter_content: str, book_id: str = "", mode: str = "drafts") -> dict:
    """
    原生执行单章上传至番茄小说作家后台：
    1. 本地落盘至 output/fanqie_sync/{book_id}/chapter_xxx.txt
    2. 如果已登录番茄账号且 Playwright 可用，驱动后台无头浏览器自动化提交至番茄后台
    """
    bid = book_id if str(book_id).startswith("book_") else f"book_{book_id}"
    book_sync_dir = FANQIE_DIR / bid
    book_sync_dir.mkdir(parents=True, exist_ok=True)

    clean_body = clean_chapter_for_fanqie(chapter_title, chapter_content)
    clean_title = chapter_title.replace("#", "").strip()

    # 1. 本地安全存盘
    ch_num_match = re.search(r"第(\d+)章", clean_title)
    chapter_num = ch_num_match.group(1) if ch_num_match else ""
    if chapter_num:
        local_filename = f"chapter_{int(chapter_num):03d}.txt"
    else:
        local_filename = f"chapter_{int(time.time())}.txt"

    txt_file = book_sync_dir / local_filename
    txt_file.write_text(clean_body, encoding="utf-8")

    result = {
        "status": "ok",
        "book_title": book_title,
        "chapter_title": clean_title,
        "word_count": len(clean_body),
        "local_file": str(txt_file),
        "mode": mode,
        "message": f"章节《{clean_title}》已按番茄作家规范完成段落缩进与排版存盘。"
    }

    # 2. 检查登录凭据
    if not AUTH_STATE_PATH.exists() or AUTH_STATE_PATH.stat().st_size < 50:
        result["status"] = "local_ready"
        result["message"] = f"《{clean_title}》已生成番茄规范排版存盘。尚未绑定番茄作家账号，请在【发书总控台】扫码登录或粘贴 Cookie 绑定！"
        return result

    if not is_playwright_available():
        result["status"] = "local_ready"
        result["message"] = f"《{clean_title}》已本地就绪。Playwright 未就绪，可通过篡改猴脚本挂机录入。"
        return result

    # 3. 驱动 Playwright 执行自动化注入流程
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = launch_browser(p, headless=True)
            context = browser.new_context(
                storage_state=str(AUTH_STATE_PATH),
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # 跳转至作家书籍管理总览
            page.goto(BOOK_MANAGE_URL, timeout=45000)
            page.wait_for_timeout(2500)

            # 寻找对应书名卡片并悬停触发【章节管理】
            clean_book_name = book_title.replace("《", "").replace("》", "").strip()
            book_cards = page.locator('div, li, section, article').filter(has_text=clean_book_name)
            card_count = book_cards.count()
            manage_clicked = False

            for i in range(card_count - 1, -1, -1):
                card = book_cards.nth(i)
                try:
                    if not card.is_visible():
                        continue
                    card.hover(timeout=2500)
                    page.wait_for_timeout(800)
                    manage_btn = card.get_by_text("章节管理").first
                    if manage_btn.is_visible():
                        manage_btn.click()
                        manage_clicked = True
                        break
                except Exception:
                    continue

            if not manage_clicked:
                gb = page.get_by_text("章节管理").first
                if gb.is_visible():
                    gb.click()
                    manage_clicked = True

            page.wait_for_timeout(2500)

            # 检查是否在新标签页中打开了章节管理/编辑器
            original_pages = len(context.pages)
            if original_pages > 1 and context.pages[-1] != page:
                editor_page = context.pages[-1]
            else:
                editor_page = page

            # 检查是否有中断的历史草稿
            draft_found = False
            if chapter_num:
                draft_row = editor_page.locator('tr, li, .chapter-item').filter(has_text=re.compile(f"第\\s*{chapter_num}\\s*章")).first
                if draft_row.is_visible():
                    draft_found = True
                    edit_icon = draft_row.locator('td').last.locator('svg, i, a, span, button, img').first
                    if edit_icon.is_visible():
                        edit_icon.click(force=True)
                    else:
                        draft_row.click(force=True)

            if not draft_found:
                new_btn = editor_page.get_by_role("button", name="新建章节").first
                if not new_btn.is_visible():
                    new_btn = editor_page.get_by_text("新建章节").first
                if new_btn.is_visible():
                    new_btn.click(force=True)

            page.wait_for_timeout(2500)
            if len(context.pages) > original_pages:
                editor_page = context.pages[-1]

            # 执行弹窗斩杀（清除新手引导遮罩）
            dismiss_popups(editor_page)

            # 填入章节序号与主标题
            num_inputs = editor_page.locator('input[type="text"]').element_handles()
            title_input = editor_page.get_by_placeholder("请输入标题", exact=False).first
            if not title_input.is_visible():
                title_input = editor_page.get_by_placeholder("请输入章节名", exact=False).first
            if not title_input.is_visible():
                title_input = editor_page.locator('input[type="text"]').last

            if chapter_num and len(num_inputs) >= 2:
                first_input = editor_page.locator('input[type="text"]').first
                if first_input.is_visible():
                    first_input.fill(chapter_num, force=True)
                sub_title = re.sub(r"^第\d+章[\s_]*", "", clean_title).strip()
                if title_input.is_visible():
                    title_input.fill(sub_title or clean_title, force=True)
            else:
                if title_input.is_visible():
                    title_input.fill(clean_title, force=True)

            # 填入正文并激活字数统计
            editor = editor_page.locator('.ql-editor, .ProseMirror, [contenteditable="true"]').first
            if editor.is_visible():
                editor.click(force=True)
                editor_page.evaluate("([el, text]) => { el.innerText = text; el.dispatchEvent(new Event('input', {bubbles: true})); }", [editor.element_handle(), clean_body])
                editor.click()
                editor_page.keyboard.press("End")
                editor_page.keyboard.press("Space")
                editor_page.wait_for_timeout(200)
                editor_page.keyboard.press("Backspace")

            # 保存草稿或发布
            if mode == "publish":
                next_btn = editor_page.get_by_text("下一步", exact=True).last
                if next_btn.is_visible():
                    next_btn.click(force=True)
                    editor_page.wait_for_timeout(1000)
                    dismiss_popups(editor_page)
                    # 勾选 AI 声明
                    try:
                        ai_no = editor_page.get_by_text("否", exact=True).first
                        if ai_no.is_visible():
                            ai_no.click(force=True)
                    except Exception:
                        pass
                    pub_btn = editor_page.get_by_role("button", name="确认发布").first
                    if pub_btn.is_visible():
                        pub_btn.click(force=True)
                        result["status"] = "ok"
                        result["message"] = f"章节《{clean_title}》已成功直接发布！"
            else:
                # 存草稿模式
                save_btn = editor_page.get_by_text("存草稿", exact=False).first
                if not save_btn.is_visible():
                    save_btn = editor_page.get_by_text("保存草稿", exact=False).first
                if not save_btn.is_visible():
                    save_btn = editor_page.get_by_text("保存", exact=False).first
                if save_btn.is_visible():
                    save_btn.click(force=True)
                    editor_page.wait_for_timeout(2000)
                    result["status"] = "ok"
                    result["message"] = f"章节《{clean_title}》已成功自动存入番茄作家草稿箱！"

            # 记录同步历史
            history_file = book_sync_dir / "sync_history.json"
            history = []
            if history_file.exists():
                try:
                    history = json.loads(history_file.read_text(encoding="utf-8"))
                except Exception:
                    history = []
            history.append({
                "chapter_title": clean_title,
                "synced_at": time.time(),
                "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                "mode": mode,
                "status": result["status"]
            })
            history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

            if editor_page != page:
                try:
                    editor_page.close()
                except Exception:
                    pass

            browser.close()
    except Exception as e_playwright:
        result["status"] = "local_ready"
        result["message"] = f"《{clean_title}》已本地存盘。直推执行提示: {e_playwright}"

    return result
