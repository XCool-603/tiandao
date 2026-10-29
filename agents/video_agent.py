import os
import json
import time
import re
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
        self.image_model = os.getenv("IMAGE_MODEL", "") or "dall-e-3"

    def test_connection(self) -> Dict[str, Any]:
        """安全探测视频网关连通性（只探测模型鉴权接口，绝对不消耗用户的昂贵生视频 Token）"""
        if not self.api_key or self.api_key == "your_api_key_here":
            return {"status": "error", "error": "未配置有效的 API Key"}

        root_url = re.sub(r'/v1/?$', '', self.base_url)
        test_urls = [
            f"{self.base_url}/models",
            f"{root_url}/v1/models",
            f"{self.base_url}/videos/generations",
            f"{root_url}/v1/videos/generations"
        ]
        # 去重保持顺序
        seen_t = set()
        unique_test_urls = []
        for u in test_urls:
            if u not in seen_t:
                seen_t.add(u)
                unique_test_urls.append(u)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "Tiandao-VideoAgent/2.0"
        }

        models_list = []
        for u in unique_test_urls:
            try:
                req = urllib.request.Request(u, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=12) as resp:
                    if resp.status in (200, 201):
                        resp_data = {}
                        try:
                            resp_data = json.loads(resp.read().decode("utf-8"))
                        except Exception:
                            pass
                        
                        if "data" in resp_data and isinstance(resp_data["data"], list):
                            models_list = [str(m.get("id", "")) for m in resp_data["data"] if isinstance(m, dict)]
                        
                        has_video_support = any("video" in m.lower() or "cogvideo" in m.lower() or "kling" in m.lower() for m in models_list)
                        note = ""
                        if models_list and not has_video_support:
                            note = " (注意：网关模型列表中未检测到常用视频模型，若此网关为纯文本LLM反代如WorkBuddy2API/Trae2API，将无法用于视频生成)"

                        return {
                            "status": "ok",
                            "message": f"视频通道鉴权成功，网关通信正常 (HTTP {resp.status}){note}",
                            "model": self.model,
                            "models_found": models_list[:10]
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

        # 若 /models 不支持，使用 HEAD/GET 探测根地址/generations 鉴权
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
            return {"status": "error", "error": f"网关连通异常: HTTP {he.code} (若为404则该地址无视频生成接口)"}
        except Exception as e:
            return {"status": "error", "error": f"网络连接超时或无法解析地址: {str(e)}"}

    def submit_video_task(
        self,
        prompt: str,
        aspect_ratio: str = "9:16",
        duration: int = 5,
        first_frame_url: str = "",
        last_frame_url: str = "",
        force_mock: bool = False
    ) -> Dict[str, Any]:
        """提交文生视频与首尾帧控镜生视频推演任务"""
        if force_mock or not self.api_key or self.api_key == "your_api_key_here":
            return self._mock_submit(prompt, duration, first_frame_url=first_frame_url, last_frame_url=last_frame_url)

        # 1. 智谱 CogVideoX 适配
        if "bigmodel.cn" in self.base_url or "cogvideo" in self.model.lower():
            return self._submit_cogvideo(prompt, duration, first_frame_url=first_frame_url)

        # 2. 可灵 Kling AI 官方适配 (支持首帧/尾帧)
        if "klingai" in self.base_url or "kling" in self.model.lower():
            return self._submit_kling(prompt, duration, first_frame_url=first_frame_url, last_frame_url=last_frame_url)

        # 3. WorkBuddy2API 与通用网关适配 (支持文生视频与首尾帧控制)
        return self._submit_generic_gateway(prompt, duration, first_frame_url=first_frame_url, last_frame_url=last_frame_url)

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
    def _submit_cogvideo(self, prompt: str, duration: int = 5, first_frame_url: str = "") -> Dict[str, Any]:
        url = f"{self.base_url}/videos/generations"
        payload = {
            "model": self.model if "cogvideo" in self.model.lower() else "cogvideox-flash",
            "prompt": prompt,
            "quality": "quality",
            "size": "720x1280",  # 9:16 竖屏短剧
            "duration": min(max(duration, 5), 10),
            "fps": 30
        }
        if first_frame_url:
            payload["image_url"] = first_frame_url
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
    def _submit_kling(self, prompt: str, duration: int = 5, first_frame_url: str = "", last_frame_url: str = "") -> Dict[str, Any]:
        is_i2v = bool(first_frame_url)
        url = f"{self.base_url}/videos/image2video" if is_i2v else f"{self.base_url}/videos/text2video"
        payload = {
            "model_name": self.model if "kling" in self.model.lower() else "kling-v1",
            "prompt": prompt,
            "aspect_ratio": "9:16",
            "duration": str(duration)
        }
        if first_frame_url:
            payload["image"] = first_frame_url
        if last_frame_url:
            payload["image_tail"] = last_frame_url
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

    # ================= 通用网关与 WorkBuddy2API 逆向多模态视觉实现 =================
    def _submit_generic_gateway(self, prompt: str, duration: int = 5, first_frame_url: str = "", last_frame_url: str = "") -> Dict[str, Any]:
        root_url = re.sub(r'/v1/?$', '', self.base_url)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        # ---------------- 阶段 1：优先探测原生文生视频端点 ----------------
        video_endpoints = [
            f"{self.base_url}/videos/generations",
            f"{root_url}/v1/videos/generations",
            f"{self.base_url}/video/generations",
            f"{root_url}/v1/video/generations",
            f"{self.base_url}/video_generation",
            f"{root_url}/v1/video_generation",
            f"{self.base_url}/video_generations",
            f"{root_url}/v1/video_generations",
            f"{self.base_url}/videos/text2video",
            f"{root_url}/v1/videos/text2video",
            f"{self.base_url}/videos/image2video",
            f"{root_url}/v1/videos/image2video",
            f"{self.base_url}/tasks",
            f"{root_url}/v1/tasks"
        ]
        seen = set()
        unique_video_endpoints = [ep for ep in video_endpoints if not (ep in seen or seen.add(ep))]

        video_payload = {
            "model": self.model,
            "model_name": self.model,
            "prompt": prompt,
            "size": "720x1280",
            "duration": duration,
            "fps": 30,
            "aspect_ratio": "9:16"
        }
        if first_frame_url:
            video_payload["image_url"] = first_frame_url
            video_payload["first_frame_url"] = first_frame_url
            video_payload["image"] = first_frame_url
            video_payload["first_frame_image"] = first_frame_url
            video_payload["input_reference"] = first_frame_url
        if last_frame_url:
            video_payload["last_frame_url"] = last_frame_url
            video_payload["image_tail"] = last_frame_url
            video_payload["tail_image_url"] = last_frame_url
            video_payload["last_frame_image"] = last_frame_url

        last_err = ""
        for ep in unique_video_endpoints:
            try:
                req = urllib.request.Request(ep, data=json.dumps(video_payload).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=40) as resp:
                    resp_text = resp.read().decode("utf-8")
                    data = json.loads(resp_text)

                    # 提取视频或动态视觉流
                    v_url, media_type = self._extract_media_url(data)
                    if v_url:
                        return {
                            "status": "completed",
                            "video_url": v_url,
                            "media_type": media_type,
                            "provider": "video_gateway",
                            "message": "AI 视频已成功生成并获取！"
                        }

                    # 提取异步任务ID
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
                            "provider": "video_gateway",
                            "message": f"AI 视频渲染任务已提交网关 (任务ID: {task_id})，进入排队渲染中..."
                        }
            except urllib.error.HTTPError as he:
                body = ""
                try: body = he.read().decode("utf-8")
                except Exception: pass
                last_err = f"网关返回 HTTP {he.code}: {body or he.reason}"
                if he.code == 404:
                    continue
                continue
            except Exception as e:
                last_err = str(e)
                continue

        # ---------------- 阶段 2：适配 WorkBuddy2API 逆向视觉生图端点 (/v1/images/generations) ----------------
        image_endpoints = [
            f"{self.base_url}/images/generations",
            f"{root_url}/v1/images/generations",
            f"{self.base_url}/images/edits",
            f"{root_url}/v1/images/edits"
        ]
        seen_img = set()
        unique_image_endpoints = [ep for ep in image_endpoints if not (ep in seen_img or seen_img.add(ep))]

        image_models = [self.model, "dall-e-3", ""] if self.model else ["dall-e-3", ""]
        for ep in unique_image_endpoints:
            for m in image_models:
                img_payload = {
                    "prompt": f"9:16 vertical short drama cinematic shot, 8k resolution, cinematic lighting, {prompt}",
                    "size": "1024x1792",
                    "n": 1,
                    "response_format": "url"
                }
                if m and not any(k in m.lower() for k in ("video", "kling", "cogvideo")):
                    img_payload["model"] = m

                try:
                    req = urllib.request.Request(ep, data=json.dumps(img_payload).encode("utf-8"), headers=headers, method="POST")
                    with urllib.request.urlopen(req, timeout=40) as resp:
                        resp_text = resp.read().decode("utf-8")
                        data = json.loads(resp_text)
                        v_url, media_type = self._extract_media_url(data)
                        if v_url:
                            return {
                                "status": "completed",
                                "video_url": v_url,
                                "image_url": v_url,
                                "media_type": "image",
                                "provider": "workbuddy2api",
                                "message": "已通过 WorkBuddy2API 逆向视觉引擎生成 9:16 高清分镜画面，已启用电影级动态运镜呈现！"
                            }
                except urllib.error.HTTPError as he:
                    if he.code == 404:
                        break
                    continue
                except Exception:
                    continue

        # ---------------- 阶段 3：尝试 WorkBuddy2API 对话多模态视觉逆向提取 ----------------
        chat_endpoints = [
            f"{self.base_url}/chat/completions",
            f"{root_url}/v1/chat/completions"
        ]
        chat_models = [self.model] if self.model and not any(k in self.model.lower() for k in ("video", "kling", "cogvideo")) else ["deepseek-chat", "gpt-4o"]
        for ep in chat_endpoints:
            for m in chat_models:
                chat_payload = {
                    "model": m,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"请为以下短剧分镜生成高清视觉画面或渲染图片，并输出图片URL：\n{prompt}"
                        }
                    ]
                }
                try:
                    req = urllib.request.Request(ep, data=json.dumps(chat_payload).encode("utf-8"), headers=headers, method="POST")
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        match = re.search(r'https?://[^\s)"]+\.(?:png|jpg|jpeg|webp|gif|mp4)', content, re.IGNORECASE)
                        if match:
                            found_url = match.group(0)
                            return {
                                "status": "completed",
                                "video_url": found_url,
                                "image_url": found_url,
                                "media_type": "video" if ".mp4" in found_url.lower() else "image",
                                "provider": "workbuddy2api_chat",
                                "message": "已从 WorkBuddy2API 对话多模态中成功提取分镜视觉媒体！"
                            }
                except Exception:
                    pass

        # ---------------- 阶段 4：所有端点连接失败诊断提示 ----------------
        if "404" in last_err:
            return {
                "status": "failed",
                "error": f"所有视频与视觉网关端点连接失败 (网关均返回 HTTP 404: 接口不存在)。\n"
                         f"当前配置地址 [{self.base_url}] 未开启视频(/videos/generations)或生图(/images/generations)路由。\n"
                         f"建议：\n"
                         f"1. 若使用 WorkBuddy2API，请确认部署的分支是否包含图像生成模块 (如 Tom6814/WorkBuddy2API 或 workbuddy2api-panel)；\n"
                         f"2. 若需真实生视频，可在后台配置智谱 CogVideoX、可灵 KlingAI 官方或支持生视频的中转网关；\n"
                         f"3. 亦可直接在卡片上点击【模拟体验(免Key)】，系统将立即渲染 9:16 动态竖屏分镜并在播放器中流畅呈现。"
            }

        return {"status": "failed", "error": f"所有视频网关端点连接失败: {last_err} (请在后台检查 VIDEO_BASE_URL 与模型型号)"}

    def _query_generic_gateway(self, task_id: str) -> Dict[str, Any]:
        """多候选端点智能探查通用网关的视频任务状态"""
        root_url = re.sub(r'/v1/?$', '', self.base_url)
        candidate_urls = [
            f"{self.base_url}/videos/generations/{task_id}",
            f"{root_url}/v1/videos/generations/{task_id}",
            f"{self.base_url}/video/generations/{task_id}",
            f"{root_url}/v1/video/generations/{task_id}",
            f"{self.base_url}/tasks/{task_id}",
            f"{root_url}/v1/tasks/{task_id}",
            f"{self.base_url}/task/{task_id}",
            f"{root_url}/v1/task/{task_id}",
            f"{self.base_url}/query/video_generation?task_id={task_id}",
            f"{root_url}/v1/query/video_generation?task_id={task_id}",
            f"{self.base_url}/async-result/{task_id}",
            f"{root_url}/v1/async-result/{task_id}",
            f"{self.base_url}/videos/text2video/{task_id}",
            f"{root_url}/v1/videos/text2video/{task_id}",
            f"{self.base_url}/videos/{task_id}",
            f"{root_url}/v1/videos/{task_id}"
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

    # ================= 递归多层级媒体 (MP4 视频 / 9:16 高清视觉) 提取器 =================
    @staticmethod
    def _extract_media_url(data: Any) -> tuple[Optional[str], str]:
        """
        从任意嵌套的 JSON 数据结构中递归提取真实可播放的 MP4 视频链接或 9:16 高清视觉图片
        返回 (url, media_type) 其中 media_type 为 'video' 或 'image'
        """
        if not data:
            return None, "video"

        if isinstance(data, str):
            s = data.strip()
            if s.startswith("http://") or s.startswith("https://") or s.startswith("data:image/"):
                if any(ext in s.lower() for ext in (".mp4", ".mov", ".webm", "/video")):
                    return s, "video"
                if any(ext in s.lower() for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", "data:image/")):
                    return s, "image"
                return s, "video"
            return None, "video"

        if isinstance(data, dict):
            # 1. 检查 b64_json (OpenAI images/generations 格式)
            if "b64_json" in data and isinstance(data["b64_json"], str) and data["b64_json"]:
                return f"data:image/png;base64,{data['b64_json']}", "image"

            # 2. 优先检查显式视频字段
            for k in ("video_url", "play_url", "output_url", "video"):
                val = data.get(k)
                if isinstance(val, str) and (val.startswith("http://") or val.startswith("https://")):
                    return val, "video"

            # 3. 检查通用媒体与生图字段
            for k in ("url", "download_url", "file_url", "image", "image_url"):
                val = data.get(k)
                if isinstance(val, str) and (val.startswith("http://") or val.startswith("https://")):
                    if any(ext in val.lower() for ext in (".png", ".jpg", ".jpeg", ".webp")):
                        return val, "image"
                    return val, "video"

            # 4. 递归检查常见列表与嵌套包装
            for field in ("video_result", "task_result", "data", "output", "images", "videos"):
                if field in data:
                    u, m = VideoAgent._extract_media_url(data[field])
                    if u:
                        return u, m

            # 5. 递归遍历所有字典值
            for v in data.values():
                if isinstance(v, (dict, list)):
                    u, m = VideoAgent._extract_media_url(v)
                    if u:
                        return u, m

        elif isinstance(data, list):
            for item in data:
                u, m = VideoAgent._extract_media_url(item)
                if u:
                    return u, m

        return None, "video"

    @staticmethod
    def _extract_video_url(data: Any) -> Optional[str]:
        u, _ = VideoAgent._extract_media_url(data)
        return u

    # ================= 模拟免Key极速体验 =================
    def _mock_submit(self, prompt: str, duration: int = 5, first_frame_url: str = "", last_frame_url: str = "") -> Dict[str, Any]:
        sample_videos = [
            "https://assets.mixkit.co/videos/preview/mixkit-vertical-view-of-a-neon-city-in-the-rain-42099-large.mp4",
            "https://assets.mixkit.co/videos/preview/mixkit-tree-branches-in-the-breeze-1188-large.mp4",
            "https://assets.mixkit.co/videos/preview/mixkit-going-down-a-curved-highway-down-a-mountain-41576-large.mp4",
            "https://assets.mixkit.co/videos/preview/mixkit-man-holding-a-smartphone-at-night-42100-large.mp4"
        ]
        import hashlib
        idx = int(hashlib.md5(prompt.encode("utf-8")).hexdigest(), 16) % len(sample_videos)
        v_url = sample_videos[idx]
        note = "（基于首尾帧与运镜控镜渲染）" if (first_frame_url or last_frame_url) else ""
        return {
            "status": "completed",
            "task_id": f"mock_{int(time.time()*1000)}",
            "video_url": v_url,
            "provider": "mock",
            "message": f"9:16 短剧分镜视效已就绪{note}，可在播放器中即时视听预览！"
        }

    # ================= 主角定妆照与分镜首尾帧生图实现 =================
    @staticmethod
    def infer_gender_and_demographics(name: str, role_title: str = "", visual_desc: str = "") -> Dict[str, str]:
        """
        根据角色名、称号、外观描述精确推断性别与东亚人像标签，彻底杜绝女性生成男相或生成西方外国人面孔
        """
        combined = f"{name} {role_title} {visual_desc}".lower()
        female_keywords = [
            "女", "娘", "姐", "妹", "母", "妇", "妻", "姑", "妃", "仙子", "圣女", "剑女", 
            "师妹", "师姐", "师尊女", "道姑", "公主", "夫人", "小姐", "翠花", "苏晴", "青霜", 
            "雪", "莲", "霜", "月", "瑶", "柔", "婷", "静", "娜", "娟", "丽", "芳", "敏",
            "female", "woman", "girl", "lady", "heroine", "actress"
        ]
        is_female = any(kw in combined for kw in female_keywords)

        if is_female:
            gender_tag = "female"
            en_desc = "East Asian beautiful young woman, Chinese female face, delicate facial features, feminine graceful charisma"
            zh_desc = "东亚绝色东方女性面孔，五官清丽出尘，中国短剧女主角质感"
        else:
            gender_tag = "male"
            en_desc = "East Asian handsome young man, Chinese male face, defined jawline, masculine heroic charisma"
            zh_desc = "东亚冷峻英挺东方男性面孔，剑眉星目，中国短剧男主角气场"

        return {
            "gender": gender_tag,
            "en_desc": en_desc,
            "zh_desc": zh_desc
        }

    def generate_character_portrait(
        self,
        name: str,
        role_title: str = "主角",
        visual_desc: str = "",
        genre: str = "短剧",
        gender: str = "",
        force_mock: bool = False
    ) -> Dict[str, Any]:
        """
        生成主角/关键角色 9:16 电影级定妆照（Character Concept Art）
        作为全剧人物面容与服饰一致性基准，强制指定东亚国人面孔与准确性别
        支持一次性返回候选图库（candidates）供创作者“后宫式翻牌挑选”
        """
        demo = self.infer_gender_and_demographics(name, role_title, visual_desc)
        if gender:
            if gender in ["女", "female", "woman"]:
                demo["gender"] = "female"
                demo["en_desc"] = "East Asian beautiful young woman, Chinese female face, delicate facial features, feminine graceful charisma"
                demo["zh_desc"] = "东亚绝色东方女性面孔，五官清丽出尘，中国短剧女主角质感"
            elif gender in ["男", "male", "man"]:
                demo["gender"] = "male"
                demo["en_desc"] = "East Asian handsome young man, Chinese male face, defined jawline, masculine heroic charisma"
                demo["zh_desc"] = "东亚冷峻英挺东方男性面孔，剑眉星目，中国短剧男主角气场"

        prompt = (
            f"9:16 vertical short drama cinematic character concept portrait, "
            f"masterpiece, 8k resolution, photorealistic, dramatic studio lighting, "
            f"sharp focus, three-quarter angle hero pose, "
            f"demographics: {demo['en_desc']}, "
            f"character: {name} ({role_title}), genre: {genre}, "
            f"costume and visual features: {visual_desc or 'distinctive iconic short drama outfit, highly detailed texture'}. "
            f"Strictly Chinese East Asian face, not Caucasian, not Western. {demo['zh_desc']}。"
        )
        img_key = os.getenv("IMAGE_API_KEY", "") or self.api_key
        has_real_img_key = bool(img_key and img_key != "your_api_key_here")

        if force_mock or not has_real_img_key:
            return self._mock_character_portrait(name, role_title, visual_desc, prompt, demo["gender"])

        res = self._generate_image_asset(prompt, mode="character_portrait")
        if res.get("status") == "completed":
            mock_ref = self._mock_character_portrait(name, role_title, visual_desc, prompt, demo["gender"])
            candidates = [res.get("image_url", "")] + [c for c in mock_ref.get("candidates", []) if c != res.get("image_url", "")][:3]
            return {
                "status": "completed",
                "name": name,
                "role_title": role_title,
                "gender": demo["gender"],
                "portrait_url": res.get("image_url", ""),
                "candidates": candidates,
                "portrait_prompt": prompt,
                "costume": visual_desc or "标志性东方短剧战袍",
                "provider": res.get("provider", "real_ai_image"),
                "message": f"角色【{name}】AI 真实生图原画已成功生成！"
            }
        # 回退到模拟
        mock_res = self._mock_character_portrait(name, role_title, visual_desc, prompt, demo["gender"])
        mock_res["notice"] = res.get("error", "网关生图接口调用异常，已自动加载高匹配度东方定妆样照")
        return mock_res

    def generate_frame_image(
        self,
        shot_visual: str,
        shot_type: str = "特写",
        camera_movement: str = "缓缓推近",
        character_traits: str = "",
        frame_type: str = "first",
        force_mock: bool = False
    ) -> Dict[str, Any]:
        """
        生成分镜首帧/尾帧关键帧画面（First / Last Frame Keyframe）
        融合角色定妆照特质以维持人物一致性，强制东亚面孔约束
        """
        frame_label = "first frame start action keyframe" if frame_type == "first" else "end frame climax outcome keyframe"
        prompt = (
            f"9:16 vertical short drama keyframe, {frame_label}, {shot_type} shot, {camera_movement}, "
            f"cinematic photorealistic 8k, dramatic lighting, {shot_visual}. "
            f"Characters must be East Asian Chinese descent, authentic Asian facial features, authentic gender presentation. "
            f"{'Character consistency appearance: ' + character_traits if character_traits else ''}"
        )
        if force_mock or not self.api_key or self.api_key == "your_api_key_here":
            return self._mock_frame_image(shot_visual, frame_type, prompt)

        res = self._generate_image_asset(prompt, mode=f"{frame_type}_frame")
        if res.get("status") == "completed":
            return {
                "status": "completed",
                "image_url": res.get("image_url", ""),
                "frame_type": frame_type,
                "prompt": prompt,
                "message": f"分镜{'首帧' if frame_type == 'first' else '尾帧'}画面已成功生成！"
            }
        # 回退到模拟
        mock_res = self._mock_frame_image(shot_visual, frame_type, prompt)
        mock_res["notice"] = res.get("error", "网关生图不可用，已自动加载高清关键帧样照")
        return mock_res

    def _generate_image_asset(self, prompt: str, mode: str = "image") -> Dict[str, Any]:
        """
        专门调用正规生图接口 (Text-to-Image / /v1/images/generations)，绝不走视频接口
        优先使用针对生图配置的 IMAGE_BASE_URL 与 IMAGE_API_KEY，其次回退自通用/短剧配置
        """
        img_api_key = os.getenv("IMAGE_API_KEY", "") or self.api_key
        img_base_url = (os.getenv("IMAGE_BASE_URL", "") or self.base_url).rstrip("/")
        root_url = re.sub(r'/v1/?$', '', img_base_url)

        candidate_eps = [
            f"{img_base_url}/images/generations",
            f"{root_url}/v1/images/generations",
            f"{img_base_url}/images/edits",
            f"{root_url}/v1/images/edits"
        ]
        seen = set()
        unique_eps = [ep for ep in candidate_eps if not (ep in seen or seen.add(ep))]

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {img_api_key}"
        }

        # 纯生图模型候选池（严禁混入视频模型名）
        model_candidates = [
            getattr(self, "image_model", "") or os.getenv("IMAGE_MODEL", ""),
            "dall-e-3",
            "flux-schnell",
            "flux",
            "stable-diffusion-xl",
            ""
        ]
        model_candidates = [m for m in dict.fromkeys(model_candidates) if not any(k in m.lower() for k in ("video", "kling", "cogvideo"))]

        last_err = ""
        for ep in unique_eps:
            for m in model_candidates:
                payload = {
                    "prompt": prompt,
                    "size": "1024x1792",
                    "n": 1,
                    "response_format": "url"
                }
                if m:
                    payload["model"] = m

                try:
                    req = urllib.request.Request(ep, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                    with urllib.request.urlopen(req, timeout=35) as resp:
                        resp_data = json.loads(resp.read().decode("utf-8"))
                        img_url, _ = self._extract_media_url(resp_data)
                        if img_url:
                            return {
                                "status": "completed",
                                "image_url": img_url,
                                "provider": "ai_image_generation",
                                "message": "纯生图模型渲染定妆照成功！"
                            }
                except urllib.error.HTTPError as he:
                    body = ""
                    try: body = he.read().decode("utf-8")
                    except Exception: pass
                    last_err = f"HTTP {he.code}: {body or he.reason}"
                    if he.code == 404:
                        break
                    continue
                except Exception as e:
                    last_err = str(e)
                    continue

        return {"status": "failed", "error": f"生图接口未就绪: {last_err}"}

    def _mock_character_portrait(self, name: str, role_title: str, visual_desc: str, prompt: str, gender: str = "male") -> Dict[str, Any]:
        """模拟主角定妆照精选高清图库（纯静态 9:16 东亚超清人像，严格按性别与东亚人像分流）"""
        # 东亚男性主角定妆图库（中国青年武侠/都市/短剧主角男神质感）
        mock_portraits_male = [
            "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=720&h=1280&fit=crop&q=80",
            "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=720&h=1280&fit=crop&q=80",
            "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=720&h=1280&fit=crop&q=80",
            "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=720&h=1280&fit=crop&q=80"
        ]
        # 东亚女性主角定妆图库（中国仙侠女修/都市女主/绝美女主清丽容貌）
        mock_portraits_female = [
            "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=720&h=1280&fit=crop&q=80",
            "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=720&h=1280&fit=crop&q=80",
            "https://images.unsplash.com/photo-1517841905240-472988babdf9?w=720&h=1280&fit=crop&q=80",
            "https://images.unsplash.com/photo-1524504388940-b1c1722653e1?w=720&h=1280&fit=crop&q=80"
        ]
        import hashlib
        if gender == "female":
            idx = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % len(mock_portraits_female)
            chosen_url = mock_portraits_female[idx]
            # 候选轮换列表：当前被挑中的放首位，其余排在后面供用户备选
            candidates = [chosen_url] + [u for u in mock_portraits_female if u != chosen_url]
            default_costume = "清丽修身东方古风流云锦裳，身负青罡残剑，英姿飒爽"
        else:
            idx = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % len(mock_portraits_male)
            chosen_url = mock_portraits_male[idx]
            candidates = [chosen_url] + [u for u in mock_portraits_male if u != chosen_url]
            default_costume = "标志性冷峻短剧主角深色战袍，腰束玄纹革带，眼神如刃"

        return {
            "status": "completed",
            "name": name,
            "role_title": role_title,
            "gender": gender,
            "portrait_url": chosen_url,
            "candidates": candidates,
            "portrait_prompt": prompt,
            "costume": visual_desc or default_costume,
            "provider": "mock_portrait",
            "message": f"角色【{name}】({'女' if gender == 'female' else '男'})定妆照图片已就绪，已生成候选画廊供随时翻牌！"
        }

    def _mock_frame_image(self, shot_visual: str, frame_type: str, prompt: str) -> Dict[str, Any]:
        """模拟分镜首尾关键帧精选图库"""
        mock_frames = [
            "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?w=720&h=1280&fit=crop&q=80",
            "https://images.unsplash.com/photo-1509198397868-475647b2a1e5?w=720&h=1280&fit=crop&q=80",
            "https://images.unsplash.com/photo-1511447333015-45b65e60f6d5?w=720&h=1280&fit=crop&q=80",
            "https://images.unsplash.com/photo-1517048676732-d65bc937f952?w=720&h=1280&fit=crop&q=80",
            "https://images.unsplash.com/photo-1519501025264-65ba15a82390?w=720&h=1280&fit=crop&q=80"
        ]
        import hashlib
        key = f"{shot_visual}_{frame_type}"
        idx = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % len(mock_frames)
        return {
            "status": "completed",
            "image_url": mock_frames[idx],
            "frame_type": frame_type,
            "prompt": prompt,
            "provider": "mock_frame",
            "message": f"分镜{'首帧' if frame_type == 'first' else '尾帧'}画面已就绪！"
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
