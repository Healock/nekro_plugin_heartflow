"""独立 judge 模型的 HTTP 客户端。"""

from __future__ import annotations

import json

import aiohttp


class JudgeClientError(RuntimeError):
    """独立 judge 请求失败。"""


class JudgeNotConfiguredError(JudgeClientError):
    """独立 judge 尚未配置。"""


class JudgeClient:
    """访问 OpenAI-compatible JSON 接口的轻量客户端。"""

    def __init__(self, base_url: str, api_key: str, model: str, api_path: str = "/chat/completions") -> None:
        self.base_url = base_url.strip().rstrip("/")
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.api_path = api_path if api_path.startswith("/") else f"/{api_path}"

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.model)

    def _url(self) -> str:
        if self.base_url.endswith(self.api_path):
            return self.base_url
        return f"{self.base_url}{self.api_path}"

    async def complete(self, system_prompt: str, user_prompt: str, timeout: float) -> str:
        """请求一次模型输出并提取文本。"""

        if not self.is_configured:
            raise JudgeNotConfiguredError("judge_api_base_url 和 judge_model 必须同时配置")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        client_timeout = aiohttp.ClientTimeout(total=max(0.1, timeout))
        try:
            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                async with session.post(self._url(), headers=headers, json=payload) as response:
                    raw_text = await response.text()
                    if response.status >= 400:
                        raise JudgeClientError(f"judge HTTP {response.status}: {raw_text[:200]}")
                    try:
                        result = json.loads(raw_text)
                    except json.JSONDecodeError as exc:
                        raise JudgeClientError("judge 返回不是 JSON") from exc
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise JudgeClientError(f"judge 网络请求失败：{type(exc).__name__}") from exc
        return _extract_completion_text(result)


def _extract_completion_text(result: object) -> str:
    if not isinstance(result, dict):
        raise JudgeClientError("judge 响应顶层不是对象")
    choices = result.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    text_parts = [item.get("text", "") for item in content if isinstance(item, dict)]
                    return "".join(str(part) for part in text_parts)
    output_text = result.get("output_text")
    if isinstance(output_text, str):
        return output_text
    raise JudgeClientError("judge 响应缺少文本内容")
