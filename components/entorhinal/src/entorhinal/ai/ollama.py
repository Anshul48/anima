"""Ollama detector, local model catalog fetcher, and inspector for Windows 11 / Entorhinal."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import httpx


@dataclass
class OllamaModelInfo:
    """Metadata describing a locally available Ollama model."""

    name: str
    model_id: str
    size_bytes: int
    size_gb: float
    param_size: str
    quant: str
    family: str
    context_length: int
    capabilities: List[str] = field(default_factory=list)

    @property
    def display_label(self) -> str:
        """Render a rich, informative label for interactive CLI selection menus."""
        caps_str = f" [{', '.join(self.capabilities)}]" if self.capabilities else ""
        specs: List[str] = []
        if self.param_size:
            specs.append(self.param_size)
        if self.quant:
            specs.append(self.quant)
        if self.size_gb > 0:
            specs.append(f"{self.size_gb:.1f} GB")

        spec_str = f" ({', '.join(specs)})" if specs else ""
        return f"{self.name}{spec_str}{caps_str}"


class OllamaDetector:
    """Client for discovering, querying, and testing local Ollama runtime instances."""

    DEFAULT_HOSTS = [
        "http://localhost:11434",
        "http://127.0.0.1:11434",
    ]

    def __init__(self, timeout_seconds: float = 2.0) -> None:
        self.timeout_seconds = timeout_seconds

    async def detect_running_host(self, candidate_hosts: Optional[List[str]] = None) -> Optional[str]:
        """Probe candidate URLs asynchronously to find an active Ollama instance."""
        hosts = candidate_hosts or self.DEFAULT_HOSTS
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            for host in hosts:
                clean_host = host.rstrip("/")
                try:
                    res = await client.get(f"{clean_host}/api/tags")
                    if res.status_code == 200:
                        return clean_host
                except Exception:
                    continue
        return None

    def detect_running_host_sync(self, candidate_hosts: Optional[List[str]] = None) -> Optional[str]:
        """Synchronous probe for active Ollama host."""
        hosts = candidate_hosts or self.DEFAULT_HOSTS
        with httpx.Client(timeout=self.timeout_seconds) as client:
            for host in hosts:
                clean_host = host.rstrip("/")
                try:
                    res = client.get(f"{clean_host}/api/tags")
                    if res.status_code == 200:
                        return clean_host
                except Exception:
                    continue
        return None

    async def list_models(self, host: Optional[str] = None) -> List[OllamaModelInfo]:
        """Fetch and parse installed models from Ollama's /api/tags endpoint."""
        target_host = host or await self.detect_running_host()
        if not target_host:
            return []

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            try:
                res = await client.get(f"{target_host.rstrip('/')}/api/tags")
                if res.status_code != 200:
                    return []
                data = res.json()
            except Exception:
                return []

        return self._parse_models_json(data)

    def list_models_sync(self, host: Optional[str] = None) -> List[OllamaModelInfo]:
        """Synchronous retrieval of installed Ollama models."""
        target_host = host or self.detect_running_host_sync()
        if not target_host:
            return []

        with httpx.Client(timeout=self.timeout_seconds) as client:
            try:
                res = client.get(f"{target_host.rstrip('/')}/api/tags")
                if res.status_code != 200:
                    return []
                data = res.json()
            except Exception:
                return []

        return self._parse_models_json(data)

    def _parse_models_json(self, data: Dict[str, Any]) -> List[OllamaModelInfo]:
        """Parse raw /api/tags JSON output into structured OllamaModelInfo records."""
        models: List[OllamaModelInfo] = []
        raw_list = data.get("models", [])

        for item in raw_list:
            name = item.get("name") or item.get("model") or "unknown"
            size_bytes = int(item.get("size", 0))
            size_gb = size_bytes / (1024 ** 3)
            details = item.get("details", {})
            param_size = details.get("parameter_size", "")
            quant = details.get("quantization_level", "")
            family = details.get("family", "")
            ctx_len = details.get("context_length", 0)
            capabilities = item.get("capabilities", [])

            models.append(
                OllamaModelInfo(
                    name=name,
                    model_id=f"ollama/{name}",
                    size_bytes=size_bytes,
                    size_gb=size_gb,
                    param_size=param_size,
                    quant=quant,
                    family=family,
                    context_length=ctx_len,
                    capabilities=capabilities,
                )
            )

        return models

    async def ping_model(self, model_name: str, host: Optional[str] = None) -> Tuple[bool, str]:
        """Perform a low-latency test completion to verify model readiness."""
        target_host = host or await self.detect_running_host()
        if not target_host:
            return False, "Ollama daemon not reachable at localhost:11434"

        clean_name = model_name.removeprefix("ollama/")
        payload = {
            "model": clean_name,
            "prompt": "Respond with 'READY' if operational.",
            "stream": False,
            "options": {"num_predict": 5},
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.post(f"{target_host.rstrip('/')}/api/generate", json=payload)
                if res.status_code == 200:
                    body = res.json()
                    response_text = body.get("response", "").strip()
                    return True, f"Model responded ({len(response_text)} chars): {response_text[:30]}"
                else:
                    return False, f"HTTP Error {res.status_code}: {res.text[:100]}"
            except Exception as e:
                return False, f"Connection failure: {str(e)}"
