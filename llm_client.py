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

        # 智能模型别名感知：针对聚合网关前缀 (如 trae.si2api.top 下的 trae: 与 solo:) 自动构建降级候选链
        models_to_try = [model]
        base_lower = self.base_url.lower()
        if "trae" in base_lower or "si2api" in base_lower:
            if model.startswith("solo:"):
                models_to_try.append(model.replace("solo:", "trae:"))
            elif model.startswith("global:"):
                models_to_try.append(model.replace("global:", "trae:"))
            elif not ":" in model:
                models_to_try.append(f"trae:{model}")

        last_error = None
        for m_curr in models_to_try:
            payload["model"] = m_curr
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(self.endpoint, data=data, headers=headers, method="POST")

            for attempt in range(retries):
                try:
                    with urllib.request.urlopen(req, timeout=90) as response:
                        body = response.read().decode("utf-8")
                        # 兼容强开 SSE 流式响应的聚合网关（即使 stream=False 仍返回 text/event-stream 数据行）
                        if body.strip().startswith("data:") or "data: {" in body:
                            full_chunks = []
                            for line in body.splitlines():
                                line = line.strip()
                                if not line or line.startswith(":") or line == "data: [DONE]":
                                    continue
                                if line.startswith("data:"):
                                    line = line[5:].strip()
                                try:
                                    chunk = json.loads(line)
                                    choices = chunk.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {})
                                        content = delta.get("content") or choices[0].get("message", {}).get("content", "")
                                        if content:
                                            full_chunks.append(content)
                                except Exception:
                                    continue
                            result = "".join(full_chunks)
                        else:
                            res_json = json.loads(body)
                            result = res_json["choices"][0]["message"]["content"]

                        time.sleep(0.5)
                        return result
                except urllib.error.HTTPError as e:
                    err_content = e.read().decode("utf-8", errors="ignore")
                    last_error = RuntimeError(f"API 请求失败 HTTP {e.code}: {err_content}")
                    # 若遇到 503 no_account 且有下一个模型别名，立即切换测试下一候选
                    if ("no_account" in err_content or e.code == 503) and m_curr != models_to_try[-1]:
                        print(f"[LLMClient 智能路由] 模型 {m_curr} 渠道繁忙无账号，自动切换候选模型 {models_to_try[-1]}...")
                        break
                    if e.code in (401, 403):
                        # 401/403 为明确密钥鉴权失败，直接抛出，无需盲目重试浪费等待时间
                        raise last_error
                    if attempt == retries - 1 and m_curr == models_to_try[-1]:
                        raise last_error
                    backoff = (attempt + 1) * 3.0 if e.code in (429, 502, 503, 504) else (attempt + 1) * 2.0
                    time.sleep(backoff)
                except Exception as e:
                    last_error = RuntimeError(f"请求异常: {str(e)}")
                    if attempt == retries - 1 and m_curr == models_to_try[-1]:
                        raise last_error
                    time.sleep((attempt + 1) * 2.0)

        if last_error:
            raise last_error
        return ""

    def call_chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        retries: int = 3
    ) -> str:
        """兼容接口：支持 messages 首位传参"""
        target_model = model or "deepseek-chat"
        return self.chat(model=target_model, messages=messages, temperature=temperature, max_tokens=max_tokens, retries=retries)

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
