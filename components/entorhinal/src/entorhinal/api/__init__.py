"""Local FastAPI Application and HTTP Transport Layer.

Exports:
- app: Default FastAPI application instance
- create_app: Factory function for dependency injection
"""

from entorhinal.api.app import app, create_app

__all__ = ["app", "create_app"]
