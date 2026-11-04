"""DeepSeek chat-completion client with an injectable HTTP transport (Sprint 4).

Two layers, and only the lower one speaks HTTP:

* the transport (DeepSeekTransport) - default HttpxTransport wraps
  httpx.AsyncClient. It receives an already built URL/body/headers and one
  timeout, and returns TransportResponse. Tests pass a stub, so no test can
  reach api.deepseek.com even by accident;
* the client (DeepSeekClient) - builds the body, applies the timeout, and
  classifies the outcome into AiUpstreamTimeout or AiUpstreamError so the service
  layer never has to know what an httpx exception looks like.

The API key is read from settings when the client is built and placed only in the
Authorization header of the outbound request. It is never logged, never returned
in a response and never written to a row: redact() exists so that even an
exception message coming back from the transport cannot carry it into a log line.

The frozen scope of this module is one stateless call: no streaming, no
multi-turn memory. The user message carries the learner's question plus the
lesson/exercise *titles*; submitted code text is not a parameter of any function
here, so it cannot be sent (Sprint 4 security boundary).
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
DEFAULT_TIMEOUT_SECONDS = 30.0
REDACTED = "***"
# Bounds the outbound text so one call cannot become an unbounded upload.
QUESTION_MAX_LENGTH = 2000
CONTEXT_TITLE_MAX_LENGTH = 200
# One retrieved reference line is a title plus a snippet; this keeps three of them
# (the default KNOWLEDGE_TOP_K) well inside the model's context budget.
KNOWLEDGE_REFERENCE_MAX_LENGTH = 400

SYSTEM_PROMPT = (
    "你是 AI Learning Copilot 的 Python 学习导师，面向零基础中文学习者。"
    "规则：1) 只用中文回答；2) 直接针对学员当前的问题，不要复述题目；"
    "3) 不要输出与学习无关的内容；4) 不确定的地方要说明不确定，不要编造 API。"
)

# The assistance level is the only lever the learner has over how much is given
# away, so it is stated to the model explicitly instead of being implied.
ASSISTANCE_INSTRUCTIONS: dict[str, str] = {
    "none": "只给方向：指出该看哪一行、哪一类语法，不要给出可直接粘贴的代码。",
    "hint": "给一条具体提示：说明下一步做什么、为什么，最多给半行代码。",
    "partial_code": "给出部分代码骨架，用注释标出学员需要自己补的空白，不要整段给答案。",
    "full_answer": "给出完整参考答案，并逐行说明每一步为什么这样做。",
}


@dataclass(frozen=True)
class TransportResponse:
    """What a transport returns: the HTTP status and the decoded JSON body."""

    status_code: int
    payload: Mapping[str, Any] | None = None


class DeepSeekTransport(Protocol):
    """The single seam between this client and the network.

    Implementations raise the same exceptions httpx.AsyncClient raises
    (httpx.TimeoutException for a timeout, httpx.HTTPError / OSError for a
    connection or protocol failure); DeepSeekClient classifies them.
    """

    async def post(
        self,
        url: str,
        *,
        json: Mapping[str, Any],
        headers: Mapping[str, str],
        timeout: float,
    ) -> TransportResponse:  # pragma: no cover - protocol declaration
        ...


class HttpxTransport:
    """Default transport: one httpx.AsyncClient per call."""

    async def post(
        self,
        url: str,
        *,
        json: Mapping[str, Any],
        headers: Mapping[str, str],
        timeout: float,
    ) -> TransportResponse:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            response = await client.post(url, json=dict(json), headers=dict(headers))
        try:
            payload = response.json()
        except ValueError:
            payload = None
        return TransportResponse(status_code=response.status_code, payload=payload)


class AiCallError(Exception):
    """Base class for every classified failure of one tutor call."""

    error_code = "AI_UPSTREAM_ERROR"

    def __init__(self, error_code: str, detail: str = "") -> None:
        super().__init__(detail or error_code)
        self.error_code = error_code
        self.detail = detail


class AiUpstreamTimeout(AiCallError):
    """The call exceeded the configured timeout."""

    def __init__(self, detail: str = "") -> None:
        super().__init__("AI_TIMEOUT", detail)


class AiUpstreamError(AiCallError):
    """The provider answered with an error, or with something unusable."""


@dataclass(frozen=True)
class AiCompletion:
    """One successful answer plus the usage numbers the ledger needs."""

    answer: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    citations: tuple[str, ...] = field(default_factory=tuple)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def usage(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


def redact(text: str, secret: str) -> str:
    """Replace the configured key inside a message before it reaches a log line."""
    if secret and secret in text:
        return text.replace(secret, REDACTED)
    return text


def _clip(value: str, limit: int) -> str:
    text = " ".join(str(value).split())
    return text[:limit]


def build_user_message(
    question: str,
    assistance_level: str,
    lesson_title: str | None = None,
    exercise_title: str | None = None,
    knowledge_context: Sequence[str] = (),
) -> str:
    """Assemble the outbound user text from the question and titles only.

    There is deliberately no parameter for submitted code: the security boundary
    of Sprint 4 is enforced by this signature, not by a caller remembering to
    trim something.
    """
    parts: list[str] = []
    if lesson_title:
        parts.append(f"课程：{_clip(lesson_title, CONTEXT_TITLE_MAX_LENGTH)}")
    if exercise_title:
        parts.append(f"练习：{_clip(exercise_title, CONTEXT_TITLE_MAX_LENGTH)}")
    if parts:
        parts.append("")
    references = [str(line).strip() for line in knowledge_context if str(line).strip()]
    if references:
        parts.append("参考资料（本地知识库检索所得，可能不完整；能用就引用，不确定要说明）：")
        for reference in references:
            parts.append(_clip(reference, KNOWLEDGE_REFERENCE_MAX_LENGTH))
        parts.append("")
    parts.append("学员的问题：")
    parts.append(_clip(question, QUESTION_MAX_LENGTH))
    instruction = ASSISTANCE_INSTRUCTIONS.get(assistance_level, ASSISTANCE_INSTRUCTIONS["hint"])
    parts.append("")
    parts.append(f"回答方式：{instruction}")
    return "\n".join(parts)


def _parse_usage(payload: Mapping[str, Any]) -> tuple[int, int]:
    usage = payload.get("usage")
    if not isinstance(usage, Mapping):
        return 0, 0

    def _as_int(value: Any) -> int:
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return 0

    return _as_int(usage.get("prompt_tokens")), _as_int(usage.get("completion_tokens"))


def _clip_answer(payload: Mapping[str, Any]) -> str:
    """choices[0].message.content, or '' when the shape is not the expected one."""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, Mapping):
        return ""
    message = first.get("message")
    if not isinstance(message, Mapping):
        return ""
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


class DeepSeekClient:
    """Stateless DeepSeek client. One instance per request, built from settings."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-flash",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: DeepSeekTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = (base_url or "").rstrip("/")
        self.model = model
        self.timeout_seconds = float(timeout_seconds)
        self._transport: DeepSeekTransport = transport or HttpxTransport()

    @property
    def configured(self) -> bool:
        """A blank key means the provider is not configured, not that it failed."""
        return bool(self._api_key.strip())

    def _headers(self) -> dict[str, str]:
        # The key appears here and nowhere else in the process.
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _body(
        self,
        question: str,
        assistance_level: str,
        lesson_title: str | None,
        exercise_title: str | None,
        knowledge_context: Sequence[str] = (),
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_user_message(
                        question,
                        assistance_level,
                        lesson_title,
                        exercise_title,
                        knowledge_context,
                    ),
                },
            ],
            "stream": False,
            "temperature": 0.2,
        }

    async def complete(
        self,
        *,
        question: str,
        assistance_level: str,
        lesson_title: str | None = None,
        exercise_title: str | None = None,
        knowledge_context: Sequence[str] = (),
    ) -> AiCompletion:
        """One chat completion, classified into AiUpstreamTimeout / AiUpstreamError."""
        if not self.configured:
            # Defensive: the orchestrator refuses before ever calling this.
            raise AiUpstreamError("AI_UNAVAILABLE", "DEEPSEEK_API_KEY 未配置")

        url = f"{self._base_url}{CHAT_COMPLETIONS_PATH}"
        body = self._body(
            question, assistance_level, lesson_title, exercise_title, knowledge_context
        )
        started = time.perf_counter()
        try:
            response = await self._transport.post(
                url, json=body, headers=self._headers(), timeout=self.timeout_seconds
            )
        except httpx.TimeoutException as exc:
            raise AiUpstreamTimeout(redact(str(exc), self._api_key)) from exc
        except (httpx.HTTPError, OSError) as exc:
            raise AiUpstreamError(
                "AI_TRANSPORT_ERROR", redact(f"{type(exc).__name__}: {exc}", self._api_key)
            ) from exc

        latency_ms = int(round((time.perf_counter() - started) * 1000))
        if response.status_code >= 400:
            raise AiUpstreamError(f"AI_UPSTREAM_STATUS_{response.status_code}")
        if not isinstance(response.payload, Mapping):
            raise AiUpstreamError("AI_UPSTREAM_BAD_PAYLOAD")

        payload = response.payload
        answer = _clip_answer(payload)
        if not answer:
            raise AiUpstreamError("AI_UPSTREAM_EMPTY_ANSWER")
        prompt_tokens, completion_tokens = _parse_usage(payload)
        model = payload.get("model")
        return AiCompletion(
            answer=answer,
            model=str(model) if isinstance(model, str) and model else self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )


__all__ = [
    "ASSISTANCE_INSTRUCTIONS",
    "AiCallError",
    "AiCompletion",
    "AiUpstreamError",
    "AiUpstreamTimeout",
    "DeepSeekClient",
    "DeepSeekTransport",
    "HttpxTransport",
    "TransportResponse",
    "build_user_message",
    "redact",
]
