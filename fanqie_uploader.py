# -*- coding: utf-8 -*-
"""
====================================================================
🍅 【天道】原生番茄小说创作专区直推引擎 (Fanqie Novel Native Sync)
====================================================================
无需第三方油猴插件、无需安装外部软件，由天道服务端原生调度：
1. 扫码登录与免密凭证持久化 (output/fanqie_sync/auth_state.json)
2. 自动定位作品、新建章节、填入标题与排版后正文
3. 智能勾选“AI辅助创作”合规声明与防风控延迟策略
4. 自动保存至草稿箱 (可配置定时/直接发布)
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

# 数据持久化目录（宿主机与容器卷严格绑定）
OUTPUT_DIR = Path(__file__).parent / "output"
FANQIE_DIR = OUTPUT_DIR / "fanqie_sync"
FANQIE_DIR.mkdir(parents=True, exist_ok=True)

AUTH_STATE_PATH = FANQIE_DIR / "auth_state.json"
CONFIG_PATH = FANQIE_DIR / "config.json"
QR_CODE_PATH = FANQIE_DIR / "login_qr.png"

LOGIN_URL = "https://fanqienovel.com/author/login"
AUTHOR_ZONE_URL = "https://fanqienovel.com/author/zone"

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

def load_fanqie_config() -> dict:
    """读取番茄同步配置"""
    default_cfg = {
        "auto_upload": False,
        "publish_mode": "drafts",  # drafts (草稿箱) 或 publish (直接发布)
        "author_name": "",
        "cookies": "",
        "ai_disclosure": True,     # 默认合规勾选 AI 辅助创作声明
        "last_sync_time": "",
        "book_mappings": {}        # 天道书籍ID -> 番茄书籍ID/标题
    }
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                default_cfg.update(saved)
        except Exception:
            pass
    return default_cfg

def save_fanqie_config(cfg: dict) -> dict:
    """持久化保存番茄同步配置"""
    FANQIE_DIR.mkdir(parents=True, exist_ok=True)
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
                # 检查是否存在核心登录会话 cookie: sessionid / passport_csrf_token
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
        "last_sync_time": cfg.get("last_sync_time", "")
    }

def clean_chapter_for_fanqie(title: str, content: str) -> str:
    """
    番茄作家后台排版格式化：
    1. 首行空两格 (全角空格或制表)
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
    errors = []
    for channel in ["msedge", "chrome", None]:
        try:
            if channel:
                return p.chromium.launch(channel=channel, headless=headless)
            else:
                return p.chromium.launch(headless=headless)
        except Exception as e:
            errors.append(f"{channel or 'default'}: {e}")
    raise RuntimeError(f"未能启动可用浏览器内核: {'; '.join(errors)}")

def start_browser_login_async(headless: bool = True) -> dict:
    """
    异步启动番茄作家专区扫码登录流程：
    在后台拉起 Chromium/Edge，打开登录页，截图二维码供前端扫码，
    用户微信/抖音/番茄作家 App 扫码成功后，自动落盘 auth_state.json。
    """
    global _login_status
    if not is_playwright_available():
        return {
            "status": "error",
            "message": "系统正在后台安装 Playwright 浏览器自动化组件，请稍等 1-2 分钟后再试。"
        }

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
                browser = launch_browser(p, headless=headless)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                page = context.new_page()
                print("🍅 [番茄同步引擎] 正在打开番茄作家专区登录页面...")
                page.goto(LOGIN_URL, timeout=30000)
                page.wait_for_load_state("networkidle")

                # 寻找并截图二维码区域
                time.sleep(2)
                try:
                    # 番茄登录二维码元素通常位于 qr / login-box / canvas 区域
                    qr_el = page.query_selector(".qrcode-img, .qrcode-wrap, canvas, [class*='qr'], [class*='Qr']")
                    if qr_el:
                        qr_el.screenshot(path=str(QR_CODE_PATH))
                    else:
                        page.screenshot(path=str(QR_CODE_PATH))
                    _login_status["qr_ready"] = True
                    _login_status["qr_path"] = str(QR_CODE_PATH)
                    print(f"🍅 [番茄同步引擎] 登录二维码已就绪，已保存至: {QR_CODE_PATH}")
                except Exception as e_qr:
                    print(f"🍅 [番茄同步引擎] 二维码截取警告: {e_qr}")
                    page.screenshot(path=str(QR_CODE_PATH))
                    _login_status["qr_ready"] = True

                # 轮询等待登录成功（最多等待 180 秒）
                for _ in range(90):
                    time.sleep(2)
                    cur_url = page.url
                    # 登录成功会跳转至 zone / books / author 后台
                    if "zone" in cur_url or "book" in cur_url or "home" in cur_url or "author" in cur_url and "login" not in cur_url:
                        print("🍅 [番茄同步引擎] 检测到登录成功跳转！正在落盘会话凭据...")
                        context.storage_state(path=str(AUTH_STATE_PATH))
                        cfg = load_fanqie_config()
                        # 尝试提取作者名称
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
                        print(f"🍅 [番茄同步引擎] 作家凭据已安全落盘至 {AUTH_STATE_PATH}！")
                        break
                browser.close()
        except Exception as e_worker:
            print(f"🍅 [番茄同步引擎] 登录流程异常: {e_worker}")
            _login_status["last_error"] = str(e_worker)
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
    原生执行单章上传至番茄小说作家草稿箱：
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
    if ch_num_match:
        ch_num = int(ch_num_match.group(1))
        local_filename = f"chapter_{ch_num:03d}.txt"
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
        "message": f"第《{clean_title}》章已按番茄作家规范完成段落缩进与排版存盘。"
    }

    # 2. 检查是否可执行原生自动化上传
    if not AUTH_STATE_PATH.exists() or AUTH_STATE_PATH.stat().st_size < 50:
        result["status"] = "local_ready"
        result["message"] = f"《{clean_title}》已生成番茄规范排版存盘。尚未绑定番茄作家账号，请在【管理控制台 -> 番茄直推】扫码登录后即可一键直传草稿箱！"
        return result

    if not is_playwright_available():
        result["status"] = "local_ready"
        result["message"] = f"《{clean_title}》已本地就绪。组件安装中，完成后即可后台直推。"
        return result

    # 3. 驱动 Playwright 无头浏览器自动推送
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = launch_browser(p, headless=True)
            context = browser.new_context(
                storage_state=str(AUTH_STATE_PATH),
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            print(f"🍅 [番茄同步引擎] 正在进入作家专区上传章节《{clean_title}》...")
            page.goto(AUTHOR_ZONE_URL, timeout=30000)
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            # 寻找对应书名并点击进入草稿/新建章节
            # 兼容多种后台 UI 选择器
            book_matched = False
            book_links = page.query_selector_all("a, div[class*='book'], [class*='title']")
            for link in book_links:
                try:
                    if book_title and book_title in link.inner_text():
                        link.click()
                        book_matched = True
                        break
                except Exception:
                    continue

            time.sleep(2)
            # 点击“新建章节”或“创建章节”
            create_btn = page.query_selector("button:has-text('新建章节'), a:has-text('新建章节'), button:has-text('写新章节'), [class*='create-chapter']")
            if create_btn:
                create_btn.click()
                page.wait_for_load_state("networkidle")
                time.sleep(2)

            # 填写章节标题
            title_input = page.query_selector("input[placeholder*='标题'], input[class*='title'], [placeholder*='第x章']")
            if title_input:
                title_input.fill(clean_title)

            # 填写正文内容 (富文本编辑器通常为 contenteditable div 或 textarea)
            content_editor = page.query_selector("div[contenteditable='true'], textarea[placeholder*='正文'], .ql-editor, [class*='editor-content']")
            if content_editor:
                content_editor.fill(clean_body)

            # 智能合规：勾选 AI 辅助创作声明 (若有弹窗或单选框)
            ai_checkbox = page.query_selector("input[type='checkbox'][value*='ai'], label:has-text('AI'), span:has-text('AI辅助')")
            if ai_checkbox:
                try:
                    ai_checkbox.click()
                except Exception:
                    pass

            time.sleep(1)

            # 提交存稿或发布
            if mode == "publish":
                submit_btn = page.query_selector("button:has-text('确定发布'), button:has-text('立即发布'), button:has-text('发布')")
            else:
                submit_btn = page.query_selector("button:has-text('存草稿'), button:has-text('保存草稿'), button:has-text('保存为草稿'), button:has-text('保存')")

            if submit_btn:
                submit_btn.click()
                time.sleep(3)
                result["status"] = "ok"
                result["message"] = f"🍅 成功！章节《{clean_title}》已原生直推至番茄小说【{'直接发布' if mode == 'publish' else '作家草稿箱'}】！"
            else:
                result["status"] = "warning"
                result["message"] = f"已进入番茄后台并填入章节《{clean_title}》，等待人工二次确认提交。"

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

            browser.close()
    except Exception as e_playwright:
        print(f"🍅 [番茄同步引擎] 自动化直推告警: {e_playwright}")
        result["status"] = "local_ready"
        result["message"] = f"《{clean_title}》已生成番茄规范本地存盘。后台直推暂未能完成 ({e_playwright})，可随时一键重试。"

    return result
