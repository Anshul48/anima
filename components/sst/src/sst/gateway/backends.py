"""Universal LLM client adapters and concurrency backends for SST execution."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request


class SSTLLMClient:
    """Universal async & sync LLM client supporting OpenAI, DeepSeek, Qwen, Anthropic, Gemini, and Mock."""

    def __init__(
        self,
        cheap_model: str = "qwen-2.5-coder-32b",
        frontier_model: str = "glm-5",
        api_key: str | None = None,
        api_base: str | None = None,
        timeout_seconds: int = 60,
        mock_mode: bool = False,
    ):
        self.cheap_model = cheap_model
        self.frontier_model = frontier_model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or "sk-dummy"
        self.api_base = api_base or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        self.timeout_seconds = timeout_seconds
        self.mock_mode = mock_mode

    def generate(self, prompt: str, temperature: float = 0.7, model: str | None = None) -> str:
        """Synchronously invokes the LLM API (fails closed unless mock_mode=True)."""
        if self.mock_mode:
            return self._mock_response(prompt, temperature)

        if not self.api_key or self.api_key == "sk-dummy":
            raise RuntimeError(
                "No valid API key provided for SSTLLMClient. Set mock_mode=True for testing or configure a valid API key."
            )

        target_model = model or self.cheap_model
        payload = {
            "model": target_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": max(0.0, min(temperature, 2.0)),
        }
        url = f"{self.api_base.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return str(data["choices"][0]["message"]["content"])
        except Exception as exc:
            raise RuntimeError(f"SSTLLMClient request failed to {url}: {exc}") from exc

    async def generate_async(self, prompt: str, temperature: float = 0.7, model: str | None = None) -> str:
        """Asynchronously invokes the LLM API."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.generate, prompt, temperature, model)

    def _mock_response(self, prompt: str, temp: float) -> str:
        """High-signal simulated responses for deterministic unit testing."""
        if "HIGH-ENTROPY" in prompt or "ADHD EXPLORER" in prompt or "DIVERGENT" in prompt or "DIVERGE" in prompt:
            if "AUTORESEARCH" in prompt or "RESEARCH GOAL" in prompt:
                return json.dumps(
                    {
                        "branches": [
                            {
                                "branch_index": 0,
                                "strategy_title": "Adaptive Gradient Momentum Scaling",
                                "hypothesis_or_rationale": "Dynamic learning rate scaling accelerates convergence on non-convex manifolds.",
                                "proposed_changes": "import json\nprint(json.dumps({'metrics': {'accuracy': 0.842, 'loss': 0.28}}))",
                            },
                            {
                                "branch_index": 1,
                                "strategy_title": "Residual Feature Gating",
                                "hypothesis_or_rationale": "Gating intermediate representations filters out high-frequency noise.",
                                "proposed_changes": "import json\nprint(json.dumps({'metrics': {'accuracy': 0.865, 'loss': 0.22}}))",
                            },
                        ]
                    }
                )
            else:  # AUTOBUILD
                return json.dumps(
                    {
                        "branches": [
                            {
                                "branch_index": 0,
                                "strategy_title": "Lock-Free Ring Buffer",
                                "hypothesis_or_rationale": "Atomic pointers minimize cache-line contention.",
                                "proposed_changes": "class RingBuffer:\n    def __init__(self, capacity=1024):\n        self.capacity = capacity\n        self.buf = [None]*capacity\n",
                            },
                            {
                                "branch_index": 1,
                                "strategy_title": "Sharded Mutex Map",
                                "hypothesis_or_rationale": "16 striped partitions reduce lock contention by 90%.",
                                "proposed_changes": "class ShardedMap:\n    def __init__(self):\n        self.shards = [{} for _ in range(16)]\n",
                            },
                        ]
                    }
                )

        elif (
            "MONOTROPIC" in prompt
            or "ASD EXPLOITER" in prompt
            or "REFINE" in prompt
            or "RIGOROUS EXPERIMENT SCIENTIST" in prompt
        ):
            if "AUTORESEARCH" in prompt or "RESEARCH GOAL" in prompt:
                return json.dumps(
                    {
                        "refined_title": "Strict Gated Residual Layer",
                        "refactoring_notes": "Enforced random seed determinism and structured JSON metric emission.",
                        "executable_content": "import json\nprint(json.dumps({'metrics': {'accuracy': 0.865, 'loss': 0.22}}))",
                    }
                )
            else:  # AUTOBUILD
                return json.dumps(
                    {
                        "refined_title": "Type-Safe Ring Buffer",
                        "refactoring_notes": "Added strict bounds checking and memory barriers.",
                        "executable_content": "class RingBuffer:\n    def __init__(self, capacity: int = 1024) -> None:\n        self.capacity = capacity\n        self.buf = [None] * capacity\n",
                    }
                )

        elif "VALUE CRITIC" in prompt or "CRITIQUE" in prompt:
            return json.dumps(
                {
                    "evaluations": [
                        {
                            "node_id": "node_eval",
                            "verdict": "APPROVE",
                            "value_score": 0.92,
                            "architectural_fit": 0.95,
                            "critique": "Mathematically sound, superior loss reduction without parameter inflation.",
                        }
                    ],
                    "best_node_id": "node_eval",
                    "synthesis_opportunity": "Combine momentum scaling with gating.",
                }
            )

        elif "COLIMIT SYNTHESIZER" in prompt or "SYNTHESIZE" in prompt:
            return json.dumps(
                {
                    "synthesized_title": "Unified Gated Adaptive Momentum Architecture",
                    "synthesis_rationale": "Blended momentum scaling with non-linear feature gating.",
                    "executable_content": "import json\nprint(json.dumps({'metrics': {'accuracy': 0.885, 'loss': 0.18}}))",
                }
            )

        return json.dumps({"status": "ok"})
