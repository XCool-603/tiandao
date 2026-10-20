// ==UserScript==
// @name         天道 · 番茄小说全自动挂机发书助手
// @namespace    http://tampermonkey.net/
// @version      1.2.0
// @description  连接天道本地推演引擎，自动将新推演章节无缝填入番茄作家后台草稿箱，实现写一章传一章全自动挂机！
// @author       Tiandao AI
// @match        *://fanqienovel.com/*
// @match        *://*.fanqienovel.com/*
// @match        *://novel.snssdk.com/*
// @grant        GM_xmlhttpRequest
// @connect      localhost
// @connect      127.0.0.1
// @connect      *
// @run-at       document-idle
// ==/UserScript==

(function() {
    'use strict';

    // 默认自适应当前服务端端口 (8088 / 28088 自动识别)
    let API_BASE = localStorage.getItem('tiandao_api_base') || "http://localhost:8088";
    let isRunning = true;
    let pollTimer = null;
    let isUploading = false;
    let currentChapter = null;

    // 1. 创建右下角挂机悬浮面板
    function createWidget() {
        if (document.getElementById('tiandao-bot-widget')) return;
        const div = document.createElement('div');
        div.id = 'tiandao-bot-widget';
        div.style.cssText = `
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 999999;
            background: rgba(18, 22, 34, 0.96);
            color: #f1f5f9;
            border: 1px solid #3b82f6;
            border-radius: 12px;
            padding: 14px 18px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.6);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 13px;
            min-width: 300px;
            max-width: 380px;
            backdrop-filter: blur(8px);
        `;

        div.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <div style="font-weight: 700; color: #60a5fa; display: flex; align-items: center; gap: 6px;">
                    <span>[天道] 自动发书助手</span>
                    <span id="tiandao-status-dot" style="display:inline-block; width:9px; height:9px; border-radius:50%; background:#94a3b8;" title="连接状态"></span>
                </div>
                <div style="display: flex; gap: 4px;">
                    <button id="tiandao-btn-manual" style="background:#0f766e; color:#fff; border:none; padding:3px 8px; border-radius:5px; cursor:pointer; font-size:11px;" title="将当前待同步章节强制填入当前编辑框">手动填入</button>
                    <button id="tiandao-btn-toggle" style="background:#2563eb; color:#fff; border:none; padding:3px 8px; border-radius:5px; cursor:pointer; font-size:11px;">运行中</button>
                </div>
            </div>
            <div id="tiandao-info-text" style="font-size:11.5px; color:#94a3b8; line-height:1.5;">
                正在探测天道推演引擎...
            </div>
            <div id="tiandao-last-log" style="font-size:11px; color:#38bdf8; margin-top:6px; word-break:break-all;">
                准备就绪
            </div>
            <div style="margin-top: 8px; padding-top: 6px; border-top: 1px dashed rgba(255,255,255,0.15); display: flex; justify-content: space-between; align-items: center; font-size: 10.5px; color: #64748b;">
                <span id="tiandao-current-url" style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:210px;">${API_BASE}</span>
                <span id="tiandao-btn-seturl" style="color:#60a5fa; cursor:pointer; text-decoration:underline;">修改地址</span>
            </div>
        `;
        document.body.appendChild(div);

        document.getElementById('tiandao-btn-toggle').onclick = () => {
            isRunning = !isRunning;
            const btn = document.getElementById('tiandao-btn-toggle');
            const dot = document.getElementById('tiandao-status-dot');
            if (isRunning) {
                btn.textContent = '运行中';
                btn.style.background = '#2563eb';
                dot.style.background = '#10b981';
                updateLog('自动发书监听已恢复');
                checkPendingChapter();
            } else {
                btn.textContent = '已暂停';
                btn.style.background = '#64748b';
                dot.style.background = '#94a3b8';
                updateLog('自动发书已暂停');
            }
        };

        document.getElementById('tiandao-btn-manual').onclick = () => {
            if (currentChapter) {
                handleUploadChapter(currentChapter, true);
            } else {
                updateLog('暂无待同步章节或未拉取到数据');
                checkPendingChapter();
            }
        };

        document.getElementById('tiandao-btn-seturl').onclick = () => {
            const newUrl = prompt("请输入天道服务访问地址（如 http://localhost:8088 或 http://127.0.0.1:8088）：", API_BASE);
            if (newUrl && newUrl.trim()) {
                API_BASE = newUrl.trim().replace(/\/$/, "");
                localStorage.setItem('tiandao_api_base', API_BASE);
                document.getElementById('tiandao-current-url').textContent = API_BASE;
                updateLog(`服务地址已切换为: ${API_BASE}`);
                checkPendingChapter();
            }
        };
    }

    function updateLog(msg) {
        const el = document.getElementById('tiandao-last-log');
        if (el) el.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    }

    function updateInfo(info) {
        const el = document.getElementById('tiandao-info-text');
        if (el) el.innerHTML = info;
    }

    // 跨域请求包装 (支持 GM_xmlhttpRequest 绕过浏览器严格跨域限制)
    function httpRequest(url, options = {}) {
        return new Promise((resolve, reject) => {
            if (typeof GM_xmlhttpRequest !== 'undefined') {
                GM_xmlhttpRequest({
                    method: options.method || 'GET',
                    url: url,
                    headers: options.headers || {},
                    data: options.body || null,
                    timeout: 8000,
                    onload: (res) => {
                        try {
                            resolve(JSON.parse(res.responseText));
                        } catch (e) {
                            resolve(res.responseText);
                        }
                    },
                    onerror: (err) => reject(err),
                    ontimeout: () => reject(new Error("请求超时"))
                });
            } else {
                fetch(url, options).then(r => r.json()).then(resolve).catch(reject);
            }
        });
    }

    // 核心：检查待上传章节
    async function checkPendingChapter() {
        if (!isRunning || isUploading) return;
        try {
            const res = await httpRequest(`${API_BASE}/api/fanqie/pending_chapter`);
            if (res && res.status === 'ok') {
                const dot = document.getElementById('tiandao-status-dot');
                if (dot) dot.style.background = '#10b981';
                
                if (res.has_pending && res.chapter) {
                    currentChapter = res.chapter;
                    updateInfo(`作品: 《${res.book_title || '当前小说'}》 | 待发: 第 ${res.chapter.chapter_id} 章 (${res.chapter.word_count} 字)`);
                    await handleUploadChapter(res.chapter);
                } else {
                    currentChapter = null;
                    updateInfo(`作品: 《${res.book_title || '当前小说'}》 | 全部章节已同步 (${res.synced_count || 0}/${res.total_chapters || 0} 章)`);
                    updateLog('暂无新章节，推演新章节后将自动同步...');
                }
                return;
            }
        } catch (err) {
            // 端口自适应：如果在 8088 失败，尝试 28088；反之亦然
            const candidate = API_BASE.includes("8088") && !API_BASE.includes("28088") ? "http://localhost:28088" : "http://localhost:8088";
            try {
                const fb = await httpRequest(`${candidate}/api/fanqie/pending_chapter`);
                if (fb && fb.status === 'ok') {
                    API_BASE = candidate;
                    localStorage.setItem('tiandao_api_base', API_BASE);
                    const dot = document.getElementById('tiandao-status-dot');
                    if (dot) dot.style.background = '#10b981';
                    const curUrlEl = document.getElementById('tiandao-current-url');
                    if (curUrlEl) curUrlEl.textContent = API_BASE;
                    updateLog(`自适应连接成功: ${API_BASE}`);
                    checkPendingChapter();
                    return;
                }
            } catch (e2) {}

            const dot = document.getElementById('tiandao-status-dot');
            if (dot) dot.style.background = '#ef4444';
            updateLog(`无法连接天道 (${API_BASE})，请确认控制台服务已启动`);
        }
    }

    // 自动在番茄页面寻找元素并填入草稿
    async function handleUploadChapter(chapter, forceManual = false) {
        if (!forceManual && isUploading) return;
        isUploading = true;
        updateLog(`正在填充第 ${chapter.chapter_id} 章《${chapter.chapter_title}》...`);
        updateInfo(`<span style="color:#f59e0b;">正在录入第 ${chapter.chapter_id} 章 (${chapter.word_count} 字)...</span>`);

        try {
            // 1. 查找标题输入框
            let titleInput = document.querySelector('input[placeholder*="标题"]') || 
                             document.querySelector('input[placeholder*="章节名"]') ||
                             document.querySelector('.chapter-title-input input') ||
                             document.querySelector('.semi-input[placeholder*="标题"]') ||
                             document.querySelector('input.publish-header-input') ||
                             document.querySelector('input[type="text"]');
            
            // 2. 查找正文输入框 (ProseMirror 或 contenteditable 或 textarea)
            let bodyEditor = document.querySelector('.ProseMirror') || 
                             document.querySelector('div[contenteditable="true"]') ||
                             document.querySelector('.public-DraftEditor-content') ||
                             document.querySelector('textarea[placeholder*="正文"]') ||
                             document.querySelector('textarea.semi-input-textarea');

            if (!titleInput || !bodyEditor) {
                // 如果当前不在编辑页，尝试寻找“新建章节”按钮
                let newBtn = Array.from(document.querySelectorAll('button, a, span')).find(el => {
                    const txt = (el.textContent || "").trim();
                    return txt === '新建章节' || txt === '写新章' || txt === '发布章节' || txt === '创建章节';
                });
                if (newBtn) {
                    updateLog('检测到新建章节按钮，自动点击进入...');
                    newBtn.click();
                    setTimeout(() => { isUploading = false; }, 2500);
                    return;
                }
                updateLog('提示: 请在番茄作家后台打开作品并进入“新建章节/编辑”页面');
                isUploading = false;
                return;
            }

            // 填入标题
            titleInput.focus();
            titleInput.value = chapter.chapter_title;
            titleInput.dispatchEvent(new Event('input', { bubbles: true }));
            titleInput.dispatchEvent(new Event('change', { bubbles: true }));
            titleInput.dispatchEvent(new Event('blur', { bubbles: true }));

            // 填入正文
            if (bodyEditor.tagName.toLowerCase() === 'textarea') {
                bodyEditor.focus();
                bodyEditor.value = chapter.content;
                bodyEditor.dispatchEvent(new Event('input', { bubbles: true }));
                bodyEditor.dispatchEvent(new Event('change', { bubbles: true }));
                bodyEditor.dispatchEvent(new Event('blur', { bubbles: true }));
            } else {
                bodyEditor.focus();
                // 兼容富文本 ProseMirror
                if (bodyEditor.classList.contains('ProseMirror')) {
                    // 构造段落 HTML
                    const paragraphs = chapter.content.split('\n').filter(p => p.trim());
                    const html = paragraphs.map(p => `<p>${p.trim()}</p>`).join('');
                    document.execCommand('selectAll', false, null);
                    document.execCommand('insertHTML', false, html);
                } else {
                    bodyEditor.innerText = chapter.content;
                }
                bodyEditor.dispatchEvent(new Event('input', { bubbles: true }));
                bodyEditor.dispatchEvent(new Event('change', { bubbles: true }));
            }

            // 等待页面反应
            await new Promise(r => setTimeout(r, 1200));

            // 寻找保存草稿按钮
            let saveBtn = Array.from(document.querySelectorAll('button')).find(el => {
                const txt = (el.textContent || "").trim();
                return txt.includes('存草稿') || txt.includes('保存草稿') || txt === '保存' || txt === '暂存';
            });

            if (saveBtn && !saveBtn.disabled) {
                saveBtn.click();
                updateLog(`第 ${chapter.chapter_id} 章已自动点击存草稿！`);
            } else {
                updateLog(`第 ${chapter.chapter_id} 章已填入标题和正文，请手动点击保存`);
            }

            // 上报同步成功状态给天道服务端
            await httpRequest(`${API_BASE}/api/fanqie/confirm_uploaded`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    book_id: chapter.book_id,
                    chapter_id: chapter.chapter_id,
                    mode: 'draft'
                })
            });

            updateInfo(`第 ${chapter.chapter_id} 章《${chapter.chapter_title}》已成功同步记录！`);
        } catch (e) {
            updateLog(`同步发生异常: ${e.message}`);
        } finally {
            isUploading = false;
        }
    }

    // 初始化运行
    function init() {
        createWidget();
        checkPendingChapter();
        if (!pollTimer) {
            pollTimer = setInterval(checkPendingChapter, 8000);
        }
    }

    if (document.readyState === 'loading') {
        window.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
