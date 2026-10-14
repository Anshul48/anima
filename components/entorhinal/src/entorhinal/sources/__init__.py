"""Permitted Source Adapters for Entorhinal.

Provides passive, privacy-gated signal adapters:
- BaseSourceAdapter: Abstract lifecycle & buffer contract
- BrowserSourceAdapter: DOM text selection, navigation, password suppression
- OSWindowSourceAdapter: Window focus, process tracking, blacklist suppression
- TerminalPTYSourceAdapter: Loss-free CLI execution and output capture
- MockSourceAdapter: High-throughput stream generator for testing
"""

from entorhinal.sources.base import BaseSourceAdapter
from entorhinal.sources.browser import BrowserSourceAdapter, is_sensitive_dom_element
from entorhinal.sources.mock import MockSourceAdapter
from entorhinal.sources.os_window import OSWindowSourceAdapter
from entorhinal.sources.terminal_pty import TerminalPTYSourceAdapter, clean_terminal_output

__all__ = [
    "BaseSourceAdapter",
    "BrowserSourceAdapter",
    "MockSourceAdapter",
    "OSWindowSourceAdapter",
    "TerminalPTYSourceAdapter",
    "clean_terminal_output",
    "is_sensitive_dom_element",
]
