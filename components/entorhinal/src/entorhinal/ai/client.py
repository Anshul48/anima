"""LiteLLM integration client with pre-egress policy sanitization and fallback routing."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import litellm

from entorhinal.ai.config import AIConfig, EntorhinalConfig
from entorhinal.ai.prompts import INTENT_CLASSIFICATION_PROMPT, SESSION_SYNTHESIS_PROMPT
from entorhinal.policy.engine import PolicyEngine
from entorhinal.schemas.models import DerivedFact, EvidenceRecord, Hypothesis, generate_uuidv7

logger = logging.getLogger(__name__)

# Suppress overly verbose litellm logs
litellm.suppress_debug_info = True


class CloudEgressProhibitedError(RuntimeError):
    """Raised when cloud LLM execution is attempted with allow_cloud=False."""
    pass


class LiteLLMClient:
    """Async AI inference client supporting local models (Ollama/vLLM) and cloud models (via LiteLLM)."""

    def __init__(
        self,
        config: Optional[AIConfig] = None,
        policy_engine: Optional[PolicyEngine] = None,
    ) -> None:
        if config is None:
            root_config = EntorhinalConfig.load_from_dir()
            config = root_config.ai

        self.config = config
        self.policy_engine = policy_engine or PolicyEngine()

    def is_local_model(self, model_name: str, api_base: Optional[str] = None) -> bool:
        """Check if the model identifier refers to a local runtime (Ollama/vLLM/LocalAI)."""
        lower = model_name.lower()
        if (
            lower.startswith("ollama/")
            or lower.startswith("vllm/")
            or lower.startswith("local/")
            or lower.startswith("localai/")
        ):
            return True

        # Explicit cloud providers are never local
        if (
            lower.startswith("gemini/")
            or lower.startswith("anthropic/")
            or lower.startswith("claude")
            or lower.startswith("openai/")
            or lower.startswith("gpt-")
            or lower.startswith("deepseek/")
            or lower.startswith("bedrock/")
            or lower.startswith("groq/")
        ):
            return False

        target_base = api_base or self.config.api_base
        if target_base and ("localhost" in target_base or "127.0.0.1" in target_base):
            return True

        return False

    def _sanitize_messages(self, messages: List[Dict[str, str]], is_cloud: bool) -> List[Dict[str, str]]:
        """Sanitize message contents before sending over the wire if targeting cloud models."""
        if not is_cloud:
            return messages

        sanitized: List[Dict[str, str]] = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                redacted, _ = self.policy_engine.redact_text(content)
                sanitized.append({**msg, "content": redacted})
            else:
                sanitized.append(msg)
        return sanitized

    async def acompletion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Execute async chat completion with automatic fallback and pre-egress privacy redaction."""
        if not self.config.enabled:
            raise RuntimeError("Entorhinal AI tier is currently disabled in configuration.")

        primary = model or self.config.primary_model
        temp = temperature if temperature is not None else self.config.temperature

        # Attempt Primary Model
        try:
            return await self._dispatch_completion(
                model=primary,
                messages=messages,
                api_base=self.config.api_base,
                api_key=self.config.api_key,
                temperature=temp,
                max_tokens=max_tokens,
                response_format=response_format,
                **kwargs,
            )
        except CloudEgressProhibitedError:
            raise
        except Exception as primary_error:
            logger.warning(
                f"Primary model ({primary}) failed: {primary_error}. Attempting fallback..."
            )
            if self.config.fallback_model and self.config.fallback_model != primary:
                return await self._dispatch_completion(
                    model=self.config.fallback_model,
                    messages=messages,
                    api_base=self.config.fallback_api_base,
                    api_key=self.config.fallback_api_key,
                    temperature=temp,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    **kwargs,
                )
            raise primary_error

    async def _dispatch_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Dispatch completion request via LiteLLM with air-gap checks and pre-egress redaction."""
        is_cloud = not self.is_local_model(model)

        if is_cloud and not self.config.allow_cloud:
            raise CloudEgressProhibitedError(
                f"Cloud model '{model}' requested, but allow_cloud=False enforces local-only air-gap."
            )

        sanitized_messages = self._sanitize_messages(messages, is_cloud=is_cloud)

        call_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": sanitized_messages,
            "temperature": temperature,
            "timeout": self.config.timeout_seconds,
            "num_retries": self.config.max_retries,
            **kwargs,
        }

        if api_base:
            call_kwargs["api_base"] = api_base
        if api_key:
            call_kwargs["api_key"] = api_key
        if max_tokens:
            call_kwargs["max_tokens"] = max_tokens
        if response_format:
            call_kwargs["response_format"] = response_format

        res = await litellm.acompletion(**call_kwargs)

        choice = res.choices[0]
        content = choice.message.content if hasattr(choice.message, "content") else ""

        return {
            "content": content,
            "model": model,
            "usage": dict(res.usage) if hasattr(res, "usage") and res.usage else {},
            "raw": res,
        }

    async def infer_task_intent(
        self,
        evidence_records: List[EvidenceRecord],
    ) -> Hypothesis:
        """Infer high-level task intent from evidence records, producing a bounded Hypothesis."""
        lines = []
        for r in evidence_records[-15:]:
            lines.append(
                f"[{r.source_type.value}] app={r.app_identifier} title={r.window_title or r.target_uri or ''}"
            )
        evidence_summary = "\n".join(lines) or "No active evidence records."

        prompt = INTENT_CLASSIFICATION_PROMPT.format(evidence_summary=evidence_summary)
        messages = [{"role": "user", "content": prompt}]

        try:
            res = await self.acompletion(
                messages=messages,
                response_format={"type": "json_object"},
            )
            raw_text = res["content"]
            parsed = json.loads(raw_text)
            intent = parsed.get("task_intent", "Software Development Activity")
            conf = float(parsed.get("confidence", 0.75))
            reason = parsed.get("reasoning_summary", "LLM-assisted intent inference")
        except Exception as e:
            logger.warning(f"Task intent LLM inference error: {e}")
            intent = "General Development Activity"
            conf = 0.50
            reason = f"Heuristic fallback due to model error: {e}"

        from datetime import datetime, timedelta, timezone

        # Invariant: calibrated confidence strictly < 1.0 and is_hypothesis=True
        bounded_conf = max(0.05, min(conf, 0.95))

        return Hypothesis(
            hypothesis_id=generate_uuidv7(),
            proposed_intent=intent,
            confidence_score=bounded_conf,
            candidate_evidence_ids=[r.record_id for r in evidence_records[-5:]],
            uncertainty_reasons=[reason] if reason else [],
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            is_hypothesis=True,
        )

    async def aembedding(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> List[float]:
        """Compute text embedding vector using configured embedding model."""
        embed_model = model or self.config.embedding_model
        is_cloud = not self.is_local_model(embed_model)

        if is_cloud and not self.config.allow_cloud:
            raise CloudEgressProhibitedError(
                f"Cloud embedding model '{embed_model}' requested with allow_cloud=False."
            )

        redacted_text, _ = self.policy_engine.redact_text(text) if is_cloud else (text, [])

        call_kwargs: Dict[str, Any] = {
            "model": embed_model,
            "input": [redacted_text],
            "timeout": self.config.timeout_seconds,
        }
        if self.config.embedding_api_base:
            call_kwargs["api_base"] = self.config.embedding_api_base

        res = await litellm.aembedding(**call_kwargs)
        return res.data[0]["embedding"]
