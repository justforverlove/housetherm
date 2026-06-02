"""
build_report.py — 將 REPORT.md 轉成列印用 HTML (P13922002.html)。
在瀏覽器開啟 → 列印 → 另存為 PDF，命名 P13922002.pdf 即為繳交檔。
用法： python build_report.py
"""
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent
STUDENT_ID = "P13922002"

CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: 'Noto Sans CJK TC','PingFang TC','Microsoft JhengHei',
       -apple-system,Arial,sans-serif; line-height: 1.55; color:#1a1a1a;
       max-width: 820px; margin: 24px auto; padding: 0 16px; font-size: 14px; }
h1 { font-size: 22px; border-bottom: 3px solid #c0392b; padding-bottom: 6px; }
h2 { font-size: 17px; margin-top: 22px; border-bottom: 1px solid #ddd; padding-bottom: 3px; }
h3 { font-size: 14px; color:#333; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 12.5px; }
th,td { border: 1px solid #ccc; padding: 4px 8px; text-align: left; }
th { background: #f3f4f6; }
code { background:#f4f4f4; padding:1px 4px; border-radius:3px; font-size:12px; }
pre { background:#f7f7f9; border:1px solid #e3e3e8; border-radius:6px; padding:10px;
      overflow:auto; font-size:11.5px; line-height:1.4; }
blockquote { border-left:4px solid #c0392b; margin:8px 0; padding:4px 12px;
             background:#fbf3f2; color:#444; }
a { color:#1565c0; text-decoration:none; }
"""


def main():
    md_text = (ROOT / "REPORT.md").read_text(encoding="utf-8")
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code", "toc"])
    html = (f"<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'>"
            f"<title>{STUDENT_ID} — Final Project</title><style>{CSS}</style></head>"
            f"<body>{body}</body></html>")
    out = ROOT / f"{STUDENT_ID}.html"
    out.write_text(html, encoding="utf-8")
    print(f"已輸出 {out}")
    print(f"→ 用瀏覽器開啟，列印(Cmd+P) → 另存為 PDF → 命名 {STUDENT_ID}.pdf")


if __name__ == "__main__":
    main()
