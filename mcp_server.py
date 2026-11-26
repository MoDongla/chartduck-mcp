# -*- coding: utf-8 -*-
"""ChartDuck MCP server（FastMCP）。

工具名用 snake_case（MCP 客户端对工具名的字符集有约束，不用点号命名空间；
服务器名 `chartduck` 本身就是命名空间）。

    chartduck-mcp                    # stdio
    chartduck-mcp --http             # streamable HTTP, 0.0.0.0:8000/mcp
"""
import sys

try:                          # mcp >= 2 把 FastMCP 改名为 MCPServer
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError as _ToolError
except ImportError:           # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError as _ToolError

from chartduck_client import ChartDuck, ChartDuckError, __version__

# 带上版本号：MCP 客户端的 serverInfo.version 会显示它；留空的话
# 「用户装的是哪一版」从握手里看不出来。
mcp = _Server("chartduck", version=__version__)


def _fail(e):
    # ToolError 是「预期内失败」：客户端拿到 isError=true，文本里带 code，
    # 服务端只记一行日志、不打 traceback（普通异常会被 SDK 换成通用文案）。
    raise _ToolError("%s: %s" % (e.code, e.message))


@mcp.tool()
def extract_chart(image_base64: str = "", image_url: str = "",
                  include_geometry: bool = True) -> dict:
    """Extract chart data from an image.

    Provide exactly one of image_base64 (raw base64, no data: prefix) or image_url.
    Returns {panels: [{box, chart_type, axis, data, geometry, axis_labels}], meta}.
    When the extractor is not confident a panel returns data: null — never guessed.
    """
    try:
        if bool(image_base64) == bool(image_url):
            raise ChartDuckError("invalid_input",
                                "provide exactly one of image_base64 or image_url")
        client = ChartDuck()
        if image_url:
            return client.extract_image_url(image_url, include_geometry)
        return client.extract_image_bytes(_b64(image_base64), None, include_geometry)
    except ChartDuckError as e:
        _fail(e)


@mcp.tool()
def extract_chart_pdf(pdf_base64: str = "", pdf_url: str = "", pages: str = "") -> dict:
    """Extract chart data from a PDF.

    Provide exactly one of pdf_base64 or pdf_url. `pages` accepts "1-5", "3", or "1,3,7".
    Returns {pages: [{page, panels: [...]}], meta}.
    """
    try:
        if bool(pdf_base64) == bool(pdf_url):
            raise ChartDuckError("invalid_input",
                                "provide exactly one of pdf_base64 or pdf_url")
        client = ChartDuck()
        spec = _pages(pages)
        if pdf_url:
            return client.extract_pdf_url(pdf_url, spec)
        return client.extract_pdf_bytes(_b64(pdf_base64), spec)
    except ChartDuckError as e:
        _fail(e)


def _b64(s):
    import base64
    try:
        return base64.b64decode(s, validate=True)
    except Exception:
        raise ChartDuckError("invalid_input", "input is not valid base64")


def _pages(s):
    if not s:
        return None
    out = []
    try:
        for part in str(s).split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-", 1)
                out.extend(range(int(a), int(b) + 1))
            elif part:
                out.append(int(part))
    except ValueError:
        raise ChartDuckError("invalid_input", "invalid pages spec: %s" % s)
    if not out or any(p < 1 for p in out):
        raise ChartDuckError("invalid_input", "invalid pages spec: %s" % s)
    return out


def main():
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
