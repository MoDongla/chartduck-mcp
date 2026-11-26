# chartduck-mcp 接口契约（v0.1 草案）

[English](mcp-contract.md) · **中文**

状态：**草案，供服务端 `/extract` `/extract_pdf` 实现与 MCP 工具对齐**。
服务端实现以引擎的服务层为底座（v2 已有鉴权/限流/配额），
本文件只定义 MCP 客户端与服务端之间的约定。

## 1. 传输与鉴权

- MCP：stdio（默认）或 streamable HTTP（`--http`，`/mcp`）。
- REST（本仓库客户端直连）：JSON over HTTPS。
- 鉴权头：客户端同时发 `X-Chartlab-Token`（引擎现名）与 `X-Chartduck-Token`（新名），
  服务端认哪个都行；`/health` 也要求带令牌（既有一致性行为）。
- 打托管公网口（`https://api.chartduck.com`）时钥匙在边缘 Worker 里，客户端不需要带令牌；
  只有指向私有引擎部署时才要。
- 客户端不在仓库里存令牌：`CHARTDUCK_API_URL` / `CHARTDUCK_TOKEN` 环境变量。
- 本地调试可设 `CHARTDUCK_ALLOW_HTTP=1` 放开 http。

## 2. MCP 工具

### `extract_chart`

| 参数 | 类型 | 说明 |
|---|---|---|
| `image_base64` | string | 图片原始字节的 base64（**不带** `data:` 前缀） |
| `image_url` | string | 仅 https；客户端负责下载，≤20 MB |
| `include_geometry` | bool | 默认 true；false 时客户端从响应里删掉 `geometry`（服务端目前恒返回） |

二者必须**恰好给一个**。请求体到服务端是**裸字节**（`Content-Type` 按魔数/扩展名猜），
不做 base64 包装。

返回：

```json
{
  "panels": [
    {
      "box": [L, T, R, B],
      "chart_type": "bar|barh|line|scatter|box|unknown",
      "why": "no_y_axis|no_value_axis|null",
      "axis": {"x": [x0, x1], "y": [y0, y1]} ,
      "axis_labels": {"x": {"text": "...", "score": 0.98} | null,
                       "y": {"text": "...", "score": 1.0} | null},
      "data": {"series": [...]} | null,
      "geometry": {"units": "normalized_box", ...} | null
    }
  ],
  "meta": {"engine_version": "1.4.0", "ocr": "gpu", "elapsed_ms": 2410}
}
```

`data` 与 `geometry` **至少一个为 null 之外的组合是允许的**（值轴面板给 data，
无值轴面板给 geometry）；两者都为 null 表示这个面板读不出来（不是错误）。

### `extract_chart_pdf`

| 参数 | 类型 | 说明 |
|---|---|---|
| `pdf_base64` | string | PDF 原始字节 base64 |
| `pdf_url` | string | 仅 https；≤100 MB |
| `pages` | string | `"1-5"` / `"3"` / `"1,3,7"`，默认全部（服务端解析前 N 页，选页在客户端过滤） |

返回：

```json
{"pages": [{"page": 1, "panels": [ ...同 extract_chart 的 panel... ]}],
 "meta": {"engine_version": "1.4.0", "pages_parsed": 3}}
```

## 3. REST 端点映射

| MCP 工具 | REST | 请求体 |
|---|---|---|
| `extract_chart` | `POST {API_URL}/extract` | 图片裸字节，`Content-Type: image/png` 等 |
| `extract_chart_pdf` | `POST {API_URL}/extract_pdf` | PDF 裸字节，`Content-Type: application/pdf` |

与 `serve.py` 现有实现一致（它按 `Content-Type`/魔数解码，JSON 只认 `image_b64`/`image`）。
客户端默认只连 https；本地调试可设 `CHARTDUCK_ALLOW_HTTP=1`。

## 4. 错误

MCP 侧：工具失败返回 `isError=true`，文本形如 `code: message`
（例：`invalid_input: provide exactly one of image_base64 or image_url`）。
REST 侧 HTTP 状态与 code 对应：

| HTTP | code | 含义 |
|---:|---|---|
| 400 | `invalid_input` | 参数缺失/冲突、base64 不合法、pages 格式错、图片解码失败 |
| 401 | `unauthorized` | 令牌缺失或错误 |
| 402 | `quota_exceeded` | 当日配额用尽 |
| 413 | `too_large` | 超过体积上限 |
| 415 | `unsupported_format` | 非图片/PDF |
| 422 | `unreadable` | 图能打开但抽不出面板（`extract_failed` / `pdf_no_pages` 等，具体看 `error`） |
| 429 | `rate_limited` | 限流（响应含 Retry-After） |
| 5xx | `upstream_error` | 服务端故障 |

## 5. 上限（草案，服务端可调）

- 图片 ≤20 MB；PDF ≤100 MB、≤200 页；
- 单页面板数不设硬上限，但 >20 时服务端只回前 20 个；
- 客户端超时默认 180 s（PDF 大文件）。

## 6. 版本与兼容

- 工具名与参数在 v0.x 内可能破坏性调整；v1.0 起遵循语义化版本。
- `meta.engine_version` 对应服务端 `chartlab-extract` 版本（当前 v1.3.0，试点版计划升 v1.4.0）。
- 新增字段不视为破坏性变更；客户端必须忽略未知字段。

## 7. 未定项（需产品决策）

1. 是否允许 `image_url` 服务端代下载（当前设计：客户端下载，避免服务端 SSRF）；
2. 批量工具（一次多图）是否进 MCP，或只走 REST `/extract_batch`；
3. 试点期的配额口径（页/天 vs token 计费）；
4. `axis_labels` 是否随试点开启（当前精度 y 76.9%，默认可以在响应里保留但文档不承诺）。
