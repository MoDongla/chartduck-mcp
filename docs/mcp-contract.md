# chartduck-mcp Interface Contract (v0.1 draft)

**English** · [中文](mcp-contract.zh.md)

Status: **draft; keeps the server-side `/extract` and `/extract_pdf` implementations
aligned with the MCP tools.** The hosted service builds on the engine's serving layer
(v2 already provides authentication, rate limiting and quotas). This document defines
only the contract between the MCP client and the service.

## 1. Transport and authentication

- MCP: stdio (default) or streamable HTTP (`--http`, `/mcp`).
- REST (used directly by the client in this repository): JSON over HTTPS.
- Auth headers: the client sends both `X-Chartlab-Token` (the engine's current name) and
  `X-Chartduck-Token` (the new name); the server may accept either. `/health` also
  requires a token, matching existing behaviour.
- Against the hosted public endpoint (`https://api.chartduck.com`) the edge Worker holds
  the engine token itself, so a client token is not required there; send one only when
  you point the client at a private engine.
- The client never stores the token in the repository: use the `CHARTDUCK_API_URL` and
  `CHARTDUCK_TOKEN` environment variables.
- For local debugging, set `CHARTDUCK_ALLOW_HTTP=1` to allow plain HTTP.

## 2. MCP tools

### `extract_chart`

| Parameter | Type | Description |
|---|---|---|
| `image_base64` | string | base64 of the image's raw bytes (**without** the `data:` prefix) |
| `image_url` | string | https only; the client downloads it, ≤20 MB |
| `include_geometry` | bool | default true; when false the client removes `geometry` from the response (the server currently always returns it) |

Provide **exactly one** of `image_base64` and `image_url`. The request body sent to the
server is **raw bytes** (`Content-Type` inferred from magic bytes/extension), not
base64-wrapped.

Returns:

```json
{
  "panels": [
    {
      "box": [L, T, R, B],
      "chart_type": "bar|barh|line|scatter|box|unknown",
      "why": "no_y_axis|no_value_axis|null",
      "axis": {"x": [x0, x1], "y": [y0, y1]},
      "axis_labels": {"x": {"text": "...", "score": 0.98} | null,
                       "y": {"text": "...", "score": 1.0} | null},
      "data": {"series": [...]} | null,
      "geometry": {"units": "normalized_box", ...} | null
    }
  ],
  "meta": {"engine_version": "1.4.0", "ocr": "gpu", "elapsed_ms": 2410}
}
```

Any combination of `data` and `geometry` other than both being null is allowed (panels
with a value axis return `data`; panels without one return `geometry`). Both null means
the panel could not be read — not an error.

### `extract_chart_pdf`

| Parameter | Type | Description |
|---|---|---|
| `pdf_base64` | string | base64 of the PDF's raw bytes |
| `pdf_url` | string | https only; ≤100 MB |
| `pages` | string | `"1-5"`, `"3"` or `"1,3,7"`; defaults to all pages (the server parses the first N pages; page selection is filtered on the client) |

Returns:

```json
{"pages": [{"page": 1, "panels": [ ...same panel shape as extract_chart... ]}],
 "meta": {"engine_version": "1.4.0", "pages_parsed": 3}}
```

## 3. REST endpoint mapping

| MCP tool | REST | Request body |
|---|---|---|
| `extract_chart` | `POST {API_URL}/extract` | raw image bytes, e.g. `Content-Type: image/png` |
| `extract_chart_pdf` | `POST {API_URL}/extract_pdf` | raw PDF bytes, `Content-Type: application/pdf` |

This matches the existing `serve.py` behaviour (it decodes by `Content-Type`/magic
bytes; the JSON body accepts only `image_b64`/`image`). The client connects over HTTPS
by default; `CHARTDUCK_ALLOW_HTTP=1` allows plain HTTP for local debugging.

## 4. Errors

MCP: a failed tool returns `isError=true` with text of the form `code: message`
(e.g. `invalid_input: provide exactly one of image_base64 or image_url`).
REST HTTP status ↔ code:

| HTTP | code | Meaning |
|---:|---|---|
| 400 | `invalid_input` | missing/conflicting parameter, invalid base64, malformed pages, image decode failure |
| 401 | `unauthorized` | missing or wrong token |
| 402 | `quota_exceeded` | daily quota exhausted |
| 413 | `too_large` | over the size limit |
| 415 | `unsupported_format` | not an image or PDF |
| 422 | `unreadable` | the file opens but no panel can be extracted (`extract_failed` / `pdf_no_pages` etc.; see `error`) |
| 429 | `rate_limited` | rate limited (the response includes Retry-After) |
| 5xx | `upstream_error` | service failure |

## 5. Limits (draft; the server may adjust)

- Images ≤20 MB; PDFs ≤100 MB and ≤200 pages.
- No hard cap on panels per page, but above 20 the server returns only the first 20.
- Default client timeout: 180 s (large PDFs).

## 6. Versioning and compatibility

- Tool names and parameters may change in a breaking way within v0.x; from v1.0 the
  contract follows semantic versioning.
- `meta.engine_version` is the server's `chartlab-extract` version (currently 1.3.0;
  1.4.0 is planned for the pilot).
- New fields are not breaking changes; clients must ignore unknown fields.

## 7. Open questions (require product decisions)

1. Should the server download `image_url` on the client's behalf? (Current design: the
   client downloads it, avoiding SSRF on the server.)
2. Should a batch tool (multiple images at once) be exposed over MCP, or only through
   REST `/extract_batch`?
3. Quota accounting during the pilot (pages/day vs. token-based billing).
4. Should `axis_labels` ship with the pilot? (Current accuracy is 76.9% on y; the
   response may keep it, but the documentation makes no promise.)
