import json
import re
import urllib.request
import urllib.error
import time
from typing import List, Dict, Any, Optional

class LLMClient:
    """通用的 OpenAI 兼容接口调用器（原生标准库实现，无第三方依赖）"""

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        if not self.base_url.endswith("/v1") and not "/chat/completions" in self.base_url:
            # 常见情况自动补全 /v1
            if not self.base_url.endswith("/v1"):
                self.endpoint = f"{self.base_url}/v1/chat/completions"
            else:
                self.endpoint = f"{self.base_url}/chat/completions"
        else:
            self.endpoint = f"{self.base_url}/chat/completions"

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        retries: int = 3
    ) -> str:
        """同步发起聊天请求"""
        if not self.api_key or self.api_key == "your_api_key_here":
            raise ValueError(
                "未配置有效 API KEY！请在 `c:\\Work\\天道\\.env` 文件中填入你的 OPENAI_API_KEY。"
            )

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        req = urllib.request.Request(self.endpoint, data=data, headers=headers, method="POST")

        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=90) as response:
                    body = response.read().decode("utf-8")
                    res_json = json.loads(body)
                    result = res_json["choices"][0]["message"]["content"]
                    # 保护后端私有服务器：每次成功调用后微休眠 1 秒，防突发流量冲垮 KV 缓存
                    time.sleep(1.0)
                    return result
            except urllib.error.HTTPError as e:
                err_content = e.read().decode("utf-8", errors="ignore")
                if attempt == retries - 1:
                    raise RuntimeError(f"API 请求失败 HTTP {e.code}: {err_content}")
                # 针对 429 限流或 502/504 超时进行指数退避
                backoff = (attempt + 1) * 4.0 if e.code in (429, 502, 503, 504) else (attempt + 1) * 2.0
                print(f"[LLMClient 护栏] 遭遇 HTTP {e.code}，正在执行退避保护等待 {backoff:.1f} 秒重试...")
                time.sleep(backoff)
            except Exception as e:
                if attempt == retries - 1:
                    raise RuntimeError(f"请求异常: {str(e)}")
                backoff = (attempt + 1) * 2.5
                print(f"[LLMClient 护栏] 网络异常: {e}，等待 {backoff:.1f} 秒重试...")
                time.sleep(backoff)

        return ""

    def chat_stream(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        retries: int = 2
    ):
        """流式发起聊天请求，实时 yield 生成的内容片段 (delta chunks)"""
        if not self.api_key or self.api_key == "your_api_key_here":
            raise ValueError(
                "未配置有效 API KEY！请在 .env 文件中配置 OPENAI_API_KEY。"
            )

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True
        }

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        req = urllib.request.Request(self.endpoint, data=data, headers=headers, method="POST")

        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=90) as response:
                    for line_bytes in response:
                        line = line_bytes.decode("utf-8", errors="ignore").strip()
                        if not line:
                            continue
                        if line.startswith("data: "):
                            raw_data = line[6:].strip()
                            if raw_data == "[DONE]":
                                break
                            try:
                                res_json = json.loads(raw_data)
                                delta = res_json["choices"][0]["delta"].get("content", "")
                                if delta:
                                    yield delta
                            except Exception:
                                continue
                    time.sleep(0.5)
                    return
            except urllib.error.HTTPError as e:
                err_content = e.read().decode("utf-8", errors="ignore")
                if attempt == retries - 1:
                    raise RuntimeError(f"流式 API 请求失败 HTTP {e.code}: {err_content}")
                backoff = (attempt + 1) * 3.0
                print(f"[LLMClient 护栏] 流式遭遇 HTTP {e.code}，等待 {backoff:.1f} 秒重试...")
                time.sleep(backoff)
            except Exception as e:
                if attempt == retries - 1:
                    raise RuntimeError(f"流式请求异常: {str(e)}")
                backoff = (attempt + 1) * 2.0
                print(f"[LLMClient 护栏] 流式网络异常: {e}，等待 {backoff:.1f} 秒重试...")
                time.sleep(backoff)

    @staticmethod
    def extract_json(text: str) -> Optional[Dict[str, Any]]:
        """从 LLM 返回的内容中提取结构化 JSON"""
        text = text.strip()
        # 匹配 ```json ... ```
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1).strip()
        
        # 尝试直接解析
        try:
            return json.loads(text)
        except Exception:
            # 尝试寻找最外层大括号
            first_brace = text.find("{")
            last_brace = text.rfind("}")
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                try:
                    return json.loads(text[first_brace : last_brace + 1])
                except Exception:
                    pass
        return None
