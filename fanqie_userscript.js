// ==UserScript==
// @name         天道 · 番茄小说全自动挂机发书助手
// @namespace    http://tampermonkey.net/
// @version      1.6.0
// @description  连接天道推演引擎，支持新建作品一键填入、空间坐标弹窗穿透、智能断点记忆、全书101章自动连发无人值守挂机！
// @author       Tiandao AI
// @match        *://fanqienovel.com/*
// @match        *://*.fanqienovel.com/*
// @match        *://novel.snssdk.com/*
// @grant        GM_xmlhttpRequest
// @connect      book.si2api.top
// @connect      *.si2api.top
// @connect      localhost
// @connect      127.0.0.1
// @connect      *
// @run-at       document-idle
// ==/UserScript==

(function() {
    'use strict';

    // 默认自适应部署服务地址
    const EMBEDDED_SERVER = "https://book.si2api.top";
    let stored = localStorage.getItem('tiandao_api_base');
    if (!stored || stored.includes("localhost") || stored.includes("127.0.0.1")) {
        stored = EMBEDDED_SERVER;
        localStorage.setItem('tiandao_api_base', stored);
    }
    let API_BASE = stored;

    let isRunning = true;
    let autoNextChapter = true; // 自动连续发布下一章
    let pollTimer = null;
    let isUploading = false;
    let currentChapter = null;
    let isCollapsed = false;

    // 本地持久化章节指针（即使服务端锁死也能自主推进）
    let currentChapIndex = parseInt(localStorage.getItem('tiandao_current_chap') || '1', 10);
    let activeBookId = localStorage.getItem('tiandao_active_bid') || '';
    let activeBookTitle = localStorage.getItem('tiandao_active_btitle') || '';
    let totalChaptersCount = parseInt(localStorage.getItem('tiandao_total_chaps') || '101', 10);

    // 格式化番茄首行缩进与去除 Markdown 杂乱字符
    function cleanForFanqie(title, text) {
        if (!text) return "";
        let clean = text.replace(/^#+\s*.*?\n/g, "")
                        .replace(/```[a-zA-Z]*/g, "")
                        .replace(/```/g, "")
                        .replace(/\*\*([^*]+)\*\*/g, "$1")
                        .replace(/\*([^*]+)\*/g, "$1");
        let lines = clean.split('\n').map(l => l.trim()).filter(l => l.length > 0);
        return lines.map(l => "　　" + l).join('\n\n');
    }

    // 弹窗斩杀机制：空间物理坐标过滤（Y > 100）消除新手向导、错别字拦截、风险检测拦截
    function dismissPopups() {
        const guideTexts = ["下一步", "完成", "我知道了", "跳过", "知道了", "同意并继续"];
        const allCandidates = Array.from(document.querySelectorAll('button, div, span, a'));
        for (const el of allCandidates) {
            const txt = (el.textContent || "").trim();
            if (guideTexts.includes(txt) && el.offsetParent !== null) {
                const rect = el.getBoundingClientRect();
                if (rect && rect.top > 100) {
                    try {
                        el.click();
                        updateLog(`已穿透新手引导遮罩: [${txt}]`);
                    } catch(e) {}
                }
            }
        }
        // 自动确认错别字提示弹窗
        for (const b of document.querySelectorAll('button')) {
            const txt = (b.textContent || "").trim();
            if ((txt === '提交' || txt === '确认提交') && b.offsetParent !== null) {
                const modal = b.closest('.semi-modal, .modal, [class*="modal"], [class*="dialog"]');
                if (modal && modal.textContent.includes('错别字')) {
                    b.click();
                    updateLog('已自动确认错别字修改提示');
                }
            }
        }
        // 自动取消内容风险检测弹窗以节约额度
        for (const b of document.querySelectorAll('button')) {
            const txt = (b.textContent || "").trim();
            if (txt === '取消' && b.offsetParent !== null) {
                const modal = b.closest('.semi-modal, .modal, [class*="modal"], [class*="dialog"]');
                if (modal && modal.textContent.includes('风险检测')) {
                    b.click();
                    updateLog('已自动取消内容风险检测弹窗');
                }
            }
        }
    }

    // 创建右下角挂机悬浮面板
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
            padding: 14px 16px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.6);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            font-size: 13px;
            min-width: 330px;
            max-width: 420px;
            backdrop-filter: blur(8px);
        `;

        div.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <div style="font-weight: 700; color: #60a5fa; display: flex; align-items: center; gap: 6px;">
                    <span>[天道] 自动发书助手 v1.6.0</span>
                    <span id="tiandao-status-dot" style="display:inline-block; width:9px; height:9px; border-radius:50%; background:#94a3b8;" title="连接状态"></span>
                </div>
                <div style="display: flex; gap: 4px; align-items: center;">
                    <button id="tiandao-btn-toggle" style="background:#2563eb; color:#fff; border:none; padding:3px 7px; border-radius:5px; cursor:pointer; font-size:11px;">运行中</button>
                    <button id="tiandao-btn-min" style="background:#334155; color:#cbd5e1; border:none; padding:3px 7px; border-radius:5px; cursor:pointer; font-size:11px;" title="收起/展开">-</button>
                </div>
            </div>

            <div id="tiandao-widget-body">
                <div style="display: flex; gap: 4px; margin-bottom: 6px; flex-wrap: wrap;">
                    <button id="tiandao-btn-fillbook" style="background:#7c3aed; color:#fff; border:none; padding:3px 7px; border-radius:5px; cursor:pointer; font-size:11px;" title="一键填入书名与简介">建书填入</button>
                    <button id="tiandao-btn-chainall" style="background:#ea580c; color:#fff; border:none; padding:3px 7px; border-radius:5px; cursor:pointer; font-size:11px; font-weight:700;" title="从当前章节开始全自动逐章录入至最后一章">连发全书</button>
                    <button id="tiandao-btn-manual" style="background:#0f766e; color:#fff; border:none; padding:3px 7px; border-radius:5px; cursor:pointer; font-size:11px;" title="填入当前选中的章节">填入本章</button>
                    <button id="tiandao-btn-autonext" style="background:#059669; color:#fff; border:none; padding:3px 7px; border-radius:5px; cursor:pointer; font-size:11px;" title="切换存草稿后是否自动新建下一章">连发:开</button>
                </div>

                <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 8px; font-size: 11.5px; background: rgba(255,255,255,0.05); padding: 5px 8px; border-radius: 6px;">
                    <span style="color:#94a3b8;">章节跳号:</span>
                    <input id="tiandao-input-chap" type="number" value="${currentChapIndex}" min="1" max="1000" style="width: 50px; background:#0f172a; border:1px solid #475569; color:#fff; border-radius:4px; padding:2px 4px; font-size:11px; text-align:center;">
                    <button id="tiandao-btn-jumpchap" style="background:#3b82f6; color:#fff; border:none; padding:2px 6px; border-radius:4px; cursor:pointer; font-size:10.5px;">设定并载入</button>
                    <button id="tiandao-btn-resetchap" style="background:#b91c1c; color:#fff; border:none; padding:2px 6px; border-radius:4px; cursor:pointer; font-size:10.5px;" title="回到第1章">归零第1章</button>
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
            </div>
        `;
        document.body.appendChild(div);

        // 折叠 / 展开
        document.getElementById('tiandao-btn-min').onclick = () => {
            isCollapsed = !isCollapsed;
            const b = document.getElementById('tiandao-widget-body');
            const mBtn = document.getElementById('tiandao-btn-min');
            if (isCollapsed) {
                b.style.display = 'none';
                mBtn.textContent = '+';
            } else {
                b.style.display = 'block';
                mBtn.textContent = '-';
            }
        };

        // 运行 / 暂停
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

        // 自动连发开关
        document.getElementById('tiandao-btn-autonext').onclick = () => {
            autoNextChapter = !autoNextChapter;
            const btn = document.getElementById('tiandao-btn-autonext');
            if (autoNextChapter) {
                btn.textContent = '连发:开';
                btn.style.background = '#059669';
                updateLog('自动连发模式已开启（存完草稿自动点新建继续下一章）');
            } else {
                btn.textContent = '连发:关';
                btn.style.background = '#64748b';
                updateLog('自动连发已关闭（仅处理当前章节）');
            }
        };

        // 建书自动填入
        document.getElementById('tiandao-btn-fillbook').onclick = () => {
            handleCreateBook();
        };

        // 填入本章
        document.getElementById('tiandao-btn-manual').onclick = () => {
            if (currentChapter) {
                handleUploadChapter(currentChapter, true);
            } else {
                updateLog(`正在拉取第 ${currentChapIndex} 章...`);
                loadChapterByIndex(currentChapIndex, true);
            }
        };

        // 一键连发全书
        document.getElementById('tiandao-btn-chainall').onclick = () => {
            autoNextChapter = true;
            const btn = document.getElementById('tiandao-btn-autonext');
            if (btn) {
                btn.textContent = '连发:开';
                btn.style.background = '#059669';
            }
            updateLog(`启动全书自动连发（从第 ${currentChapIndex} 章开始）...`);
            loadChapterByIndex(currentChapIndex, true);
        };

        // 设定章节序号
        document.getElementById('tiandao-btn-jumpchap').onclick = () => {
            const inputVal = parseInt(document.getElementById('tiandao-input-chap').value, 10);
            if (inputVal > 0) {
                currentChapIndex = inputVal;
                localStorage.setItem('tiandao_current_chap', currentChapIndex);
                updateLog(`章节指针已跳转至第 ${currentChapIndex} 章`);
                loadChapterByIndex(currentChapIndex, false);
            }
        };

        // 归零重置为第1章
        document.getElementById('tiandao-btn-resetchap').onclick = () => {
            currentChapIndex = 1;
            localStorage.setItem('tiandao_current_chap', '1');
            document.getElementById('tiandao-input-chap').value = '1';
            updateLog('已将发书进度归零重置为第 1 章！');
            loadChapterByIndex(1, false);
        };

        // 修改服务端地址
        document.getElementById('tiandao-btn-seturl').onclick = () => {
            const newUrl = prompt("请输入天道服务访问地址（如 https://book.si2api.top 或 http://localhost:8088）：", API_BASE);
            if (newUrl && newUrl.trim()) {
                API_BASE = newUrl.trim().replace(/\/$/, "");
                localStorage.setItem('tiandao_api_base', API_BASE);
                document.getElementById('tiandao-current-url').textContent = API_BASE;
                updateLog(`服务地址已切换为: ${API_BASE}`);
                syncBookMeta();
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
                    timeout: 10000,
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

    // 同步书籍元数据
    async function syncBookMeta() {
        try {
            const books = await httpRequest(`${API_BASE}/api/books`);
            if (Array.isArray(books) && books.length > 0) {
                // 优先选取章节最多的作品
                let bestBook = books[0];
                for (const b of books) {
                    if ((b.chapter_count || 0) > (bestBook.chapter_count || 0)) {
                        bestBook = b;
                    }
                }
                activeBookId = bestBook.id;
                activeBookTitle = bestBook.title;
                totalChaptersCount = bestBook.chapter_count || 101;
                localStorage.setItem('tiandao_active_bid', activeBookId);
                localStorage.setItem('tiandao_active_btitle', activeBookTitle);
                localStorage.setItem('tiandao_total_chaps', totalChaptersCount);

                const dot = document.getElementById('tiandao-status-dot');
                if (dot) dot.style.background = '#10b981';
                updateInfo(`作品: 《${activeBookTitle}》 | 共 ${totalChaptersCount} 章 (当前定位: 第 ${currentChapIndex} 章)`);
                return true;
            }
        } catch(e) {
            const dot = document.getElementById('tiandao-status-dot');
            if (dot) dot.style.background = '#ef4444';
            updateLog(`连接天道服务失败: ${e.message}`);
        }
        return false;
    }

    // 一键在番茄【新建作品】页面自动填入书名与简介
    async function handleCreateBook() {
        updateLog("正在从天道拉取小说档案...");
        try {
            const res = await httpRequest(`${API_BASE}/api/fanqie/book_meta`);
            if (!res || res.status !== 'ok') {
                updateLog("获取小说档案失败，请检查天道连接");
                return;
            }

            let titleInput = document.querySelector('input[placeholder*="书名"]') || 
                             document.querySelector('input[placeholder*="作品名"]') ||
                             document.querySelector('input[placeholder*="作品名称"]') ||
                             document.querySelector('.book-title-input input') ||
                             document.querySelector('.semi-input[placeholder*="书名"]');
            
            let synopsisInput = document.querySelector('textarea[placeholder*="简介"]') || 
                                document.querySelector('textarea[placeholder*="作品简介"]') ||
                                document.querySelector('.synopsis-textarea') ||
                                document.querySelector('.semi-input-textarea[placeholder*="简介"]');

            if (!titleInput && !synopsisInput) {
                let createBookBtn = Array.from(document.querySelectorAll('button, a, span')).find(el => {
                    const txt = (el.textContent || "").trim();
                    return (txt === '新建作品' || txt === '创建作品') && el.offsetParent !== null;
                });
                if (createBookBtn) {
                    updateLog("检测到【新建作品】按钮，自动点击进入...");
                    createBookBtn.click();
                    setTimeout(handleCreateBook, 2000);
                    return;
                }
                updateLog("提示: 请先在番茄页面点击【新建作品】打开建书表单");
                return;
            }

            if (titleInput) {
                titleInput.focus();
                titleInput.value = res.title;
                titleInput.dispatchEvent(new Event('input', { bubbles: true }));
                titleInput.dispatchEvent(new Event('change', { bubbles: true }));
                titleInput.dispatchEvent(new Event('blur', { bubbles: true }));
            }

            if (synopsisInput) {
                synopsisInput.focus();
                synopsisInput.value = res.synopsis || res.theme_prompt || "";
                synopsisInput.dispatchEvent(new Event('input', { bubbles: true }));
                synopsisInput.dispatchEvent(new Event('change', { bubbles: true }));
                synopsisInput.dispatchEvent(new Event('blur', { bubbles: true }));
            }

            updateLog(`书名《${res.title}》与简介已全部自动填入！`);
            updateInfo(`推荐分类: <b style="color:#f59e0b;">${res.genre}</b> | 标签: ${res.fanqie_tags ? res.fanqie_tags.join("、") : ""}`);
        } catch (e) {
            updateLog(`建书自动填入异常: ${e.message}`);
        }
    }

    // 根据索引加载章节内容（具备对假同步穿透机制）
    async function loadChapterByIndex(chapIndex, autoExecute = false) {
        if (!activeBookId) await syncBookMeta();
        updateLog(`正在从天道提取第 ${chapIndex} 章数据...`);
        try {
            const url = `${API_BASE}/api/chapter?book_id=${encodeURIComponent(activeBookId)}&id=${chapIndex}`;
            const chapData = await httpRequest(url);
            if (chapData && chapData.content) {
                let rawTitle = (chapData.title || `第${chapIndex}章`).replace(/#/g, '').trim();
                if (!rawTitle.startsWith('第') && !rawTitle.includes('章')) {
                    rawTitle = `第${chapIndex}章 ${rawTitle}`;
                }
                currentChapter = {
                    book_id: activeBookId,
                    book_title: activeBookTitle,
                    chapter_id: chapIndex,
                    chapter_title: rawTitle,
                    content: cleanForFanqie(rawTitle, chapData.content),
                    word_count: chapData.content.length,
                    total_chapters: totalChaptersCount
                };
                currentChapIndex = chapIndex;
                localStorage.setItem('tiandao_current_chap', chapIndex);
                const inputEl = document.getElementById('tiandao-input-chap');
                if (inputEl) inputEl.value = chapIndex;

                updateInfo(`准备录入: 第 ${chapIndex} / ${totalChaptersCount} 章《${rawTitle}》(${currentChapter.word_count} 字)`);
                updateLog(`第 ${chapIndex} 章拉取成功，随时可填入`);

                if (autoExecute) {
                    await handleUploadChapter(currentChapter);
                }
                return currentChapter;
            } else {
                updateLog(`提取第 ${chapIndex} 章失败: 未找到该章节内容`);
            }
        } catch(e) {
            updateLog(`提取第 ${chapIndex} 章出错: ${e.message}`);
        }
        return null;
    }

    // 核心轮询：检查待上传章节或新建作品上下文
    async function checkPendingChapter() {
        if (!isRunning || isUploading) return;

        // 检测是否在新建作品页面
        const isCreatePage = document.querySelector('input[placeholder*="书名"]') || 
                             document.querySelector('textarea[placeholder*="简介"]') ||
                             window.location.href.includes("create") ||
                             window.location.href.includes("new-book");
        if (isCreatePage) {
            const dot = document.getElementById('tiandao-status-dot');
            if (dot) dot.style.background = '#10b981';
            updateInfo("检测到【新建作品】页面：点击右上角<b>【建书填入】</b>一键填入书名与简介");
            return;
        }

        // 尝试向服务端获取待推章节
        try {
            const res = await httpRequest(`${API_BASE}/api/fanqie/pending_chapter`);
            if (res && res.status === 'ok') {
                const dot = document.getElementById('tiandao-status-dot');
                if (dot) dot.style.background = '#10b981';
                
                if (res.has_pending && res.chapter) {
                    currentChapter = res.chapter;
                    currentChapIndex = parseInt(res.chapter.chapter_id, 10) || currentChapIndex;
                    localStorage.setItem('tiandao_current_chap', currentChapIndex);
                    const inp = document.getElementById('tiandao-input-chap');
                    if (inp) inp.value = currentChapIndex;
                    updateInfo(`待发章节: 第 ${res.chapter.chapter_id} 章 (${res.chapter.word_count} 字)`);
                    await handleUploadChapter(res.chapter);
                    return;
                }
            }
        } catch(e) {}

        // 如果服务端显示 false（如被历史误标为已同步），则自主按本地指针激活第 currentChapIndex 章！
        if (!activeBookId) await syncBookMeta();
        if (currentChapIndex <= totalChaptersCount) {
            updateInfo(`服务端状态已过滤，当前排队待录入: 第 ${currentChapIndex} / ${totalChaptersCount} 章`);
        } else {
            updateInfo(`全书全部 ${totalChaptersCount} 章已全部录入完毕！`);
        }
    }

    // 自动在番茄页面寻找元素并填入草稿
    async function handleUploadChapter(chapter, forceManual = false) {
        if (!forceManual && isUploading) return;
        isUploading = true;
        dismissPopups();
        updateLog(`正在填充第 ${chapter.chapter_id} 章《${chapter.chapter_title}》...`);
        updateInfo(`<span style="color:#f59e0b;">正在录入第 ${chapter.chapter_id} 章 (${chapter.word_count} 字)...</span>`);

        try {
            // 1. 查找标题输入框
            let titleInput = document.querySelector('input[placeholder*="标题"]') || 
                             document.querySelector('input[placeholder*="章节名"]') ||
                             document.querySelector('input[placeholder*="输入章节名"]') ||
                             document.querySelector('.chapter-title-input input') ||
                             document.querySelector('.semi-input[placeholder*="标题"]') ||
                             document.querySelector('input.publish-header-input') ||
                             document.querySelector('input[type="text"]');
            
            // 2. 查找正文输入框 (ProseMirror 或 contenteditable 或 textarea)
            let bodyEditor = document.querySelector('.ProseMirror') || 
                             document.querySelector('div[contenteditable="true"]') ||
                             document.querySelector('.public-DraftEditor-content') ||
                             document.querySelector('textarea[placeholder*="正文"]') ||
                             document.querySelector('textarea[placeholder*="输入正文"]') ||
                             document.querySelector('textarea.semi-input-textarea');

            if (!titleInput || !bodyEditor) {
                let newBtn = Array.from(document.querySelectorAll('button, a, span, div')).find(el => {
                    const txt = (el.textContent || "").trim();
                    return (txt === '新建章节' || txt === '写新章' || txt === '发布章节' || txt === '创建章节' || txt === '写新章节' || txt === '+ 新建章节' || txt === '+ 新建') && el.offsetParent !== null;
                });
                if (newBtn) {
                    updateLog('检测到新建章节按钮，自动点击进入...');
                    newBtn.click();
                    setTimeout(() => {
                        isUploading = false;
                        handleUploadChapter(chapter, true);
                    }, 2500);
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
                if (bodyEditor.classList.contains('ProseMirror')) {
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

            await new Promise(r => setTimeout(r, 1200));
            dismissPopups();

            // 寻找保存草稿按钮
            let saveBtn = Array.from(document.querySelectorAll('button')).find(el => {
                const txt = (el.textContent || "").trim();
                return (txt.includes('存草稿') || txt.includes('保存草稿') || txt === '保存' || txt === '暂存' || txt === '存为草稿') && el.offsetParent !== null;
            });

            if (saveBtn && !saveBtn.disabled) {
                saveBtn.click();
                updateLog(`第 ${chapter.chapter_id} 章已自动点击存草稿！`);
                setTimeout(dismissPopups, 1000);
            } else {
                updateLog(`第 ${chapter.chapter_id} 章已填入标题和正文，请手动点击保存`);
            }

            // 上报已录入（即使服务端未更新也静默通过）
            try {
                await httpRequest(`${API_BASE}/api/fanqie/confirm_uploaded`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        book_id: chapter.book_id,
                        chapter_id: chapter.chapter_id,
                        mode: 'tampermonkey_draft'
                    })
                });
            } catch(e) {}

            updateInfo(`第 ${chapter.chapter_id} 章《${chapter.chapter_title}》已成功存入草稿箱！`);

            // 自动推进到下一章
            currentChapIndex = parseInt(chapter.chapter_id, 10) + 1;
            localStorage.setItem('tiandao_current_chap', currentChapIndex);
            const inp = document.getElementById('tiandao-input-chap');
            if (inp) inp.value = currentChapIndex;

            // 如果开启了自动连发模式，自动点击新建章节继续录入下一章
            if (autoNextChapter && currentChapIndex <= totalChaptersCount) {
                updateLog(`第 ${chapter.chapter_id} 章存稿完毕，3 秒后自动创建第 ${currentChapIndex} 章...`);
                await new Promise(r => setTimeout(r, 3000));

                let nextChapterBtn = Array.from(document.querySelectorAll('button, a, span, div')).find(el => {
                    const txt = (el.textContent || "").trim();
                    return (txt === '新建章节' || txt === '写新章' || txt === '创建章节' || txt === '写新章节' || txt === '+ 新建章节' || txt === '+ 新建') && el.offsetParent !== null;
                });

                if (nextChapterBtn) {
                    updateLog(`自动点击【新建章节】准备第 ${currentChapIndex} 章...`);
                    nextChapterBtn.click();
                    setTimeout(() => {
                        isUploading = false;
                        loadChapterByIndex(currentChapIndex, true);
                    }, 2500);
                    return;
                } else {
                    updateLog("连发提示: 等待新建章节按钮出现...");
                    setTimeout(() => {
                        isUploading = false;
                        loadChapterByIndex(currentChapIndex, true);
                    }, 3000);
                    return;
                }
            } else if (currentChapIndex > totalChaptersCount) {
                updateLog("全书所有章节均已录入完毕，已自动停止连发！");
            }
        } catch (e) {
            updateLog(`同步发生异常: ${e.message}`);
        } finally {
            isUploading = false;
        }
    }

    // 初始化运行
    function init() {
        createWidget();
        syncBookMeta().then(() => {
            checkPendingChapter();
        });
        if (!pollTimer) {
            pollTimer = setInterval(() => checkPendingChapter(), 10000);
        }
    }

    if (document.readyState === 'loading') {
        window.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
