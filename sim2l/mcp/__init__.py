"""MCP integration for exposing sim2l services as agent tools.

The transport layer depends on the optional ``mcp`` package. Core gateway
logic lives in :mod:`sim2l.mcp.gateway` and can be tested without that
dependency installed.
"""

from .gateway import Sim2LMCPGateway

__all__ = ["Sim2LMCPGateway"]
