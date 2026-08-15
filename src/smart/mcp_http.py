"""Remote MCP entrypoint for hosted ChatGPT/App connections."""

from __future__ import annotations

import os

from .server import mcp


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=os.getenv("MCP_HOST", "0.0.0.0"),
        port=int(os.getenv("MCP_PORT", "8001")),
    )
