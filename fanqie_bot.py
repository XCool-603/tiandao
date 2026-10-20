#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天道 x Fanqie Auto Publish 整合版挂机发书机器人 (Fanqie Auto Uploader Bot)
基于 Playwright 驱动系统原生 Microsoft Edge 浏览器，
内置：
1. 空间物理坐标弹窗斩杀（清除新手引导遮罩）
2. 小说卡片悬停探测 (Card Hover -> 章节管理)
3. 多标签页智能跟随 (New Tab Tracking)
4. ProseMirror 原生事件注入与字数统计激活
5. 断点续检与章节草稿覆盖防重
"""

import os
import sys
import time
import json
import re
import urllib.request
import urllib.parse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
FANQIE_DIR = OUTPUT_DIR / "fanqie_sync"
FANQIE_DIR.mkdir(parents=True, exist_ok=True)
AUTH_STATE_PATH = FANQIE_DIR / "auth_state.json"

BOOK_MANAGE_URL = "https://fanqienovel.com/main/writer/book-manage"
LOGIN_URL = "https://fanqienovel.com/main/writer/login"

def get_server_api_base():
    # 默认优先探测远程与本地服务
    candidates = [
        "https://book.si2api.top",
        "http://book.si2api.top",
        "http://localhost:8088",
        "http://127.0.0.1:8088"
    ]
    for c in candidates:
        try:
            req = urllib.request.urlopen(f"{c}/api/fanqie/config", timeout=2)
            if req.status == 200:
                return c
        except Exception:
            pass
    return "https://book.si2api.top"

SERVER_API = get_server_api_base()

def fetch_json(url, data=None):
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8") if data is not None else None,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"status": "error", "message": str(e)}

def dismiss_popups(page):
    """清除遮挡视线的新手引导浮层与干扰弹窗"""
    for _ in range(3):
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(150)
        except Exception:
            pass

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

    try:
        submit_btn = page.get_by_role("button", name="提交").first
        if submit_btn.is_visible():
            submit_btn.click(force=True)
            page.wait_for_timeout(500)
    except Exception:
        pass

    try:
        cancel_btn = page.get_by_role("button", name="取消").last
        if cancel_btn.is_visible():
            cancel_btn.click(force=True)
            page.wait_for_timeout(500)
    except Exception:
        pass

def ensure_login(playwright):
    """确保具备有效的作家后台登录凭据"""
    if AUTH_STATE_PATH.exists() and AUTH_STATE_PATH.stat().st_size > 50:
        return True

    print("\n" + "=" * 60)
    print("首次使用需登录番茄作家后台，正在启动 Edge 浏览器窗口...")
    print("=" * 60)

    browser = playwright.chromium.launch(channel="msedge", headless=False)
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    page.goto(LOGIN_URL, timeout=45000)

    print("\n请在弹出的浏览器中通过手机扫码或验证码登录番茄作家后台。")
    print("登录成功并进入后台页面后，回到此处按回车继续...")
    input(">>> 确认已完成登录请按回车：")

    context.storage_state(path=str(AUTH_STATE_PATH))
    print(f"登录凭据已成功保存至: {AUTH_STATE_PATH}")
    browser.close()
    return True

def upload_chapter_to_fanqie(context, book_title, chapter_num, chapter_title, content, mode="draft"):
    """执行单个章节的自动发布或存草稿"""
    page = context.new_page()
    try:
        print(f"\n正在处理: 第 {chapter_num} 章《{chapter_title}》...")
        page.goto(BOOK_MANAGE_URL, timeout=45000)
        page.wait_for_timeout(2500)

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
        original_pages = len(context.pages)
        if original_pages > 1 and context.pages[-1] != page:
            editor_page = context.pages[-1]
        else:
            editor_page = page

        # 检查是否已存在草稿
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

        # 弹窗斩杀
        dismiss_popups(editor_page)

        # 填入章节标题
        num_inputs = editor_page.locator('input[type="text"]').element_handles()
        title_input = editor_page.get_by_placeholder("请输入标题", exact=False).first
        if not title_input.is_visible():
            title_input = editor_page.get_by_placeholder("请输入章节名", exact=False).first
        if not title_input.is_visible():
            title_input = editor_page.locator('input[type="text"]').last

        full_title = f"第{chapter_num}章 {chapter_title}" if chapter_num and "章" not in chapter_title else chapter_title
        if chapter_num and len(num_inputs) >= 2:
            first_input = editor_page.locator('input[type="text"]').first
            if first_input.is_visible():
                first_input.fill(str(chapter_num), force=True)
            sub_title = re.sub(r"^第\d+章[\s_]*", "", chapter_title).strip()
            if title_input.is_visible():
                title_input.fill(sub_title or chapter_title, force=True)
        else:
            if title_input.is_visible():
                title_input.fill(full_title, force=True)

        # 填入正文并激活字数统计
        editor = editor_page.locator('.ql-editor, .ProseMirror, [contenteditable="true"]').first
        if editor.is_visible():
            editor.click(force=True)
            editor_page.evaluate("([el, text]) => { el.innerText = text; el.dispatchEvent(new Event('input', {bubbles: true})); }", [editor.element_handle(), content])
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
                try:
                    ai_no = editor_page.get_by_text("否", exact=True).first
                    if ai_no.is_visible():
                        ai_no.click(force=True)
                except Exception:
                    pass
                pub_btn = editor_page.get_by_role("button", name="确认发布").first
                if pub_btn.is_visible():
                    pub_btn.click(force=True)
                    print(f"第 {chapter_num} 章已直接发布！")
        else:
            save_btn = editor_page.get_by_text("存草稿", exact=False).first
            if not save_btn.is_visible():
                save_btn = editor_page.get_by_text("保存草稿", exact=False).first
            if not save_btn.is_visible():
                save_btn = editor_page.get_by_text("保存", exact=False).first
            if save_btn.is_visible():
                save_btn.click(force=True)
                editor_page.wait_for_timeout(2000)
                print(f"第 {chapter_num} 章已存入草稿箱！")

        if editor_page != page:
            try:
                editor_page.close()
            except Exception:
                pass
        page.close()
        return True
    except Exception as e:
        print(f"第 {chapter_num} 章处理异常: {e}")
        try:
            page.close()
        except Exception:
            pass
        return False

def main():
    import argparse
    parser = argparse.ArgumentParser(description="天道 x 番茄自动发书机器人 (Playwright 强化版)")
    parser.add_argument("--server", type=str, default=None, help="天道服务地址")
    parser.add_argument("--login", action="store_true", help="仅执行扫码登录并保存凭据")
    parser.add_argument("--batch", type=int, default=None, help="本次发布的章节数量")
    parser.add_argument("--all", action="store_true", help="发布所有待发章节")
    parser.add_argument("--daemon", action="store_true", help="守护进程模式持续监听新章节")
    parser.add_argument("--headless", action="store_true", help="无头模式运行")
    parser.add_argument("--mode", type=str, default="draft", choices=["draft", "publish"], help="发布模式")
    args = parser.parse_args()

    global SERVER_API
    if args.server:
        SERVER_API = args.server.rstrip("/")

    print("=" * 60)
    print("天道 x 番茄自动发书机器人 (Playwright 强化版)")
    print(f"连接服务地址: {SERVER_API}")
    print(f"发布模式: {'存入草稿箱' if args.mode == 'draft' else '直接公开发布'}")
    print("=" * 60)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("未检测到 playwright 库，请先执行: pip install playwright")
        return

    with sync_playwright() as p:
        ensure_login(p)

        if args.login:
            print("登录凭据已就绪，退出。")
            return

        # 启动持久化会话浏览器
        browser = p.chromium.launch(channel="msedge", headless=args.headless)
        context = browser.new_context(
            storage_state=str(AUTH_STATE_PATH),
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )

        print("\n正在从天道服务拉取待发布章节...")
        success_total = 0
        target_limit = args.batch

        while True:
            if target_limit is not None and success_total >= target_limit:
                print(f"\n已达到设定的发布数量限制 ({success_total} 章)，任务顺利完成！")
                break

            res = fetch_json(f"{SERVER_API}/api/fanqie/pending_chapter")
            if not res or res.get("status") != "ok" or not res.get("has_pending"):
                print(f"暂无待发章节 (已同步 {res.get('synced_count', 0)} / {res.get('total_chapters', 0)} 章)。")
                if args.all or target_limit is not None:
                    print("所有指定章节均已发布完成，退出。")
                    break
                print("挂机轮询中，将在天道推演新章节后自动同步...")
                time.sleep(10)
                continue

            chap = res["chapter"]
            book_title = res.get("book_title", "小说作品")
            book_id = res.get("book_id", "")
            cid = chap.get("chapter_id")
            title = chap.get("chapter_title", "")
            content = chap.get("content", "")

            ok = upload_chapter_to_fanqie(context, book_title, cid, title, content, mode=args.mode)
            if ok:
                success_total += 1
                fetch_json(f"{SERVER_API}/api/fanqie/confirm_uploaded", {
                    "book_id": book_id,
                    "chapter_id": cid,
                    "mode": "playwright_bot_draft"
                })
                print(f"已上报同步成功 (已完成 {success_total} 章)，等待 3 秒继续处理下一章...")
                time.sleep(3)
            else:
                print("遇到异常，等待 10 秒后重试...")
                time.sleep(10)

        browser.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n机器人已退出。")
