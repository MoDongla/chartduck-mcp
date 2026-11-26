# -*- coding: utf-8 -*-
"""ChartDuck REST 客户端：MCP server 与 CLI 共用。

传输是**裸字节**（`Content-Type` 决定解码方式），与 serve.py 的 `/extract`
`/extract_pdf` 一致，不做 base64 包装。仅用标准库（urllib），除 MCP server
本身外不需要第三方依赖。
"""
import json
import os
import urllib.error
import urllib.request

__version__ = "0.1.1"

# 必须显式发 UA：api.chartduck.com 的 WAF 按 UA 挡 urllib 的默认值
# （`Python-urllib/3.x` → 403 + CF error 1010，2026-11-26 实测 3/3）。
# 与 Worker 子请求空 UA 被挡是同一类坑，解法一样：在调用侧带上身份。
USER_AGENT = "chartduck-mcp/%s (+https://chartduck.com)" % __version__

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_PDF_BYTES = 100 * 1024 * 1024
DEFAULT_TIMEOUT = 180

ERRORS = {
    400: "invalid_input",
    401: "unauthorized",
    402: "quota_exceeded",
    413: "too_large",
    415: "unsupported_format",
    422: "unreadable",
    429: "rate_limited",
    500: "upstream_error",
    503: "upstream_error",
}

_IMAGE_CTYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".bmp": "image/bmp", ".tif": "image/tiff",
    ".tiff": "image/tiff", ".gif": "image/gif",
}


class ChartDuckError(RuntimeError):
    def __init__(self, code, message, status=None):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message
        self.status = status

    def as_dict(self):
        return {"code": self.code, "message": self.message, "status": self.status}


def _ctype_for(data, filename=None, default="application/octet-stream"):
    """按魔数猜类型，猜不出再看扩展名。"""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:2] == b"BM":
        return "image/bmp"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"%PDF":
        return "application/pdf"
    if filename:
        for ext, ct in _IMAGE_CTYPES.items():
            if filename.lower().endswith(ext):
                return ct
    return default


def _open(req, timeout):
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            body = json.loads(raw)
        except ValueError:
            body = {}
        code = body.get("error") or body.get("code") or ERRORS.get(e.code, "http_%d" % e.code)
        msg = body.get("detail") or body.get("message") or raw[:300].decode("utf-8", "replace")
        raise ChartDuckError(code, msg, e.code)
    except urllib.error.URLError as e:
        raise ChartDuckError("upstream_error", str(e.reason))


def _fetch(url, max_bytes, what):
    """下载远端文件。只允许 https（本地开发可设 CHARTDUCK_ALLOW_HTTP=1）。"""
    if not (url.startswith("https://") or
            (os.environ.get("CHARTDUCK_ALLOW_HTTP") == "1" and url.startswith("http://"))):
        raise ChartDuckError("invalid_input", "only https URLs are accepted: %s" % url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with _open(req, 30) as r:
        data = r.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ChartDuckError("too_large", "%s exceeds %d bytes" % (what, max_bytes))
    return data


class ChartDuck:
    def __init__(self, api_url=None, token=None, timeout=DEFAULT_TIMEOUT):
        self.api_url = (api_url or os.environ.get("CHARTDUCK_API_URL", "")).rstrip("/")
        self.token = token or os.environ.get("CHARTDUCK_TOKEN", "")
        self.timeout = timeout
        if not self.api_url:
            raise ChartDuckError("invalid_input", "CHARTDUCK_API_URL is not set")

    def _headers(self, ctype=None):
        h = {"User-Agent": USER_AGENT}
        if ctype:
            h["Content-Type"] = ctype
        if self.token:
            # 引擎现在认 X-Chartlab-Token；改名后认 X-Chartduck-Token。两个都发，
            # 服务端切换时客户端不用跟着发版。
            h["X-Chartlab-Token"] = self.token
            h["X-Chartduck-Token"] = self.token
        return h

    def _post_raw(self, path, data, ctype):
        req = urllib.request.Request(self.api_url + path, data=data,
                                     headers=self._headers(ctype), method="POST")
        with _open(req, self.timeout) as r:
            res = json.loads(r.read().decode("utf-8"))
        if isinstance(res, dict) and res.get("ok") is False:
            raise ChartDuckError(res.get("error") or "unreadable",
                                res.get("detail") or res.get("error") or "extraction failed")
        return res

    # ---- images -----------------------------------------------------------
    def extract_image_bytes(self, data, filename=None, include_geometry=True):
        if len(data) > MAX_IMAGE_BYTES:
            raise ChartDuckError("too_large", "image exceeds %d bytes" % MAX_IMAGE_BYTES)
        res = self._post_raw("/extract", data, _ctype_for(data, filename, "image/png"))
        if not include_geometry and isinstance(res.get("panels"), list):
            for p in res["panels"]:
                p.pop("geometry", None)
        return res

    def extract_image_file(self, path, include_geometry=True):
        with open(path, "rb") as f:
            return self.extract_image_bytes(f.read(), os.path.basename(path), include_geometry)

    def extract_image_url(self, url, include_geometry=True):
        return self.extract_image_bytes(_fetch(url, MAX_IMAGE_BYTES, "image"),
                                        url.rsplit("/", 1)[-1], include_geometry)

    # ---- pdfs -------------------------------------------------------------
    def extract_pdf_bytes(self, data, pages=None, filename=None):
        if len(data) > MAX_PDF_BYTES:
            raise ChartDuckError("too_large", "pdf exceeds %d bytes" % MAX_PDF_BYTES)
        res = self._post_raw("/extract_pdf", data,
                             _ctype_for(data, filename, "application/pdf"))
        # 服务端当前解析前 N 页，选页在客户端过滤（不省解析开销，契约里写明）。
        if pages and isinstance(res.get("pages"), list):
            want = set(int(p) for p in pages)
            res["pages"] = [p for p in res["pages"] if p.get("page") in want]
        return res

    def extract_pdf_file(self, path, pages=None):
        with open(path, "rb") as f:
            return self.extract_pdf_bytes(f.read(), pages, os.path.basename(path))

    def extract_pdf_url(self, url, pages=None):
        return self.extract_pdf_bytes(_fetch(url, MAX_PDF_BYTES, "pdf"), pages,
                                      url.rsplit("/", 1)[-1])

    # ---- misc -------------------------------------------------------------
    def health(self):
        req = urllib.request.Request(self.api_url + "/health", headers=self._headers())
        with _open(req, 15) as r:
            return json.loads(r.read().decode("utf-8"))


def load_mock(path=None):
    here = os.path.dirname(os.path.abspath(__file__))
    path = path or os.path.join(here, "examples", "sample_response.json")
    if not os.path.exists(path):
        raise ChartDuckError(
            "invalid_input",
            "--mock needs examples/sample_response.json; it ships with the "
            "source repository, not the wheel",
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)
