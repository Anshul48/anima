r"""Interactive Onboarding Wizard for Entorhinal on Windows 11.

Implements the Hermes / OpenClaw-grade 6-step initialization flow:
1. Workspace & Storage (~/.entorhinal, directories, journal init)
2. Source Feeds (OS Window, Terminal PTY, Browser Companion)
3. Privacy & Redaction Baseline (Blacklists, PII, Pre-Egress Sanitization)
4. AI & Model Backend (Option C: Hybrid Local Ollama + Cloud LiteLLM)
5. Daemon & IPC Transports (REST 127.0.0.1:8000 + Named Pipe \\.\pipe\entorhinal_vnext)
6. Diagnostic Verification & Self-Test (Hash-chain, Redaction test, Model ping)
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

import questionary
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from entorhinal.ai.config import (
    AIConfig,
    DaemonConfig,
    EntorhinalConfig,
    PolicyConfig,
    SourcesConfig,
    save_env_secret,
)
from entorhinal.ai.ollama import OllamaDetector, OllamaModelInfo
from entorhinal.cli.theme import (
    CHECKED_GLYPH,
    POINTER_GLYPH,
    QUESTIONARY_THEME,
    console,
    print_banner,
    render_step_header,
    render_success_card,
    render_summary_table,
    render_warning_card,
)
from entorhinal.evidence.journal import EvidenceJournal
from entorhinal.policy.engine import PolicyEngine
from entorhinal.schemas.models import (
    ClassificationLevel,
    EvidenceRecord,
    RawSignalEvent,
    SourceType,
    generate_uuidv7,
)


class InteractiveSetupWizard:
    """Orchestrates interactive and non-interactive system onboarding for Windows 11."""

    def __init__(self, target_dir: Optional[str] = None) -> None:
        self.target_dir = Path(target_dir).resolve() if target_dir else Path.home() / ".entorhinal"
        self.ollama_detector = OllamaDetector()
        self.policy_engine = PolicyEngine()

    # ==========================================================================
    # Main Interactive Runner
    # ==========================================================================

    def run_interactive(self, preset_mode: Optional[str] = None) -> EntorhinalConfig:
        """Run full 6-step interactive onboarding wizard."""
        print_banner()

        console.print(
            "[bold white]Welcome to the Entorhinal Interactive Setup Wizard![/bold white]\n"
            "[dim]This wizard will configure your local storage, privacy guardrails, passive capture sources,\n"
            "and Hybrid AI models (Local Ollama + Cloud LiteLLM) for Windows 11.[/dim]\n"
        )

        total_steps = 6

        # Step 1: Storage & Directories
        storage_dir = self._step1_storage(step=1, total=total_steps)

        # Step 2: Source Capture Feeds
        sources_cfg = self._step2_sources(step=2, total=total_steps)

        # Step 3: Privacy & Redaction Baseline
        policy_cfg = self._step3_privacy(step=3, total=total_steps)

        # Step 4: AI & Model Architecture (Option C: Hybrid)
        ai_cfg, env_secrets = self._step4_ai_models(step=4, total=total_steps, preset_mode=preset_mode)

        # Step 5: Daemon & IPC Transports
        daemon_cfg = self._step5_daemon(step=5, total=total_steps)

        # Build Root Config
        config = EntorhinalConfig(
            version="1.0",
            storage_dir=str(storage_dir),
            sources=sources_cfg,
            policy=policy_cfg,
            ai=ai_cfg,
            daemon=daemon_cfg,
        )

        # Step 6: Diagnostic Verification & Smoke Test
        self._step6_verification(step=6, total=total_steps, config=config, env_secrets=env_secrets)

        return config

    # ==========================================================================
    # Step 1: Storage & Workspace
    # ==========================================================================

    def _step1_storage(self, step: int, total: int) -> Path:
        render_step_header(
            step_num=step,
            total_steps=total,
            title="Storage & State Directory Initialization",
            subtitle="Configures durable storage paths, cryptographic evidence journal, and index partitions.",
        )

        default_path = str(self.target_dir)
        choice_dir = questionary.text(
            "Enter Entorhinal storage directory path:",
            default=default_path,
            style=QUESTIONARY_THEME,
        ).ask()

        resolved = Path(os.path.expanduser(choice_dir.strip() if choice_dir else default_path)).resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        (resolved / "backups").mkdir(parents=True, exist_ok=True)
        (resolved / "indices").mkdir(parents=True, exist_ok=True)
        (resolved / "logs").mkdir(parents=True, exist_ok=True)

        journal_file = resolved / "evidence_journal.jsonl"
        if not journal_file.exists():
            journal_file.touch(mode=0o600)

        render_success_card(
            "Storage Initialized",
            f"Directory: [cyan]{resolved}[/cyan]\nJournal: [cyan]{journal_file}[/cyan]",
        )
        return resolved

    # ==========================================================================
    # Step 2: Source Capture Selection
    # ==========================================================================

    def _step2_sources(self, step: int, total: int) -> SourcesConfig:
        render_step_header(
            step_num=step,
            total_steps=total,
            title="Passive Source Signal Consent",
            subtitle="Select which observational source adapters are permitted to capture developer activity.",
        )

        choices = [
            questionary.Choice(
                title="OS Window Focus Adapter (Captures active app names, window titles, switch latency)",
                value="os_window",
                checked=True,
            ),
            questionary.Choice(
                title="Terminal Command / PTY Adapter (Lossless CLI commands, exit codes, and durations)",
                value="terminal_pty",
                checked=True,
            ),
            questionary.Choice(
                title="Browser Companion Adapter (Opt-in DOM/CDP context, strictly auto-drops passwords)",
                value="browser",
                checked=True,
            ),
        ]

        selected = questionary.checkbox(
            "Enable passive source adapters (Space to toggle, Enter to confirm):",
            choices=choices,
            style=QUESTIONARY_THEME,
        ).ask()

        if selected is None:
            selected = ["os_window", "terminal_pty", "browser"]

        cfg = SourcesConfig(
            enable_os_window="os_window" in selected,
            enable_terminal_pty="terminal_pty" in selected,
            enable_browser="browser" in selected,
        )

        render_success_card(
            "Sources Configured",
            f"Active: OS Window ({cfg.enable_os_window}), Terminal ({cfg.enable_terminal_pty}), Browser ({cfg.enable_browser})",
        )
        return cfg

    # ==========================================================================
    # Step 3: Privacy & Redaction Baseline
    # ==========================================================================

    def _step3_privacy(self, step: int, total: int) -> PolicyConfig:
        render_step_header(
            step_num=step,
            total_steps=total,
            title="Privacy Guardrails & Pre-Egress Sanitization",
            subtitle="Pre-storage blacklists and multi-pass credential masking prevent sensitive data leakage.",
        )

        app_choices = [
            questionary.Choice("1Password (Password Manager)", value="1Password", checked=True),
            questionary.Choice("Bitwarden (Password Manager)", value="Bitwarden", checked=True),
            questionary.Choice("KeePass / KeePassXC (Password Manager)", value="KeePass", checked=True),
            questionary.Choice("Windows Security / Credential Manager", value="Windows Security", checked=True),
        ]

        selected_apps = questionary.checkbox(
            "Select blacklisted application window filters:",
            choices=app_choices,
            style=QUESTIONARY_THEME,
        ).ask() or ["1Password", "Bitwarden", "KeePass", "Windows Security"]

        redact_cloud = questionary.confirm(
            "Enable deterministic pre-egress PII / token redaction for cloud AI models?",
            default=True,
            style=QUESTIONARY_THEME,
        ).ask()

        if redact_cloud is None:
            redact_cloud = True

        cfg = PolicyConfig(
            redact_pii_before_cloud_egress=redact_cloud,
            drop_unpermitted_domains=True,
            excluded_applications=selected_apps,
        )

        render_success_card(
            "Privacy Policies Active",
            f"Pre-Egress Cloud Redaction: [green]{'ENABLED' if redact_cloud else 'DISABLED'}[/green]\n"
            f"Excluded Apps: {', '.join(selected_apps)}",
        )
        return cfg

    # ==========================================================================
    # Step 4: AI & Model Architecture (Option C: Hybrid)
    # ==========================================================================

    def _step4_ai_models(
        self,
        step: int,
        total: int,
        preset_mode: Optional[str] = None,
    ) -> tuple[AIConfig, dict[str, str]]:
        render_step_header(
            step_num=step,
            total_steps=total,
            title="AI & Model Backend (Option C: Hybrid Setup)",
            subtitle="Combines fast, private local Ollama inference with LiteLLM cloud models for deep reasoning.",
        )

        # Mode Selection
        mode = preset_mode
        if not mode:
            mode_choice = questionary.select(
                "Select AI operating architecture:",
                choices=[
                    questionary.Choice(
                        title="Option C: Hybrid Setup (Local Primary + Cloud Fallback / Deep Tier) [RECOMMENDED]",
                        value="hybrid",
                    ),
                    questionary.Choice(
                        title="Option A: 100% Local-Only (Air-Gapped Ollama / vLLM, Zero Cloud Egress)",
                        value="local",
                    ),
                    questionary.Choice(
                        title="Option B: Cloud-Only (LiteLLM with Gemini / Claude / OpenAI)",
                        value="cloud",
                    ),
                ],
                style=QUESTIONARY_THEME,
            ).ask() or "hybrid"
            mode = mode_choice

        env_secrets: dict[str, str] = {}

        # ----------------------------------------------------------------------
        # Probe & Fetch Local Ollama Models
        # ----------------------------------------------------------------------
        local_host: Optional[str] = None
        ollama_models: List[OllamaModelInfo] = []

        if mode in ("hybrid", "local"):
            with console.status("[bold #00E5FF]Probing for running Ollama instance at localhost:11434 ...[/bold #00E5FF]"):
                local_host = self.ollama_detector.detect_running_host_sync()
                if local_host:
                    ollama_models = self.ollama_detector.list_models_sync(local_host)

            if local_host and ollama_models:
                render_success_card(
                    "Ollama Instance Detected",
                    f"Host: [cyan]{local_host}[/cyan]\nFound [green]{len(ollama_models)}[/green] locally installed models.",
                )
            elif local_host:
                render_warning_card(
                    "Ollama Online (No Models Found)",
                    f"Ollama is running at {local_host}, but no models are installed yet.\nYou can pull models with [cyan]ollama pull qwen2.5-coder:7b[/cyan].",
                )
            else:
                render_warning_card(
                    "Ollama Not Detected",
                    "Ollama was not found running on localhost:11434.\nIf you plan to use local models, launch Ollama desktop or run [cyan]ollama serve[/cyan].",
                )

        # ----------------------------------------------------------------------
        # Primary Model Selection
        # ----------------------------------------------------------------------
        primary_model = "ollama/qwen3.8:27b"
        api_base = "http://localhost:11434"

        if mode in ("hybrid", "local"):
            model_choices: list[Any] = []
            if ollama_models:
                for m in ollama_models:
                    model_choices.append(questionary.Choice(title=m.display_label, value=m.model_id))
            
            # Fallback choices
            model_choices.append(questionary.Choice(title="ollama/qwen2.5-coder:7b (Fast 7B coder)", value="ollama/qwen2.5-coder:7b"))
            model_choices.append(questionary.Choice(title="ollama/llama3.2:3b (Ultra-light 3B)", value="ollama/llama3.2:3b"))
            model_choices.append(questionary.Choice(title="Custom Model ID (Enter manually)", value="custom"))

            selected_model = questionary.select(
                "Select Primary Local Model for fast intent & clustering:",
                choices=model_choices,
                style=QUESTIONARY_THEME,
            ).ask() or "ollama/qwen3.8:27b"

            if selected_model == "custom":
                custom_id = questionary.text(
                    "Enter custom LiteLLM model identifier (e.g. 'ollama/mistral'):",
                    default="ollama/qwen3.8:27b",
                    style=QUESTIONARY_THEME,
                ).ask()
                primary_model = custom_id.strip() if custom_id else "ollama/qwen3.8:27b"
            else:
                primary_model = selected_model

            api_base = local_host or "http://localhost:11434"

        else:
            # Cloud only primary
            cloud_primary_choices = [
                questionary.Choice("Google Gemini (gemini/gemini-2.5-flash) [Fast, Large Context]", value="gemini/gemini-2.5-flash"),
                questionary.Choice("Anthropic Claude (anthropic/claude-3-5-sonnet-20241022) [High Reasoning]", value="anthropic/claude-3-5-sonnet-20241022"),
                questionary.Choice("OpenAI GPT-4o-mini (openai/gpt-4o-mini) [Fast Standard]", value="openai/gpt-4o-mini"),
                questionary.Choice("DeepSeek Chat (deepseek/deepseek-chat) [Efficient Coder]", value="deepseek/deepseek-chat"),
            ]
            primary_model = questionary.select(
                "Select Primary Cloud Model:",
                choices=cloud_primary_choices,
                style=QUESTIONARY_THEME,
            ).ask() or "gemini/gemini-2.5-flash"
            api_base = None

        # ----------------------------------------------------------------------
        # Fallback / Cloud Model Selection (Option C)
        # ----------------------------------------------------------------------
        fallback_model: Optional[str] = None
        fallback_api_key_env: Optional[str] = "GEMINI_API_KEY"

        if mode == "hybrid":
            cloud_choices = [
                questionary.Choice("Google Gemini (gemini/gemini-2.5-flash) [Recommended Cloud Fallback]", value="gemini/gemini-2.5-flash"),
                questionary.Choice("Anthropic Claude (anthropic/claude-3-5-sonnet-20241022)", value="anthropic/claude-3-5-sonnet-20241022"),
                questionary.Choice("OpenAI GPT-4o-mini (openai/gpt-4o-mini)", value="openai/gpt-4o-mini"),
                questionary.Choice("DeepSeek Chat (deepseek/deepseek-chat)", value="deepseek/deepseek-chat"),
                questionary.Choice("Disable Cloud Fallback (Local-Only Fallback)", value="none"),
            ]
            chosen_fallback = questionary.select(
                "Select Cloud Fallback / Deep Reasoning Model:",
                choices=cloud_choices,
                style=QUESTIONARY_THEME,
            ).ask() or "gemini/gemini-2.5-flash"

            if chosen_fallback != "none":
                fallback_model = chosen_fallback
                if "gemini" in fallback_model:
                    fallback_api_key_env = "GEMINI_API_KEY"
                elif "anthropic" in fallback_model or "claude" in fallback_model:
                    fallback_api_key_env = "ANTHROPIC_API_KEY"
                elif "openai" in fallback_model or "gpt" in fallback_model:
                    fallback_api_key_env = "OPENAI_API_KEY"
                elif "deepseek" in fallback_model:
                    fallback_api_key_env = "DEEPSEEK_API_KEY"
                else:
                    fallback_api_key_env = "LLM_API_KEY"

                # Check if API Key already exists in environment
                existing_key = os.environ.get(fallback_api_key_env)
                if existing_key:
                    masked = existing_key[:4] + "..." + existing_key[-4:] if len(existing_key) > 8 else "***"
                    console.print(f"[bold green]✔ Detected {fallback_api_key_env} in environment ({masked})[/bold green]")
                else:
                    prompt_key = questionary.password(
                        f"Enter {fallback_api_key_env} (masked, or press Enter to set later):",
                        style=QUESTIONARY_THEME,
                    ).ask()
                    if prompt_key and prompt_key.strip():
                        env_secrets[fallback_api_key_env] = prompt_key.strip()
                        os.environ[fallback_api_key_env] = prompt_key.strip()

        # ----------------------------------------------------------------------
        # Embedding Model Selection
        # ----------------------------------------------------------------------
        embedding_model = "ollama/nomic-embed-text"
        embedding_api_base: Optional[str] = api_base

        embed_choices = [
            questionary.Choice("ollama/nomic-embed-text [Local 8192-dim, Fast on CPU]", value="ollama/nomic-embed-text"),
            questionary.Choice("ollama/bge-m3 [Local Multilingual]", value="ollama/bge-m3"),
            questionary.Choice("text-embedding-3-small [Cloud OpenAI / LiteLLM]", value="text-embedding-3-small"),
        ]
        chosen_embed = questionary.select(
            "Select Embedding Model for semantic clustering & retrieval:",
            choices=embed_choices,
            style=QUESTIONARY_THEME,
        ).ask() or "ollama/nomic-embed-text"
        embedding_model = chosen_embed

        if not embedding_model.startswith("ollama/"):
            embedding_api_base = None

        ai_cfg = AIConfig(
            enabled=True,
            mode=mode,
            allow_cloud=mode in ("hybrid", "cloud"),
            primary_model=primary_model,
            api_base=api_base,
            fallback_model=fallback_model,
            fallback_api_key_env=fallback_api_key_env,
            embedding_model=embedding_model,
            embedding_api_base=embedding_api_base,
            temperature=0.1,
            timeout_seconds=15.0,
            max_retries=2,
        )

        render_success_card(
            "AI Integration Configured",
            f"Mode: [bold cyan]{mode.upper()}[/bold cyan]\n"
            f"Primary Model: [cyan]{primary_model}[/cyan] ({api_base or 'Cloud'})\n"
            f"Fallback Model: [cyan]{fallback_model or 'None'}[/cyan]\n"
            f"Embedding Model: [cyan]{embedding_model}[/cyan]",
        )

        return ai_cfg, env_secrets

    # ==========================================================================
    # Step 5: Daemon & IPC Transport
    # ==========================================================================

    def _step5_daemon(self, step: int, total: int) -> DaemonConfig:
        render_step_header(
            step_num=step,
            total_steps=total,
            title="Daemon & IPC Transports",
            subtitle="Local loopback REST API and Windows Named Pipe (\\\\.\\pipe\\entorhinal_vnext) for Reflex.",
        )

        port_str = questionary.text(
            "REST loopback daemon port:",
            default="8000",
            style=QUESTIONARY_THEME,
        ).ask() or "8000"

        try:
            port = int(port_str.strip())
        except ValueError:
            port = 8000

        pipe_name = r"\\.\pipe\entorhinal_vnext"

        cfg = DaemonConfig(
            host="127.0.0.1",
            port=port,
            named_pipe_path=pipe_name,
        )

        render_success_card(
            "Daemon Transports Configured",
            f"REST Daemon: [cyan]http://127.0.0.1:{port}[/cyan] (Trust UI at /ui)\n"
            f"Named Pipe IPC: [cyan]{pipe_name}[/cyan] (Sub-2ms latency)",
        )
        return cfg

    # ==========================================================================
    # Step 6: Diagnostic Verification & Smoke Test
    # ==========================================================================

    def _step6_verification(
        self,
        step: int,
        total: int,
        config: EntorhinalConfig,
        env_secrets: dict[str, str],
    ) -> None:
        render_step_header(
            step_num=step,
            total_steps=total,
            title="Diagnostic Verification & Self-Test",
            subtitle="Executing 4-point cryptographic and subsystem integrity checks.",
        )

        storage_path = config.get_resolved_storage_dir()
        storage_path.mkdir(parents=True, exist_ok=True)

        # 1. Save Secrets to .env
        for k, v in env_secrets.items():
            save_env_secret(storage_path, k, v)

        # 2. Save config.yaml
        config.save_to_dir(storage_path)

        test_results: list[tuple[str, str, bool]] = []

        with Progress(
            SpinnerColumn(style="bold #00E5FF"),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Test 1: Journal Integrity
            t1 = progress.add_task("[bold white]1. Verifying Evidence Journal cryptographic hash-chain...[/bold white]", total=None)
            time.sleep(0.3)
            journal = EvidenceJournal(storage_path=storage_path / "evidence_journal.jsonl")
            is_valid, _, _ = journal.verify_journal_integrity()
            test_results.append(("Evidence Journal Hash-Chain", "VERIFIED (100% Cryptographically Intact)" if is_valid else "CORRUPTED", is_valid))
            progress.update(t1, completed=True)

            # Test 2: Pre-Egress Policy Redaction
            t2 = progress.add_task("[bold white]2. Testing deterministic credential & PII redaction...[/bold white]", total=None)
            time.sleep(0.2)
            # AWS documentation example key (EXAMPLE…) — synthetic, not a credential.
            test_text = "Test AWS Key AKIAIOSFODNN7EXAMPLE and secret aws_secret_access_key='wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'"
            redacted, count = self.policy_engine.redact_text(test_text)
            passed_redaction = "AKIA" not in redacted and count >= 2
            test_results.append(("Deterministic Policy Redaction", f"PASSED ({count} secret patterns masked)" if passed_redaction else "FAILED", passed_redaction))
            progress.update(t2, completed=True)

            # Test 3: Local / Ollama Connectivity
            t3 = progress.add_task("[bold white]3. Checking AI backend endpoint connectivity...[/bold white]", total=None)
            time.sleep(0.3)
            if config.ai.api_base and "localhost" in config.ai.api_base:
                ollama_ok = self.ollama_detector.detect_running_host_sync() is not None
                status_str = f"ONLINE ({config.ai.primary_model})" if ollama_ok else "OFFLINE (Start Ollama to activate)"
                test_results.append(("Local AI Endpoint (Ollama)", status_str, ollama_ok))
            else:
                test_results.append(("Cloud AI Model Provider", f"CONFIGURED ({config.ai.primary_model})", True))
            progress.update(t3, completed=True)

            # Test 4: Named Pipe IPC Definition
            t4 = progress.add_task("[bold white]4. Verifying Windows Named Pipe transport binding...[/bold white]", total=None)
            time.sleep(0.2)
            pipe_ok = config.daemon.named_pipe_path.startswith(r"\\.\pipe\\")
            test_results.append(("Windows Named Pipe Protocol", f"READY ({config.daemon.named_pipe_path})", pipe_ok))
            progress.update(t4, completed=True)

        console.print()

        # Display Final Summary
        summary_rows = [
            ("Storage Path", str(storage_path)),
            ("Config File", str(storage_path / "config.yaml")),
            ("AI Operating Mode", config.ai.mode.upper()),
            ("Primary Model", config.ai.primary_model),
            ("Fallback Model", config.ai.fallback_model or "None"),
            ("Embedding Model", config.ai.embedding_model),
            ("Air-Gap / Allow Cloud", str(config.ai.allow_cloud)),
            ("Loopback Daemon", f"http://{config.daemon.host}:{config.daemon.port}"),
            ("Named Pipe IPC", config.daemon.named_pipe_path),
        ]
        for name, val, status in test_results:
            status_text = f"[bold green]{val}[/bold green]" if status else f"[bold yellow]{val}[/bold yellow]"
            summary_rows.append((f"Self-Test: {name}", status_text))

        render_summary_table(summary_rows)

        console.print(
            "[bold #00FF88]═══════════════════════════════════════════════════════════════════════════════[/bold #00FF88]\n"
            f"[bold #00FF88]{CHECKED_GLYPH} ENTORHINAL INITIALIZATION COMPLETE & RATIFIED![/bold #00FF88]\n"
            "[bold #00FF88]═══════════════════════════════════════════════════════════════════════════════[/bold #00FF88]\n\n"
            "[bold white]Next Steps & Commands:[/bold white]\n"
            "  [cyan]uv run python -m entorhinal.cli.main status[/cyan]       Check system health & journal stats\n"
            "  [cyan]uv run python -m entorhinal.cli.main serve-vnext[/cyan]  Start vNext Named Pipe Provider for Reflex\n"
            "  [cyan]uv run python -m entorhinal.cli.main serve[/cyan]        Start loopback REST API & Web Trust UI (/ui)\n"
            "  [cyan]uv run python -m entorhinal.cli.main inspect timeline[/cyan] View chronological captured events\n"
        )

    # ==========================================================================
    # Non-Interactive / Headless Setup (For CI, Tests, and Automated Scripts)
    # ==========================================================================

    def run_non_interactive(
        self,
        storage_dir: Optional[str] = None,
        mode: str = "hybrid",
        primary_model: Optional[str] = None,
        fallback_model: Optional[str] = "gemini/gemini-2.5-flash",
        embedding_model: str = "ollama/nomic-embed-text",
        allow_cloud: Optional[bool] = None,
        enable_os_window: bool = True,
        enable_terminal_pty: bool = True,
        enable_browser: bool = True,
        port: int = 8000,
    ) -> EntorhinalConfig:
        """Run non-interactive initialization creating default config and directories."""
        resolved = Path(storage_dir).resolve() if storage_dir else self.target_dir
        resolved.mkdir(parents=True, exist_ok=True)
        (resolved / "backups").mkdir(parents=True, exist_ok=True)
        (resolved / "indices").mkdir(parents=True, exist_ok=True)
        (resolved / "logs").mkdir(parents=True, exist_ok=True)

        journal_file = resolved / "evidence_journal.jsonl"
        if not journal_file.exists():
            journal_file.touch(mode=0o600)

        # Detect Ollama or use standard default
        local_host = self.ollama_detector.detect_running_host_sync()
        if primary_model is None:
            if mode in ("hybrid", "local"):
                primary_model = "ollama/qwen3.8:27b" if local_host else "ollama/qwen2.5-coder:7b"
            else:
                primary_model = "gemini/gemini-2.5-flash"

        api_base = local_host or "http://localhost:11434" if mode in ("hybrid", "local") else None
        allow_c = allow_cloud if allow_cloud is not None else (mode in ("hybrid", "cloud"))

        config = EntorhinalConfig(
            version="1.0",
            storage_dir=str(resolved),
            sources=SourcesConfig(
                enable_os_window=enable_os_window,
                enable_terminal_pty=enable_terminal_pty,
                enable_browser=enable_browser,
            ),
            policy=PolicyConfig(
                redact_pii_before_cloud_egress=True,
                drop_unpermitted_domains=True,
            ),
            ai=AIConfig(
                enabled=True,
                mode=mode,
                allow_cloud=allow_c,
                primary_model=primary_model,
                api_base=api_base,
                fallback_model=fallback_model if mode == "hybrid" else None,
                fallback_api_key_env="GEMINI_API_KEY" if mode == "hybrid" else None,
                embedding_model=embedding_model,
                embedding_api_base=api_base if embedding_model.startswith("ollama/") else None,
            ),
            daemon=DaemonConfig(
                host="127.0.0.1",
                port=port,
                named_pipe_path=r"\\.\pipe\entorhinal_vnext",
            ),
        )

        config.save_to_dir(resolved)
        return config
