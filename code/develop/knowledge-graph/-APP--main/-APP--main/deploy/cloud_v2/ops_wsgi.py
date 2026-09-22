"""Eager production WSGI binding for the private ops-admin-agent."""

from .ops_server import create_production_ops_app


application = create_production_ops_app()
app = application


__all__ = ["app", "application"]
