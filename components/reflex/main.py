"""Reflex Jarvis: Autonomous Computer-Use and Motor Learning Console.

Interactive entry point and CLI for controlling desktop windows,
executing System 1 motor skills, deliberating with System 2 (Holo 3.1 9B Ollama),
and driving System 2 -> System 1 habit transference.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time

from reflex.agent.jarvis import JarvisAgent, JarvisExecutionResult
from reflex.cognition.system2.providers import HoloOllamaProvider, OllamaLLMClient
from reflex.execution.native.window_manager import (
    DEFAULT_APP_KEY,
    MockWindowManagerSubstrate,
    NativeWindowManager,
)

BANNER = r"""
================================================================================
   ____       __ _             _             _       
  |  _ \ ___ / _| | _____  __ | | __ _ _ ____   _(_)___  
  | |_) / _ \ |_| |/ _ \ \/ / | |/ _` | '__\ \ / / / __| 
  |  _ <  __/  _| |  __/>  <  | | (_| | |   \ V /| \__ \ 
  |_| \_\___|_| |_|\___/_/\_\ |_|\__,_|_|    \_/ |_|___/ 
                                                          
  AUTONOMOUS COMPUTER USE & MOTOR LEARNING ENGINE
================================================================================
  * System 1: Invariant Affordance Motor Skills (< 5ms Fast-Path)
  * System 2: Local Holo 3.1 9B Ollama / Deliberative Planning
  * Desktop: Native Window Manager (Deterministic Discovery & Tiling)
  * Verification: Closed-Loop Efference Copy & Surprise Circuit Breaker
================================================================================
"""


def print_banner() -> None:
    print(BANNER)
    print("Type a natural language instruction or built-in command:")
    print(f"  Examples: 'open {DEFAULT_APP_KEY}', 'tile {DEFAULT_APP_KEY}s horizontally', 'list windows'")
    print("  Built-ins: 'status', 'skills', 'windows', 'demo', 'help', 'exit'")
    print("-" * 80)


def print_result(res: JarvisExecutionResult) -> None:
    status_symbol = "[OK]" if res.success else "[FAILED]"
    color_prefix = "\033[92m" if res.success else "\033[91m"
    color_suffix = "\033[0m"

    print(f"\n{color_prefix}{status_symbol}{color_suffix} Substrate: \033[1m{res.substrate}\033[0m | Latency: {res.latency_ms:.2f}ms")
    print(f"  Actions Executed: {res.actions_executed}")
    if res.circuit_breaker_tripped:
        print("  \033[93m[!] Surprise Circuit Breaker TRIPPED (PE > tau)\033[0m")
    if res.transferred_to_system1:
        print(f"  \033[96m[+] System 2 -> System 1 Transferred: MotorSkill '{res.new_skill_id}' consolidated\033[0m")
    print(f"\n  {res.output}\n")


async def run_interactive_repl(agent: JarvisAgent) -> None:
    """Runs interactive command REPL."""
    print_banner()

    while True:
        try:
            line = input("jarvis> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting Jarvis console.")
            break

        if not line:
            continue

        cmd_lower = line.lower()
        if cmd_lower in ("exit", "quit", "q"):
            print("Goodbye!")
            break

        if cmd_lower == "help":
            print("\nAvailable Commands:")
            print("  Window Management:")
            print(f"    open {DEFAULT_APP_KEY}                  - Spawns a new {DEFAULT_APP_KEY.capitalize()} window")
            print(f"    tile {DEFAULT_APP_KEY}s [grid|horizontal|vertical] - Tiles windows instantly")
            print("    list windows                  - Shows all open desktop windows")
            print("    focus <title>                 - Brings window to foreground")
            print("    minimize / maximize <title>   - Minimizes or maximizes window")
            print("    close <title>                 - Closes specified window")
            print("  Cognitive Engine:")
            print("    type '<text>' into <input>    - Plans or re-grounds typing action")
            print("    click <button>                - Plans or re-grounds click action")
            print("    status                        - Shows system status")
            print("    skills                        - Lists consolidated System 1 skills")
            print("    demo                          - Runs complete autonomous demonstration")
            print("    exit                          - Exits console\n")
            continue

        if cmd_lower == "status":
            st = agent.get_status()
            print("\n--- System Status ---")
            print(f"  Window Manager: {st['window_manager']['active_windows']} active windows (Mock: {st['window_manager']['is_mock']})")
            print(f"  System 1: {st['system1']['total_skills']} total skills ({st['system1']['trusted_skills']} trusted/fast-path)")
            print(f"  Circuit Breaker: Tripped: {st['circuit_breaker']['is_tripped']} (Total trips: {st['circuit_breaker']['trip_count']})")
            print(f"  System 2 Model: {st['system2']['model']} (Ollama URL: {st['system2']['base_url']})\n")
            continue

        if cmd_lower == "skills":
            skills = agent.skill_registry.list_skills()
            print(f"\n--- Consolidated Motor Skills ({len(skills)}) ---")
            if not skills:
                print("  No motor skills currently in registry. Execute System 2 actions to consolidate habits.")
            for sk, meta in skills:
                status_tag = f"[{meta.status.value.upper()}]"
                print(f"  - {status_tag} {sk.skill_id} (conf: {sk.confidence:.2f}, steps: {len(sk.action_sequence)}, runs: {meta.validated_count})")
            print()
            continue

        if cmd_lower == "windows":
            res = await agent.execute_command("list windows")
            print(f"\n{res.output}\n")
            continue

        if cmd_lower == "demo":
            print("\n[*] Starting Autonomous Jarvis Demonstration...")
            results = await agent.run_demo()
            for r in results:
                print_result(r)
            print("[*] Demonstration complete!\n")
            continue

        # Execute natural language command
        res = await agent.execute_command(line)
        print_result(res)


def main() -> None:
    """CLI entry point for Reflex Jarvis."""
    parser = argparse.ArgumentParser(description="Reflex Jarvis Autonomous Computer-Use Agent")
    parser.add_argument("--command", "-c", type=str, help="Single command to execute non-interactively")
    parser.add_argument("--demo", action="store_true", help="Run automated demonstration")
    parser.add_argument("--mock", action="store_true", help="Force mock window manager substrate (useful on Linux/CI)")
    parser.add_argument("--model", type=str, default="holo3.1:9b", help="Local Ollama model identifier")
    parser.add_argument("--ollama-url", type=str, default="http://localhost:11434", help="Ollama server base URL")
    args = parser.parse_args()

    use_mock = args.mock or not NativeWindowManager.live_substrate_available()
    ollama_provider = HoloOllamaProvider(
        base_url=args.ollama_url,
        model=args.model,
    )
    agent = JarvisAgent(
        ollama_client=ollama_provider,
        use_mock=use_mock,
    )

    if args.demo:
        print("[*] Running Autonomous Jarvis Demonstration...")
        results = asyncio.run(agent.run_demo())
        for r in results:
            print_result(r)
    elif args.command:
        res = asyncio.run(agent.execute_command(args.command))
        print_result(res)
    else:
        asyncio.run(run_interactive_repl(agent))


if __name__ == "__main__":
    main()
