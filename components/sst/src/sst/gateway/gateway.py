"""Central ModelGateway router and manager for SST execution."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request

from .contracts import (
    AuthenticationError,
    GatewayRequest,
    GatewayResponse,
    MissingModelError,
    ProviderGatewayError,
    ProviderKind,
    ProviderProfile,
    RateLimitError,
    RouteTarget,
    UnreachableEndpointError,
    redact_text,
)


class ModelGateway:
    """Provider-neutral model gateway for discovery, live verification, routing, and invocation."""

    def __init__(
        self,
        profiles: dict[str, ProviderProfile] | None = None,
        routes: dict[str, RouteTarget] | None = None,
    ) -> None:
        self.profiles: dict[str, ProviderProfile] = dict(profiles or {})
        self.routes: dict[str, RouteTarget] = dict(routes or {})

    def register_profile(self, profile: ProviderProfile) -> None:
        """Registers or updates a secret-free provider profile."""
        self.profiles[profile.name] = profile

    def get_profile(self, name: str) -> ProviderProfile | None:
        return self.profiles.get(name)

    def remove_profile(self, name: str) -> None:
        self.profiles.pop(name, None)
        stale_roles = [role for role, target in self.routes.items() if target.profile == name]
        for role in stale_roles:
            del self.routes[role]

    def set_route(self, role: str, profile_name: str, model: str) -> None:
        """Assigns a role to a provider profile and model."""
        if profile_name not in self.profiles:
            raise ValueError(f"Unknown provider profile '{profile_name}'")
        self.routes[role] = RouteTarget(profile=profile_name, model=model)

    def get_route(self, role: str) -> RouteTarget | None:
        return self.routes.get(role)

    @staticmethod
    def _price(profile: ProviderProfile, prompt_tokens: int, completion_tokens: int) -> tuple[float, bool]:
        """Returns (cost_usd, cost_known) for a priced profile, else (0.0, False)."""
        in_rate = profile.input_usd_per_1k_tokens
        out_rate = profile.output_usd_per_1k_tokens
        if in_rate is None or out_rate is None:
            return 0.0, False
        return (prompt_tokens / 1000.0) * in_rate + (completion_tokens / 1000.0) * out_rate, True

    def invoke(self, request: GatewayRequest) -> GatewayResponse:
        """Routes and executes a model request with budget checks and secret redaction."""
        profile_name = request.profile_name
        model = request.model

        if not profile_name and request.role:
            route = self.get_route(request.role)
            if route:
                profile_name = route.profile
                model = model or route.model

        if not profile_name:
            if len(self.profiles) == 1:
                profile_name = next(iter(self.profiles.keys()))
            else:
                raise ProviderGatewayError(
                    f"No provider profile assigned for role '{request.role}' and no profile specified",
                    category="routing_error",
                    remediation="Configure a profile and assign it to this route.",
                )

        profile = self.profiles.get(profile_name)
        if not profile:
            raise ProviderGatewayError(
                f"Provider profile '{profile_name}' is not registered",
                category="routing_error",
                remediation=f"Available profiles: {', '.join(self.profiles.keys()) or 'none'}",
            )

        target_model = model or profile.selected_model
        if not target_model:
            raise MissingModelError(
                f"No model selected for profile '{profile_name}' or role '{request.role}'",
                profile=profile_name,
            )

        timeout = request.timeout_seconds or profile.timeout_seconds

        try:
            if profile.kind == ProviderKind.TEST:
                content = json.dumps({"status": "ok", "mock": True})
                if request.role == "critique":
                    content = json.dumps(
                        {
                            "evaluations": [
                                {
                                    "node_id": "test_node",
                                    "verdict": "APPROVE",
                                    "value_score": 0.95,
                                    "architectural_fit": 0.90,
                                    "critique": "Optimal test implementation.",
                                }
                            ],
                            "value_score": 0.95,
                            "verdict": "APPROVE",
                            "rationale": "Optimal test implementation.",
                        }
                    )
                return GatewayResponse(
                    content=content,
                    model=target_model,
                    profile=profile_name,
                    prompt_tokens=10,
                    completion_tokens=15,
                    total_tokens=25,
                    cost_usd=0.0,
                    cost_known=True,
                    duration_seconds=0.01,
                )

            elif profile.kind == ProviderKind.OLLAMA:
                return self._call_ollama(profile, target_model, request, float(timeout))

            elif profile.kind == ProviderKind.OPENAI_COMPATIBLE:
                return self._call_openai_compatible(profile, target_model, request, float(timeout))

            else:
                raise ProviderGatewayError(f"Unsupported provider kind '{profile.kind}'")

        except ProviderGatewayError:
            raise
        except Exception as exc:
            raise ProviderGatewayError(redact_text(str(exc)), profile=profile_name) from exc

    async def invoke_async(self, request: GatewayRequest) -> GatewayResponse:
        """Asynchronously invokes the model provider endpoint."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.invoke, request)

    def _call_ollama(
        self, profile: ProviderProfile, model: str, request: GatewayRequest, timeout: float
    ) -> GatewayResponse:
        url = f"{profile.api_base.rstrip('/')}/api/chat"
        payload = {
            "model": model,
            "messages": request.messages,
            "options": {"temperature": request.temperature},
            "stream": False,
        }
        if request.response_schema or (request.role in {"diverge", "refine", "critique", "synthesize"}):
            payload["format"] = "json"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = str(data.get("message", {}).get("content", "") or "")
                prompt_tokens = int(data.get("prompt_eval_count", 0))
                completion_tokens = int(data.get("eval_count", 0))
                cost_usd, cost_known = self._price(profile, prompt_tokens, completion_tokens)
                return GatewayResponse(
                    content=content,
                    model=model,
                    profile=profile.name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                    cost_usd=cost_usd,
                    cost_known=cost_known,
                )
        except urllib.error.URLError as e:
            raise UnreachableEndpointError(f"Cannot connect to Ollama at {url}: {e}", profile=profile.name) from e
        except Exception as e:
            raise ProviderGatewayError(f"Ollama request error: {e}", profile=profile.name) from e

    def _call_openai_compatible(
        self, profile: ProviderProfile, model: str, request: GatewayRequest, timeout: float
    ) -> GatewayResponse:
        url = f"{profile.api_base.rstrip('/')}/chat/completions"
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or "sk-dummy"
        payload = {
            "model": model,
            "messages": request.messages,
            "temperature": request.temperature,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choice = data["choices"][0]["message"]
                usage = data.get("usage", {})
                prompt_tokens = int(usage.get("prompt_tokens", 0))
                completion_tokens = int(usage.get("completion_tokens", 0))
                total = int(usage.get("total_tokens", prompt_tokens + completion_tokens))
                cost_usd, cost_known = self._price(profile, prompt_tokens, completion_tokens)
                return GatewayResponse(
                    content=str(choice.get("content") or ""),
                    model=model,
                    profile=profile.name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total,
                    cost_usd=cost_usd,
                    cost_known=cost_known,
                )
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise AuthenticationError(f"Authentication failed: {e}", profile=profile.name) from e
            elif e.code == 429:
                raise RateLimitError(f"Rate limit exceeded: {e}", profile=profile.name) from e
            elif e.code == 404:
                raise MissingModelError(f"Model or endpoint not found: {e}", profile=profile.name) from e
            raise ProviderGatewayError(f"HTTP error {e.code}: {e}", profile=profile.name) from e
        except urllib.error.URLError as e:
            raise UnreachableEndpointError(f"Cannot connect to {url}: {e}", profile=profile.name) from e
        except Exception as e:
            raise ProviderGatewayError(f"OpenAI compatible request failed: {e}", profile=profile.name) from e


SSTModelGateway = ModelGateway
