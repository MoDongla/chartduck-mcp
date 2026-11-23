# -*- coding: utf-8 -*-
"""ChartDuck CLI。

    chartduck extract figure.png -o figure.json
    chartduck extract-pdf paper.pdf --pages 1-3 -o paper.json
    chartduck health
"""
import argparse
import json
import sys

from chartduck_client import ChartDuck, ChartDuckError, load_mock


def _emit(obj, out):
    text = json.dumps(obj, ensure_ascii=False, indent=1)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print("->", out)
    else:
        print(text)


def _run(fn, out):
    try:
        _emit(fn(), out)
        return 0
    except ChartDuckError as e:
        print(json.dumps(e.as_dict(), ensure_ascii=False), file=sys.stderr)
        return 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="chartduck")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="extract chart data from an image")
    e.add_argument("path")
    e.add_argument("-o", "--out")
    e.add_argument("--no-geometry", action="store_true")
    e.add_argument("--mock", action="store_true", help="use examples/sample_response.json")

    p = sub.add_parser("extract-pdf", help="extract chart data from a PDF")
    p.add_argument("path")
    p.add_argument("--pages", help='"1-5", "3", or "1,3,7"')
    p.add_argument("-o", "--out")
    p.add_argument("--mock", action="store_true")

    sub.add_parser("health", help="check the hosted service")
    args = ap.parse_args(argv)

    if args.cmd == "health":
        return _run(lambda: ChartDuck().health(), None)
    if args.mock:
        return _run(load_mock, args.out)
    if args.cmd == "extract":
        return _run(lambda: ChartDuck().extract_image_file(args.path, not args.no_geometry),
                    args.out)
    if args.cmd == "extract-pdf":
        pages = None
        if args.pages:
            pages = []
            for part in args.pages.split(","):
                if "-" in part:
                    a, b = part.split("-", 1)
                    pages.extend(range(int(a), int(b) + 1))
                elif part:
                    pages.append(int(part))
        return _run(lambda: ChartDuck().extract_pdf_file(args.path, pages), args.out)
    return 2


if __name__ == "__main__":
    sys.exit(main())
