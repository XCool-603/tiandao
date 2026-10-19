// ==UserScript==
// @name         天道 · 番茄小说全自动挂机发书助手
// @namespace    http://tampermonkey.net/
// @version      1.1.0
// @description  连接天道本地推演引擎，自动将新推演章节无缝填入番茄作家后台草稿箱，实现写一章传一章全自动挂机！
// @author       Tiandao AI
// @match        https://fanqienovel.com/writer/zone*
// @match        https://fanqienovel.com/main/writer*
// @match        https://fanqienovel.com/creator*
// @grant        GM_xmlhttpRequest
// @connect      localhost
// @connect      127.0.0.1
// @run-at       document-idle
// ==/UserScript==

(function() {
    'use strict';

    let API_BASE = localStorage.getItem('tiandao_api_base') || "http://localhost:28088";
    let isRunning = true;
    let pollTimer = null;
    let isUploading = false;

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
            background: rgba(18, 22, 34, 0.95);
            color: #f1f5f9;
            border: 1px solid #3b82f6;
            border-radius: 12px;
            padding: 14px 18px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 13px;
            min-width: 280px;
            backdrop-filter: blur(8px);
        `;

        div.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <div style="font-weight: 700; color: #60a5fa; display: flex; align-items: center; gap: 6px;">
                    <span>【天道】自动挂机发书</span>
                    <span id="tiandao-status-dot" style="display:inline-block; width:8px; height:8px; border-radius:50%; background:#10b981;"></span>
                </div>
                <button id="tiandao-btn-toggle" style="background:#2563eb; color:#fff; border:none; padding:3px 10px; border-radius:6px; cursor:pointer; font-size:11px;">运行中</button>
            </div>
            <div id="tiandao-info-text" style="font-size:11.5px; color:#94a3b8; line-height:1.5;">
                正在监听天道推演章节...
            </div>
            <div id="tiandao-last-log" style="font-size:11px; color:#38bdf8; margin-top:6px; word-break:break-all;">
                准备就绪
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
                updateLog('挂机已恢复');
                checkPendingChapter();
            } else {
                btn.textContent = '已暂停';
                btn.style.background = '#64748b';
                dot.style.background = '#94a3b8';
                updateLog('挂机已暂停');
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

    // 跨域请求包装
    function httpRequest(url, options = {}) {
        return new Promise((resolve, reject) => {
            if (typeof GM_xmlhttpRequest !== 'undefined') {
                GM_xmlhttpRequest({
                    method: options.method || 'GET',
                    url: url,
                    headers: options.headers || {},
                    data: options.body || null,
                    onload: (res) => {
                        try {
                            resolve(JSON.parse(res.responseText));
                        } catch (e) {
                            resolve(res.responseText);
                        }
                    },
                    onerror: (err) => reject(err)
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
                document.getElementById('tiandao-status-dot').style.background = '#10b981';
                if (res.has_pending && res.chapter) {
                    await handleUploadChapter(res.chapter);
                } else {
                    updateInfo(`书名: 《${res.book_title || '当前作品'}》 | 已同步: ${res.synced_count || 0}/${res.total_chapters || 0} 章`);
                    updateLog('所有已生成章节均已同步，等待推演新章节...');
                }
            }
        } catch (err) {
            // 自动在 28088 与 8088 端口之间智能回退尝试
            if (API_BASE.includes("28088")) {
                try {
                    const fb = await httpRequest(`http://localhost:8088/api/fanqie/pending_chapter`);
                    if (fb && fb.status === 'ok') {
                        API_BASE = "http://localhost:8088";
                        localStorage.setItem('tiandao_api_base', API_BASE);
                        document.getElementById('tiandao-status-dot').style.background = '#10b981';
                        return;
                    }
                } catch(e2){}
            }
            document.getElementById('tiandao-status-dot').style.background = '#ef4444';
            updateLog(`未连接到天道服务 (${API_BASE})，请确认天道已启动`);
        }
    }

    // 自动在番茄页面填充并保存草稿
    async function handleUploadChapter(chapter) {
        isUploading = true;
        updateLog(`正在同步第 ${chapter.chapter_id} 章《${chapter.chapter_title}》...`);
        updateInfo(`<span style="color:#f59e0b;">⚡ 正在录入第 ${chapter.chapter_id} 章 (${chapter.word_count} 字)...</span>`);

        try {
            // 1. 查找标题输入框
            let titleInput = document.querySelector('input[placeholder*="标题"]') || 
                             document.querySelector('.chapter-title-input input') ||
                             document.querySelector('input[type="text"]');
            
            // 2. 查找正文输入框 (ProseMirror 或 textarea 或 contenteditable)
            let bodyEditor = document.querySelector('.ProseMirror') || 
                             document.querySelector('div[contenteditable="true"]') ||
                             document.querySelector('textarea[placeholder*="正文"]');

            if (!titleInput || !bodyEditor) {
                // 如果当前不在编辑页，尝试寻找“新建章节”按钮
                let newBtn = Array.from(document.querySelectorAll('button, a')).find(el => 
                    el.textContent.includes('新建章节') || el.textContent.includes('写新章') || el.textContent.includes('发布章节')
                );
                if (newBtn) {
                    updateLog('正在自动点击“新建章节”...');
                    newBtn.click();
                    setTimeout(() => { isUploading = false; }, 2000);
                    return;
                }
                updateLog('⚠️ 请先在页面中进入作品章节发布管理页');
                isUploading = false;
                return;
            }

            // 填入标题
            titleInput.value = chapter.chapter_title;
            titleInput.dispatchEvent(new Event('input', { bubbles: true }));
            titleInput.dispatchEvent(new Event('change', { bubbles: true }));

            // 填入正文
            if (bodyEditor.tagName.toLowerCase() === 'textarea') {
                bodyEditor.value = chapter.content;
                bodyEditor.dispatchEvent(new Event('input', { bubbles: true }));
                bodyEditor.dispatchEvent(new Event('change', { bubbles: true }));
            } else {
                bodyEditor.focus();
                bodyEditor.innerText = chapter.content;
                bodyEditor.dispatchEvent(new Event('input', { bubbles: true }));
            }

            // 稍微等待渲染
            await new Promise(r => setTimeout(r, 1000));

            // 寻找保存草稿按钮
            let saveBtn = Array.from(document.querySelectorAll('button')).find(el => 
                el.textContent.includes('存草稿') || 
                el.textContent.includes('保存草稿') ||
                el.textContent.includes('保存')
            );

            if (saveBtn && !saveBtn.disabled) {
                saveBtn.click();
                updateLog(`✅ 第 ${chapter.chapter_id} 章已自动点击存草稿！`);
            } else {
                updateLog(`第 ${chapter.chapter_id} 章已填入，等待确认`);
            }

            // 上报成功状态给天道服务端
            await httpRequest(`${API_BASE}/api/fanqie/confirm_uploaded`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    book_id: chapter.book_id,
                    chapter_id: chapter.chapter_id,
                    mode: 'draft'
                })
            });

            updateInfo(`🎉 第 ${chapter.chapter_id} 章已成功同步存盘！`);
        } catch (e) {
            updateLog(`❌ 同步发生异常: ${e.message}`);
        } finally {
            isUploading = false;
        }
    }

    // 初始化运行
    window.addEventListener('load', () => {
        setTimeout(() => {
            createWidget();
            checkPendingChapter();
            pollTimer = setInterval(checkPendingChapter, 10000); // 每 10 秒轮询
        }, 1500);
    });

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        createWidget();
        checkPendingChapter();
        if (!pollTimer) pollTimer = setInterval(checkPendingChapter, 10000);
    }
})();
