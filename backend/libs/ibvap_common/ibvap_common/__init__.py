"""Shared library for all IBVAP microservices.

Per the Implementation Guide (IG §3): no service imports another service's
package directly. This is the only code shared across service boundaries.
"""

__all__ = ["auth", "db", "errors", "internal_auth", "logging", "redis_streams", "settings"]
