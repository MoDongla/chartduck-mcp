# ChartDuck MCP

Open-source MCP server and CLI for [ChartDuck](https://chartduck.com) — chart data
extraction from scientific figures and document pages. The extraction engine runs on
the hosted service; this repository is the thin client (MCP + CLI + Python SDK).

> **Status: pre-release (0.1.x).** The hosted API is live at
> `https://api.chartduck.com`, so the client listed here does reach a working service.
> It is a shared public endpoint with a daily quota and no uptime commitment — if it
> answers `429` / `rate_limited`, wait and retry. The contract, code and error
> semantics below are implemented and tested against a mock, a local engine and the
> hosted endpoint.

## What it does

Given a chart image (or a PDF page), return structured data per panel:

- panel box, chart type (`bar` / `barh` / `line` / `scatter` / `box`)
- data series (values in data coordinates when the axes can be calibrated)
- geometry for panels without a value axis (`normalized_box` units)
- recognized axis titles (beta)

```json
{
  "panels": [
    {
      "box": [100.0, 19.0, 474.0, 393.0],
      "chart_type": "line",
      "axis_labels": {
        "x": {"text": "Baseline Fgas", "score": 0.98},
        "y": {"text": "Change in Fgas", "score": 1.0}
      },
      "data": {"series": [{"kind": "line", "points": [[0.5022, -0.0007], "..."]}]}
    }
  ],
  "meta": {"engine_version": "1.4.0", "elapsed_ms": 2640}
}
```

## Honest capability statement

Measured on public ICPR2022-style documents (unseen distribution):

- **~65-70% of figures yield data automatically**; the rest return `data: null`.
- Supported types: vertical bar, line, scatter, vertical box, horizontal bar.
  `scatter-line` is partially supported. Other types are refused, not guessed.
- **If the extractor is not confident, it returns `null` instead of a wrong table.**
  This is a design choice: a missing value is recoverable, a plausible wrong value is not.
- Axis titles are beta: x-axis content accuracy 91.7%, y-axis 76.9% — not covered by any
  support commitment.

Full benchmark methodology: <https://chartduck.com/#benchmarks>.

## Install

Requires Python 3.10+.

```bash
pip install chartduck-mcp          # 0.1.1: hosted API is live
# or from source
git clone https://github.com/MoDongla/chartduck-mcp && cd chartduck-mcp && pip install -e .
```

## Configure

```bash
export CHARTDUCK_API_URL="https://api.chartduck.com"   # hosted service base URL
export CHARTDUCK_TOKEN="..."                            # optional: only for a private deployment
```

## Use as an MCP server

Claude Code:

```bash
claude mcp add chartduck -- chartduck-mcp
```

Claude Desktop / generic JSON config:

```json
{
  "mcpServers": {
    "chartduck": {
      "command": "chartduck-mcp",
      "env": {
        "CHARTDUCK_API_URL": "https://api.chartduck.com",
        "CHARTDUCK_TOKEN": "..."
      }
    }
  }
}
```

Streamable HTTP mode (for hosting):

```bash
chartduck-mcp --http   # listens on 0.0.0.0:8000/mcp by default
```

### Tools

| Tool | Input | Returns |
|---|---|---|
| `extract_chart` | `image_base64` or `image_url`, `include_geometry` | `{panels: [...], meta}` |
| `extract_chart_pdf` | `pdf_base64` or `pdf_url`, `pages` (`"1-5"`, `"3"`, `"1,3"`) | `{pages: [{page, panels}], meta}` |

Tool failures come back as MCP `isError` results with text `code: message`
(`invalid_input`, `unauthorized`, `quota_exceeded`, `unreadable`, `rate_limited`, ...);
full table in `docs/mcp-contract.md`.

## Use as a CLI

```bash
chartduck extract figure.png -o figure.json
chartduck extract-pdf paper.pdf --pages 1-3 -o paper.json
chartduck health
```

Add `--mock` to parse `examples/sample_response.json` without a service
(useful for wiring integrations).

## SDK

```python
from chartduck_client import ChartDuck

client = ChartDuck()                      # reads CHARTDUCK_API_URL / CHARTDUCK_TOKEN
result = client.extract_image_file("figure.png")
for panel in result["panels"]:
    print(panel["chart_type"], panel.get("data"))
```

## Layout

```
chartduck_client.py   # REST client (stdlib urllib; the only third-party dep is `mcp`)
mcp_server.py         # MCP server (FastMCP, stdio or streamable HTTP)
cli.py                # command line
docs/mcp-contract.md  # tool contract, error codes, limits (English; 中文版 mcp-contract.zh.md)
examples/             # sample response
```

## License

MIT. The hosted ChartDuck service, extraction engine, and evaluation corpus are not
part of this repository.
