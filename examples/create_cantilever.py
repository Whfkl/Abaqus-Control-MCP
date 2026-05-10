"""Create a small cantilever demo model through the Abaqus MCP bridge."""

from abaqus_mcp_bridge.cli import CANTILEVER_DEMO_CODE
from abaqus_mcp_bridge.client import AbaqusBridgeClient


def main() -> None:
    result = AbaqusBridgeClient(timeout=60).execute(CANTILEVER_DEMO_CODE)
    print(result)


if __name__ == "__main__":
    main()
