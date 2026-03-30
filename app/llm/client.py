from __future__ import annotations

import json
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.logging_config import logger
from app.core.settings import get_settings
from app.schemas.common import LLMAnalysisResult


class LLMClient:
    def __init__(self):
        self.settings = get_settings()

    def enabled(self) -> bool:
        return bool(self.settings.llm_enabled and self.settings.llm_api_key and self.settings.llm_model)

    def analyze(
        self,
        prompt: str,
        *,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
    ) -> tuple[LLMAnalysisResult, dict[str, Any], dict[str, Any]]:
        if not self.enabled():
            fallback = LLMAnalysisResult(
                root_cause_summary="LLM 未启用，返回规则引擎降级结果。",
                possible_causes=["请在 .env 中配置 LLM_ENABLED=true、API Key 与模型名"],
                affected_modules=[],
                recommended_checks=["检查 LLM 配置", "可先使用页面中的错误上下文与规则统计结果"],
                owner_departments=["软件控制"],
                severity="unknown",
                confidence=0.2,
            )
            return fallback, {"prompt": prompt}, {"fallback": True, "reason": "disabled", "attempts": 0, "elapsed_seconds": 0.0}

        payload = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": "你是企业级测序仪日志诊断助手，只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }
        return self._analyze_payload(payload, timeout_seconds=timeout_seconds, max_retries=max_retries)

    def request_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        fallback: dict[str, Any] | None = None,
        temperature: float = 0.1,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        if not self.enabled():
            return (
                fallback or {"fallback": True, "reason": "disabled"},
                {"system_prompt": system_prompt, "user_prompt": user_prompt},
                {"fallback": True, "reason": "disabled", "attempts": 0, "elapsed_seconds": 0.0},
            )

        payload = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}

        timeout = int(timeout_seconds or self.settings.llm_timeout_seconds)
        retries = max(1, int(max_retries or self.settings.llm_max_retries))
        started_at = time.monotonic()
        last_error = "unknown"
        last_meta: dict[str, Any] = {}
        last_attempt = 0
        for attempt in range(1, retries + 1):
            last_attempt = attempt
            try:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = self._parse_json_content(content)
                    return parsed, payload, {**data, "attempts": attempt, "elapsed_seconds": round(time.monotonic() - started_at, 3), "timeout_seconds": timeout}
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                retry_after = exc.response.headers.get("Retry-After")
                body = exc.response.text[:500]
                last_meta = {"status_code": status, "retry_after": retry_after, "body": body}
                last_error = f"HTTP {status} 调用失败"
                logger.warning("llm_json_http_error", attempt=attempt, status=status, retry_after=retry_after)
                if attempt < retries:
                    time.sleep(self._retry_wait(attempt, retry_after))
            except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
                last_error = f"返回 JSON 不合法: {exc}"
                last_meta = {"error_type": type(exc).__name__}
                logger.warning("llm_json_parse_failed", attempt=attempt, error=last_error)
                if attempt < retries:
                    time.sleep(self._retry_wait(attempt))
            except httpx.TimeoutException as exc:
                last_error = f"接口超时: {exc}"
                last_meta = {"error_type": type(exc).__name__}
                logger.warning("llm_json_timeout", attempt=attempt, error=last_error)
                if attempt < retries:
                    time.sleep(self._retry_wait(attempt))
            except Exception as exc:
                last_error = str(exc)
                last_meta = {"error_type": type(exc).__name__}
                logger.warning("llm_json_failed", attempt=attempt, error=last_error)
                if attempt < retries:
                    time.sleep(self._retry_wait(attempt))

        return (
            fallback or {"fallback": True, "reason": last_error},
            payload,
            {"error": last_error, "fallback": True, "attempts": last_attempt, "elapsed_seconds": round(time.monotonic() - started_at, 3), "timeout_seconds": timeout, **last_meta},
        )

    def _analyze_payload(
        self,
        payload: dict[str, Any],
        *,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
    ) -> tuple[LLMAnalysisResult, dict[str, Any], dict[str, Any]]:
        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}

        timeout = int(timeout_seconds or self.settings.llm_timeout_seconds)
        retries = max(1, int(max_retries or self.settings.llm_max_retries))
        started_at = time.monotonic()
        last_error = "unknown"
        last_meta: dict[str, Any] = {}
        last_attempt = 0
        for attempt in range(1, retries + 1):
            last_attempt = attempt
            try:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = self._parse_content(content)
                    return parsed, payload, {**data, "attempts": attempt, "elapsed_seconds": round(time.monotonic() - started_at, 3), "timeout_seconds": timeout}
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                retry_after = exc.response.headers.get("Retry-After")
                body = exc.response.text[:500]
                last_meta = {"status_code": status, "retry_after": retry_after, "body": body}
                if status == 429:
                    last_error = "429 Too Many Requests，接口限流"
                    wait_sec = self._retry_wait(attempt, retry_after)
                elif status in (401, 403):
                    last_error = f"{status} 鉴权失败或无权限"
                    wait_sec = 1
                else:
                    last_error = f"HTTP {status} 调用失败"
                    wait_sec = self._retry_wait(attempt, retry_after)
                logger.warning("llm_call_http_error", attempt=attempt, status=status, retry_after=retry_after)
                if attempt < retries:
                    time.sleep(wait_sec)
            except (json.JSONDecodeError, ValidationError, KeyError, IndexError) as exc:
                last_error = f"返回 JSON 不合法: {exc}"
                last_meta = {"error_type": type(exc).__name__}
                logger.warning("llm_call_parse_failed", attempt=attempt, error=last_error)
                if attempt < retries:
                    time.sleep(self._retry_wait(attempt))
            except httpx.TimeoutException as exc:
                last_error = f"接口超时: {exc}"
                last_meta = {"error_type": type(exc).__name__}
                logger.warning("llm_call_timeout", attempt=attempt, error=last_error)
                if attempt < retries:
                    time.sleep(self._retry_wait(attempt))
            except Exception as exc:
                last_error = str(exc)
                last_meta = {"error_type": type(exc).__name__}
                logger.warning("llm_call_failed", attempt=attempt, error=last_error)
                if attempt < retries:
                    time.sleep(self._retry_wait(attempt))

        fallback = self._fallback_result(last_error, last_meta)
        return fallback, payload, {"error": last_error, "fallback": True, "attempts": last_attempt, "elapsed_seconds": round(time.monotonic() - started_at, 3), "timeout_seconds": timeout, **last_meta}

    @staticmethod
    def _retry_wait(attempt: int, retry_after: str | None = None) -> int:
        if retry_after and retry_after.isdigit():
            return min(int(retry_after), 30)
        return min(2 ** attempt, 20)

    def _fallback_result(self, last_error: str, meta: dict[str, Any]) -> LLMAnalysisResult:
        possible = []
        checks = []
        owner = ["软件控制", "测试运维"]
        error_text = str(last_error)
        if "429" in error_text:
            possible = ["LLM 服务限流", "并发请求过多", "账户配额或 QPS 达到上限"]
            checks = ["稍后重试", "降低并发分析次数", "检查火山方舟配额/QPS", "必要时切换备用模型"]
        elif "401" in error_text or "403" in error_text:
            possible = ["API Key 不正确", "模型无权限", "base_url 或 model 配置错误"]
            checks = ["检查 .env 中 LLM_API_KEY", "确认模型名和接入点正确", "检查账号权限"]
        elif "JSON 不合法" in error_text:
            possible = ["模型未严格返回 JSON", "返回内容被截断"]
            checks = ["降低输出复杂度", "缩短上下文", "在 prompt 中强化 JSON 约束"]
        else:
            possible = ["接口超时或网络波动", "返回 JSON 不合法", "鉴权或模型配置异常"]
            checks = ["检查 base_url/api_key/model", "查看服务端日志", "重试分析"]
        return LLMAnalysisResult(
            root_cause_summary=f"LLM 调用失败，已降级。错误: {error_text}",
            possible_causes=possible,
            affected_modules=[],
            recommended_checks=checks,
            owner_departments=owner,
            severity="unknown",
            confidence=0.1,
        )

    def _parse_content(self, content: str) -> LLMAnalysisResult:
        data = self._parse_json_content(content)
        return LLMAnalysisResult.model_validate(data)

    @staticmethod
    def _parse_json_content(content: str) -> dict[str, Any]:
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            content = content.replace("json", "", 1).strip()
        return json.loads(content)
