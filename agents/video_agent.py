import os
import json
import time
import threading
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List

class VideoAgent:
    """
    竖屏短剧 AI 视频生成智能代理 (VideoAgent)
    支持：
    1. 智谱 CogVideoX 官方 (open.bigmodel.cn/api/paas/v4)
    2. 可灵 AI 官方 (api.klingai.com/v1)
    3. Si2API / One-API / New-API / Trae 等聚合中转网关 (/v1/videos/generations, /v1/tasks, etc.)
    4. 模拟免Key极速体验 (Mock Video)
    """

    def __init__(self, api_key: str = "", base_url: str = "", model_name: str = ""):
        # 1. API Key 优先级解析：
        #    显式传入 > 专用 VIDEO_API_KEY > 继承 DRAMA_API_KEY > 回退 OPENAI_API_KEY
        self.api_key = api_key or os.getenv("VIDEO_API_KEY", "")
        inherited_from_drama = False
        if not self.api_key:
            if os.getenv("DRAMA_API_KEY"):
                self.api_key = os.getenv("DRAMA_API_KEY", "")
                inherited_from_drama = True
            else:
                self.api_key = os.getenv("OPENAI_API_KEY", "")

        # 2. Base URL 优先级解析：
        #    显式传入 > 专用 VIDEO_BASE_URL > 若继承自 DRAMA_API_KEY 配对 DRAMA_BASE_URL > 默认智谱官方
        explicit_base = base_url or os.getenv("VIDEO_BASE_URL", "")
        if explicit_base:
            self.base_url = explicit_base.rstrip("/")
        elif inherited_from_drama and os.getenv("DRAMA_BASE_URL"):
            self.base_url = os.getenv("DRAMA_BASE_URL", "").rstrip("/")
        elif os.getenv("OPENAI_BASE_URL") and not inherited_from_drama and self.api_key == os.getenv("OPENAI_API_KEY"):
            self.base_url = os.getenv("OPENAI_BASE_URL", "").rstrip("/")
        else:
            self.base_url = "https://open.bigmodel.cn/api/paas/v4"

        # 3. Model 智能适配
        self.model = model_name or os.getenv("VIDEO_MODEL", "")
        if not self.model:
            if "kling" in self.base_url or "kling" in self.model.lower():
                self.model = "kling-v1"
            else:
                self.model = "cogvideox-flash"

    def test_connection(self) -> Dict[str, Any]:
        """安全探测视频网关连通性（只探测模型鉴权接口，绝对不消耗用户的昂贵生视频 Token）"""
        if not self.api_key or self.api_key == "your_api_key_here":
            return {"status": "error", "error": "未配置有效的 API Key"}

        # 探测 GET /models
        test_urls = [
            f"{self.base_url}/models",
            f"{self.base_url}/v1/models" if not self.base_url.endswith("/v1") else f"{self.base_url}/models"
        ]
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "Tiandao-VideoAgent/2.0"
        }
        for u in test_urls:
            try:
                req = urllib.request.Request(u, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=12) as resp:
                    if resp.status in (200, 201):
                        return {
                            "status": "ok",
                            "message": f"视频通道鉴权成功，网关通信正常 (HTTP {resp.status})",
                            "model": self.model
                        }
            except urllib.error.HTTPError as he:
                if he.code in (401, 403):
                    return {"status": "error", "error": f"API Key 鉴权失败 (HTTP {he.code}): 请检查 Key 是否正确或已欠费"}
                elif he.code in (404, 405):
                    continue
                else:
                    return {"status": "error", "error": f"网关返回状态码 {he.code}"}
            except Exception:
                continue

        # 若 /models 不支持，使用 HEAD 探测根地址/generations 鉴权
        try:
            req = urllib.request.Request(f"{self.base_url}/videos/generations", headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {"status": "ok", "message": "视频接口连通正常", "model": self.model}
        except urllib.error.HTTPError as he:
            if he.code in (401, 403):
                return {"status": "error", "error": f"鉴权拒绝 (HTTP {he.code}): 请检查 API Key"}
            # 405 Method Not Allowed 或 400 Bad Request 说明网络已通且鉴权通过，只是缺少 POST body
            if he.code in (405, 400):
                return {"status": "ok", "message": "视频通道网络与鉴权正常", "model": self.model}
            return {"status": "error", "error": f"网关连通异常: HTTP {he.code}"}
        except Exception as e:
            return {"status": "error", "error": f"网络连接超时或无法解析地址: {str(e)}"}

    def submit_video_task(self, prompt: str, aspect_ratio: str = "9:16", duration: int = 5, force_mock: bool = False) -> Dict[str, Any]:
        """提交文生视频推演任务"""
        if force_mock or not self.api_key or self.api_key == "your_api_key_here":
            return self._mock_submit(prompt, duration)

        # 1. 智谱 CogVideoX 适配
        if "bigmodel.cn" in self.base_url or "cogvideo" in self.model.lower():
            return self._submit_cogvideo(prompt, duration)

        # 2. 可灵 Kling AI 官方适配
        if "klingai" in self.base_url or "kling" in self.model.lower():
            return self._submit_kling(prompt, duration)

        # 3. 通用网关适配 (Si2API / One-API / New-API / Trae 等)
        return self._submit_generic_gateway(prompt, duration)

    def query_video_status(self, task_id: str, force_mock: bool = False) -> Dict[str, Any]:
        """轮询查询视频任务完成状态并获取真实 MP4 URL"""
        if force_mock or task_id.startswith("mock_"):
            return {
                "status": "completed",
                "video_url": "https://assets.mixkit.co/videos/preview/mixkit-vertical-view-of-a-neon-city-in-the-rain-42099-large.mp4",
                "cover_url": "",
                "message": "模拟视频构建完成"
            }

        if "bigmodel.cn" in self.base_url:
            return self._query_cogvideo(task_id)

        if "klingai" in self.base_url:
            return self._query_kling(task_id)

        return self._query_generic_gateway(task_id)

    # ================= 智谱 CogVideoX 官方实现 =================
    def _submit_cogvideo(self, prompt: str, duration: int = 5) -> Dict[str, Any]:
        url = f"{self.base_url}/videos/generations"
        payload = {
            "model": self.model if "cogvideo" in self.model.lower() else "cogvideox-flash",
            "prompt": prompt,
            "quality": "quality",
            "size": "720x1280",  # 9:16 竖屏短剧
            "duration": min(max(duration, 5), 10),
            "fps": 30
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=35) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                task_id = data.get("id") or data.get("task_id")
                if task_id:
                    return {
                        "status": "processing",
                        "task_id": task_id,
                        "provider": "cogvideo",
                        "message": "智谱 CogVideoX 渲染任务已创建，排队渲染中..."
                    }
                v_url = self._extract_video_url(data)
                if v_url:
                    return {"status": "completed", "video_url": v_url, "provider": "cogvideo", "message": "视频已生成"}
                return {"status": "failed", "error": f"未能解析智谱返回的任务ID: {data}"}
        except urllib.error.HTTPError as he:
            body = ""
            try: body = he.read().decode("utf-8")
            except Exception: pass
            return {"status": "failed", "error": f"智谱 CogVideoX 提交失败 (HTTP {he.code}): {body or he.reason}"}
        except Exception as e:
            return {"status": "failed", "error": f"智谱 CogVideoX 提交异常: {str(e)}"}

    def _query_cogvideo(self, task_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/async-result/{task_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                state = str(data.get("task_status", "")).upper()
                if state == "SUCCESS":
                    results = data.get("video_result", [])
                    v_url = results[0].get("url") if results else self._extract_video_url(data)
                    c_url = results[0].get("cover_image_url") if results else ""
                    return {
                        "status": "completed",
                        "video_url": v_url,
                        "cover_url": c_url,
                        "message": "视频渲染完成"
                    }
                elif state in ("FAIL", "FAILED"):
                    return {
                        "status": "failed",
                        "error": data.get("error_msg") or data.get("error", "智谱视频渲染失败")
                    }
                else:
                    return {
                        "status": "processing",
                        "task_id": task_id,
                        "message": "视频正在渲染合成中，请稍候..."
                    }
        except Exception as e:
            return {"status": "processing", "task_id": task_id, "message": f"轮询视频状态中 ({str(e)})"}

    # ================= 可灵 Kling AI 官方实现 =================
    def _submit_kling(self, prompt: str, duration: int = 5) -> Dict[str, Any]:
        url = f"{self.base_url}/videos/text2video"
        payload = {
            "model_name": self.model if "kling" in self.model.lower() else "kling-v1",
            "prompt": prompt,
            "aspect_ratio": "9:16",
            "duration": str(duration)
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=35) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                task_id = data.get("data", {}).get("task_id") or data.get("task_id")
                if task_id:
                    return {
                        "status": "processing",
                        "task_id": task_id,
                        "provider": "kling",
                        "message": "可灵 AI 视频任务已提交，进入排队管道..."
                    }
                v_url = self._extract_video_url(data)
                if v_url:
                    return {"status": "completed", "video_url": v_url, "provider": "kling", "message": "视频已生成"}
                return {"status": "failed", "error": f"可灵未能解析任务ID: {data}"}
        except urllib.error.HTTPError as he:
            body = ""
            try: body = he.read().decode("utf-8")
            except Exception: pass
            return {"status": "failed", "error": f"可灵 AI 提交失败 (HTTP {he.code}): {body or he.reason}"}
        except Exception as e:
            return {"status": "failed", "error": f"可灵 AI 提交失败: {str(e)}"}

    def _query_kling(self, task_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/videos/text2video/{task_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                state = str(data.get("data", {}).get("task_status", "")).lower()
                if state in ("succeed", "success"):
                    v_url = self._extract_video_url(data)
                    return {"status": "completed", "video_url": v_url, "message": "视频渲染完成"}
                elif state in ("failed", "fail"):
                    return {"status": "failed", "error": "可灵视频生成失败"}
                else:
                    return {"status": "processing", "task_id": task_id, "message": "可灵视频渲染中..."}
        except Exception as e:
            return {"status": "processing", "task_id": task_id, "message": f"轮询可灵状态中 ({str(e)})"}

    # ================= 通用网关实现 (Si2API / One-API / New-API) =================
    def _submit_generic_gateway(self, prompt: str, duration: int = 5) -> Dict[str, Any]:
        endpoints = [
            f"{self.base_url}/videos/generations",
            f"{self.base_url}/video/generations",
            f"{self.base_url}/v1/videos/generations" if not self.base_url.endswith("/v1") else f"{self.base_url}/videos/generations"
        ]
        # 去重
        seen = set()
        unique_endpoints = []
        for ep in endpoints:
            if ep not in seen:
                seen.add(ep)
                unique_endpoints.append(ep)

        payload = {
            "model": self.model,
            "prompt": prompt,
            "size": "720x1280",
            "duration": duration,
            "fps": 30,
            "aspect_ratio": "9:16"
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        last_err = ""
        for ep in unique_endpoints:
            try:
                req = urllib.request.Request(ep, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=40) as resp:
                    resp_text = resp.read().decode("utf-8")
                    data = json.loads(resp_text)

                    # 1. 直接返回 MP4 URL
                    v_url = self._extract_video_url(data)
                    if v_url:
                        return {"status": "completed", "video_url": v_url, "provider": "generic", "message": "视频已成功生成并获取！"}

                    # 2. 提取异步 Task ID
                    task_id = (
                        data.get("id") or
                        data.get("task_id") or
                        data.get("data", {}).get("task_id") or
                        (data.get("data", [{}])[0].get("id") if isinstance(data.get("data"), list) and data.get("data") else None)
                    )
                    if task_id:
                        return {
                            "status": "processing",
                            "task_id": str(task_id),
                            "provider": "generic",
                            "message": f"AI 视频渲染任务已提交网关 (任务ID: {task_id})，进入排队渲染中..."
                        }
            except urllib.error.HTTPError as he:
                body = ""
                try: body = he.read().decode("utf-8")
                except Exception: pass
                last_err = f"网关返回 HTTP {he.code}: {body or he.reason}"
                # 如果是 404 说明路径不对，尝试下一个候选路径
                if he.code == 404:
                    continue
                # 如果是 401/403/400 则直接报错，告知用户真实问题
                return {"status": "failed", "error": f"视频提交失败: {last_err}"}
            except Exception as e:
                last_err = str(e)
                continue

        # 如果所有候选端点均失败，如实返回错误，绝不静默使用模拟数据糊弄用户
        return {"status": "failed", "error": f"所有视频网关端点连接失败: {last_err} (请在后台检查 VIDEO_BASE_URL 或网关是否支持 /videos/generations)"}

    def _query_generic_gateway(self, task_id: str) -> Dict[str, Any]:
        """多候选端点智能探查通用网关的视频任务状态"""
        candidate_urls = [
            f"{self.base_url}/videos/generations/{task_id}",
            f"{self.base_url}/v1/videos/generations/{task_id}",
            f"{self.base_url}/tasks/{task_id}",
            f"{self.base_url}/v1/tasks/{task_id}",
            f"{self.base_url}/task/{task_id}",
            f"{self.base_url}/query/video_generation?task_id={task_id}",
            f"{self.base_url}/v1/query/video_generation?task_id={task_id}",
            f"{self.base_url}/async-result/{task_id}",
            f"{self.base_url}/videos/text2video/{task_id}",
            f"{self.base_url}/videos/{task_id}",
            f"{self.base_url}/v1/videos/{task_id}"
        ]
        headers = {"Authorization": f"Bearer {self.api_key}"}

        for url in candidate_urls:
            try:
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=20) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))

                        # 1. 尝试直接抽取视频 URL
                        v_url = self._extract_video_url(data)
                        if v_url:
                            return {
                                "status": "completed",
                                "video_url": v_url,
                                "message": "视频渲染完成，已成功获取视频流"
                            }

                        # 2. 检查各种通用状态字段
                        status_str = str(
                            data.get("status") or
                            data.get("task_status") or
                            data.get("state") or
                            data.get("data", {}).get("task_status") or
                            ""
                        ).upper()

                        if status_str in ("SUCCESS", "SUCCEED", "SUCCEEDED", "COMPLETED", "DONE", "FINISHED"):
                            v_url = self._extract_video_url(data)
                            if v_url:
                                return {"status": "completed", "video_url": v_url, "message": "视频渲染完成"}

                        if status_str in ("FAIL", "FAILED", "ERROR"):
                            err_msg = data.get("error_msg") or data.get("error") or data.get("message") or "网关返回生成失败"
                            return {"status": "failed", "error": str(err_msg)}

                        if status_str in ("PROCESSING", "PENDING", "RUNNING", "QUEUED", "SUBMITTED", "WAITING"):
                            return {
                                "status": "processing",
                                "task_id": task_id,
                                "message": "AI 视频引擎正在渲染合成中，请稍候..."
                            }
            except urllib.error.HTTPError as he:
                if he.code == 404:
                    continue  # 当前端点不是该网关的查询端点，继续试下一个
                pass
            except Exception:
                pass

        # 若暂时未能探查到结果，保持 processing 状态让后台继续守护轮询
        return {
            "status": "processing",
            "task_id": task_id,
            "message": "AI 视频排队渲染中，后台守护进程持续接收中..."
        }

    # ================= 递归多层级 MP4 URL 提取器 =================
    @staticmethod
    def _extract_video_url(data: Any) -> Optional[str]:
        """从任意嵌套的 JSON 数据结构中递归提取真实可播放的 MP4 视频链接"""
        if not data:
            return None
        if isinstance(data, str):
            s = data.strip()
            if (s.startswith("http://") or s.startswith("https://")) and any(ext in s.lower() for ext in (".mp4", ".mov", ".webm", "/video", "cdn", "oss", "s3")):
                return s
            return None
        if isinstance(data, dict):
            # 高频字段优先判断
            for k in ("video_url", "url", "download_url", "file_url", "play_url", "output_url", "video"):
                val = data.get(k)
                if isinstance(val, str) and (val.startswith("http://") or val.startswith("https://")):
                    if any(ext in val.lower() for ext in (".mp4", ".mov", ".webm", "/video", "cdn", "oss", "s3", "generations")):
                        return val
            # 智谱 video_result
            if "video_result" in data and isinstance(data["video_result"], list) and data["video_result"]:
                u = VideoAgent._extract_video_url(data["video_result"][0])
                if u: return u
            # 可灵 task_result.videos
            if "task_result" in data and isinstance(data["task_result"], dict):
                vids = data["task_result"].get("videos", [])
                if isinstance(vids, list) and vids:
                    u = VideoAgent._extract_video_url(vids[0])
                    if u: return u
            # OpenAI / One-API data 数组
            if "data" in data:
                u = VideoAgent._extract_video_url(data["data"])
                if u: return u
            # output 字段
            if "output" in data:
                u = VideoAgent._extract_video_url(data["output"])
                if u: return u
            # 递归遍历字典所有 value
            for v in data.values():
                if isinstance(v, (dict, list)):
                    u = VideoAgent._extract_video_url(v)
                    if u: return u
        elif isinstance(data, list):
            for item in data:
                u = VideoAgent._extract_video_url(item)
                if u: return u
        return None

    # ================= 模拟免Key极速体验 =================
    def _mock_submit(self, prompt: str, duration: int = 5) -> Dict[str, Any]:
        sample_videos = [
            "https://assets.mixkit.co/videos/preview/mixkit-vertical-view-of-a-neon-city-in-the-rain-42099-large.mp4",
            "https://assets.mixkit.co/videos/preview/mixkit-tree-branches-in-the-breeze-1188-large.mp4",
            "https://assets.mixkit.co/videos/preview/mixkit-going-down-a-curved-highway-down-a-mountain-41576-large.mp4",
            "https://assets.mixkit.co/videos/preview/mixkit-man-holding-a-smartphone-at-night-42100-large.mp4"
        ]
        import hashlib
        idx = int(hashlib.md5(prompt.encode("utf-8")).hexdigest(), 16) % len(sample_videos)
        v_url = sample_videos[idx]
        return {
            "status": "completed",
            "task_id": f"mock_{int(time.time()*1000)}",
            "video_url": v_url,
            "provider": "mock",
            "message": "免Key体验模式：已极速构建高能短剧样片（可在控制台管理端绑定 CogVideoX/可灵 Key 切换为实拍AI渲染）"
        }


class VideoTaskManager:
    """
    【短剧视频后台异步轮询守护管理器 (VideoTaskManager)】
    彻底解决“生成后的视频没有返回回来、白白浪费 Token”的问题：
    1. 任务登记：只要发起生成且进入 processing，无论前端是否关闭，后台自动注册轮询守护。
    2. 定时轮询：后台守护线程每 4 秒轮询一次第三方 AI 网关。
    3. 自动落盘：一旦视频渲染完成获取到真实 MP4 地址，立即自动存盘写入目标作品短剧数据中！
    4. 自动续拉：服务器重启或页面刷新时，自动扫描所有 processing 镜号继续接管轮询。
    """
    _instance = None

    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
        self.worker_thread = None
        self.running = False
        self.book_mgr = None
        self.sim_mgr = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = VideoTaskManager()
        return cls._instance

    def initialize(self, book_mgr, sim_mgr):
        self.book_mgr = book_mgr
        self.sim_mgr = sim_mgr
        self.start()

    def start(self):
        with self.lock:
            if not self.running:
                self.running = True
                self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="VideoTaskPoller")
                self.worker_thread.start()

    def register_task(self, book_id: str, episode_num: int, shot_num: int, task_id: str, agent: VideoAgent):
        """登记一个处理中的视频任务"""
        if not task_id or task_id.startswith("mock_"):
            return
        with self.lock:
            self.tasks[task_id] = {
                "book_id": book_id,
                "episode_num": episode_num,
                "shot_num": shot_num,
                "task_id": task_id,
                "agent": agent,
                "registered_at": time.time(),
                "attempts": 0,
                "last_poll_at": 0
            }
        print(f" [视频后台守护] 已登记轮询任务 #{shot_num} (TaskID: {task_id})，后台自动守护直至视频完成落盘...")

    def scan_and_register_pending_shots(self):
        """扫描所有书籍中未完成的视频任务，恢复轮询"""
        if not self.book_mgr:
            return
        try:
            count = 0
            for b in self.book_mgr.books.values():
                for d in getattr(b, "dramas", []):
                    ep = d.get("episode_num", 1)
                    for s in d.get("shots", []):
                        if s.get("video_status") == "processing" and s.get("video_task_id"):
                            tid = s.get("video_task_id")
                            if tid and not tid.startswith("mock_"):
                                self.register_task(b.id, ep, s.get("shot_num"), tid, VideoAgent())
                                count += 1
            if count > 0:
                print(f" [视频后台守护] 已自动恢复接管 {count} 个未完成的排队渲染视频任务！")
        except Exception as e:
            print(f"[视频后台守护扫描告警] {e}")

    def _worker_loop(self):
        while self.running:
            time.sleep(3.5)
            with self.lock:
                task_items = list(self.tasks.values())

            now = time.time()
            for t in task_items:
                tid = t["task_id"]
                # 间隔 3 秒轮询一次防频控
                if now - t.get("last_poll_at", 0) < 3.0:
                    continue

                t["attempts"] += 1
                t["last_poll_at"] = now
                agent = t["agent"]

                try:
                    res = agent.query_video_status(tid)
                    st = res.get("status")

                    if st == "completed":
                        v_url = res.get("video_url", "")
                        self._update_shot(t["book_id"], t["episode_num"], t["shot_num"], "completed", video_url=v_url)
                        print(f" [视频守护完成] 任务 {tid} 成功生成 MP4 视频！已持久化写入第 {t['episode_num']} 集镜号 #{t['shot_num']}")
                        with self.lock:
                            self.tasks.pop(tid, None)
                    elif st == "failed":
                        err = res.get("error", "视频生成失败")
                        self._update_shot(t["book_id"], t["episode_num"], t["shot_num"], "failed", error=err)
                        print(f" [视频守护告警] 任务 {tid} 渲染失败: {err}")
                        with self.lock:
                            self.tasks.pop(tid, None)
                    elif t["attempts"] >= 180:  # 超过 10 分钟
                        self._update_shot(t["book_id"], t["episode_num"], t["shot_num"], "failed", error="视频渲染超时(>10分钟)")
                        with self.lock:
                            self.tasks.pop(tid, None)
                except Exception as e:
                    if t["attempts"] >= 180:
                        with self.lock:
                            self.tasks.pop(tid, None)

    def _update_shot(self, book_id, ep_num, shot_num, status, video_url="", error=""):
        try:
            target_book = self.book_mgr.books.get(book_id) if self.book_mgr else None
            if not target_book and self.sim_mgr:
                target_book = self.sim_mgr.active_book
            if not target_book:
                return

            dramas = getattr(target_book, "dramas", [])
            for d in dramas:
                if d.get("episode_num") == ep_num:
                    for s in d.get("shots", []):
                        if s.get("shot_num") == shot_num:
                            s["video_status"] = status
                            if video_url:
                                s["video_url"] = video_url
                                s.pop("video_error", None)
                            if error:
                                s["video_error"] = error
                            target_book.save()
                            return
        except Exception as e:
            print(f"[视频状态更新异常] {e}")
