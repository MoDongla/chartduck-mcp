# -*- coding: utf-8 -*-
"""客户端测试：本地假服务端，不需要真服务和第三方依赖。

    python -m unittest discover -s tests -v
"""
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chartduck_client as cc  # noqa: E402

SEEN = {}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _reply(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)
        SEEN.clear()
        SEEN.update(path=self.path,
                    token=self.headers.get("X-Chartduck-Token"),
                    legacy_token=self.headers.get("X-Chartlab-Token"),
                    ctype=self.headers.get("Content-Type"),
                    nbytes=len(raw),
                    magic=raw[:4])
        if raw.endswith(b"FAIL"):
            self._reply(422, {"ok": False, "error": "extract_failed", "detail": "no panels"})
        elif self.path == "/extract_pdf":
            self._reply(200, {"ok": True, "pages": [
                {"page": 1, "panels": []}, {"page": 2, "panels": []},
                {"page": 3, "panels": []}]})
        else:
            self._reply(200, {"ok": True, "panels": [
                {"chart_type": "line", "geometry": {"units": "normalized_box"}}]})

    def do_GET(self):
        self._reply(200, {"ok": True, "version": "test"})


class ClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Handler)
        cls.url = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        os.environ["CHARTDUCK_ALLOW_HTTP"] = "1"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def client(self):
        return cc.ChartDuck(api_url=self.url, token="tok-test", timeout=10)

    def test_raw_transport_and_headers(self):
        out = self.client().extract_image_bytes(PNG, "a.png")
        self.assertTrue(out["ok"])
        self.assertEqual(SEEN["path"], "/extract")
        self.assertEqual(SEEN["token"], "tok-test")
        self.assertEqual(SEEN["legacy_token"], "tok-test")
        self.assertEqual(SEEN["ctype"], "image/png")
        self.assertEqual(SEEN["nbytes"], len(PNG))

    def test_ctypes(self):
        self.assertEqual(cc._ctype_for(b"%PDF-1.7 x"), "application/pdf")
        self.assertEqual(cc._ctype_for(b"\xff\xd8\xff\xe0"), "image/jpeg")
        self.assertEqual(cc._ctype_for(b"xxxx", "b.JPG"), "image/jpeg")
        self.assertEqual(cc._ctype_for(b"xxxx"), "application/octet-stream")

    def test_geometry_filter(self):
        out = self.client().extract_image_bytes(PNG, "a.png", include_geometry=False)
        self.assertNotIn("geometry", out["panels"][0])

    def test_error_translation(self):
        with self.assertRaises(cc.ChartDuckError) as cm:
            self.client().extract_image_bytes(PNG + b"FAIL")
        self.assertEqual(cm.exception.code, "extract_failed")
        self.assertEqual(cm.exception.status, 422)

    def test_pdf_page_filter(self):
        out = self.client().extract_pdf_bytes(b"%PDF-1.7 ...", pages=[2])
        self.assertEqual([p["page"] for p in out["pages"]], [2])
        self.assertEqual(SEEN["ctype"], "application/pdf")

    def test_rejects_plain_http_url(self):
        del os.environ["CHARTDUCK_ALLOW_HTTP"]
        try:
            with self.assertRaises(cc.ChartDuckError):
                cc._fetch("http://example.com/x.png", 10, "img")
        finally:
            os.environ["CHARTDUCK_ALLOW_HTTP"] = "1"

    def test_requires_api_url(self):
        with self.assertRaises(cc.ChartDuckError) as cm:
            cc.ChartDuck(api_url="")
        self.assertEqual(cm.exception.code, "invalid_input")

    def test_size_guard(self):
        with self.assertRaises(cc.ChartDuckError) as cm:
            cc.ChartDuck(api_url=self.url).extract_image_bytes(b"x" * (cc.MAX_IMAGE_BYTES + 1))
        self.assertEqual(cm.exception.code, "too_large")


if __name__ == "__main__":
    unittest.main()
