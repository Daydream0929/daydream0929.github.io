#!/usr/bin/env python3
"""Publish workspace markdown reports as styled HTML with an index page.

Scans the workspace root for report markdown files, converts each into
reports/<name>.html via md2html, and regenerates reports/index.html.
"""

import argparse
import glob
import html
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from md2html import convert  # noqa: E402

# scripts/ -> tech-research-report/ -> skills/ -> workspace root
DEFAULT_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))

INDEX_TEMPLATE = u"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>技术调研报告索引</title>
<style>
:root {{ --fg:#1a1a1a; --soft:#4a4a4a; --bg:#fff; --soft-bg:#f6f7f9;
        --border:#e3e6ea; --accent:#b8442e; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --fg:#e6e6e6; --soft:#a8a8a8; --bg:#14161a; --soft-bg:#1b1e24;
          --border:#2c313a; --accent:#e0705a; }}
}}
body {{ margin:0; background:var(--bg); color:var(--fg); line-height:1.7;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",
              "Microsoft YaHei",sans-serif; }}
.wrap {{ max-width:860px; margin:0 auto; padding:48px 32px 80px; }}
h1 {{ font-size:28px; margin:0 0 6px; font-weight:650; }}
.sub {{ color:var(--soft); font-size:14px; margin:0 0 32px; }}
table {{ border-collapse:collapse; width:100%; font-size:15px; }}
th,td {{ border:1px solid var(--border); padding:11px 14px; text-align:left; }}
th {{ background:var(--soft-bg); font-weight:600; }}
tbody tr:nth-child(even) {{ background:var(--soft-bg); }}
a {{ color:var(--accent); text-decoration:none; }}
a:hover {{ text-decoration:underline; }}
.mono {{ font-family:"SF Mono",Menlo,Consolas,monospace; font-size:12.5px;
        color:var(--soft); }}
</style>
</head>
<body>
<div class="wrap">
<h1>技术调研报告索引</h1>
<p class="sub">生成时间 {generated} · 共 {count} 份报告 · 源码在工作区根目录，HTML 在本目录</p>
<table>
<thead><tr><th>报告</th><th>章节数</th><th>更新时间</th><th>Markdown 源文件</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
</div>
</body>
</html>
"""


def collect_sources(root):
    found = []
    for path in sorted(glob.glob(os.path.join(root, '*.md'))):
        name = os.path.basename(path)
        if name.lower().startswith('readme'):
            continue
        found.append(path)
    return found


def declares_technical_research(source):
    """Return true only for reports that explicitly opt into validation."""
    try:
        in_fence = False
        with open(source, 'r', encoding='utf-8-sig') as handle:
            for line in handle:
                stripped = line.lstrip()
                if stripped.startswith('```') or stripped.startswith('~~~'):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    continue
                cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
                if len(cells) >= 2 and cells[0] == '文档类型' and cells[1] == '技术调研报告':
                    return True
    except (OSError, UnicodeError):
        pass
    return False


def validate_declared_report(validator, source):
    """Run the standalone validator and leave its diagnostics on stdout."""
    return subprocess.call([
        sys.executable, validator, source, '--profile', 'auto'
    ])


def main():
    parser = argparse.ArgumentParser(
        description='Publish workspace markdown reports as styled HTML.')
    parser.add_argument('--root', default=DEFAULT_ROOT,
                        help='workspace root containing report .md files')
    parser.add_argument('--out', default=None,
                        help='output directory (default: <root>/reports)')
    parser.add_argument('--validate', action='store_true',
                        help='validate declared 技术调研报告 files before publishing')
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    out = os.path.abspath(args.out) if args.out else os.path.join(root, 'reports')
    if not os.path.isdir(out):
        os.makedirs(out)

    rows = []
    count = 0
    validation_failures = 0
    validator = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'validate_research_report.py')
    for source in collect_sources(root):
        if args.validate and declares_technical_research(source):
            if validate_declared_report(validator, source) != 0:
                print('validation failed: %s' % source)
                validation_failures += 1
                continue

        stem = os.path.splitext(os.path.basename(source))[0]
        target = os.path.join(out, stem + '.html')
        try:
            title, sections = convert(source, target)
        except Exception as exc:  # noqa: BLE001
            print('failed: %s: %s' % (source, exc), file=sys.stderr)
            continue
        count += 1
        stamp = time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(source)))
        rows.append(
            '<tr><td><a href="%s">%s</a></td><td>%d</td><td>%s</td>'
            '<td class="mono">%s.md</td></tr>' % (
                html.escape(stem + '.html'), html.escape(title), sections,
                stamp, html.escape(stem)))

    index = INDEX_TEMPLATE.format(
        generated=time.strftime('%Y-%m-%d %H:%M:%S'),
        count=count,
        rows='\n'.join(rows),
    )
    with open(os.path.join(out, 'index.html'), 'w', encoding='utf-8') as handle:
        handle.write(index)

    return 2 if validation_failures else 0


if __name__ == '__main__':
    sys.exit(main())
