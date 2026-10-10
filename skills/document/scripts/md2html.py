#!/usr/bin/env python3
"""Self-contained Markdown -> HTML converter for technical research reports.

No external dependencies. Targets Python 3.8+. Handles the constructs used by
this project's reports: GFM pipe tables, fenced code blocks, mermaid diagrams,
ordered/unordered lists, blockquotes, inline formatting, and an auto-generated
table of contents.

Content is HTML-escaped before rendering so serving over HTTP cannot execute
injected markup.
"""

import argparse
import html
import os
import re
import sys

HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$')
FENCE_RE = re.compile(r'^```(\w*)\s*$')
HR_RE = re.compile(r'^\s*([-*_])\s*(?:\1\s*){2,}$')
UL_RE = re.compile(r'^(\s*)[-*+]\s+(.*)$')
OL_RE = re.compile(r'^(\s*)\d+[.)]\s+(.*)$')
QUOTE_RE = re.compile(r'^>\s?(.*)$')
TABLE_ROW_RE = re.compile(r'^\s*\|(.*)\|\s*$')
TABLE_SEP_RE = re.compile(r'^\s*\|?[\s:|-]+\|?\s*$')
CODE_SPAN_RE = re.compile(r'`([^`]+)`')
STANDALONE_IMAGE_RE = re.compile(r'^!\[([^\]]*)\]\(([^)\s]+)\)\s*$')
INLINE_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)\)')

BADGE_TOKENS = {
    'C': ('badge-c', '源码/一手来源核实'),
    'C*': ('badge-cstar', '规范级稳定知识'),
    'S': ('badge-s', '单一来源，未交叉验证'),
    'P': ('badge-p', '预测/估算'),
    '?': ('badge-q', '未能核实'),
}


def slugify(text, used):
    """Build a stable, unique HTML id from heading text."""
    base = re.sub(r'[^\w\u4e00-\u9fff-]+', '-', text.strip().lower())
    base = re.sub(r'-+', '-', base).strip('-') or 'section'
    candidate, n = base, 1
    while candidate in used:
        n += 1
        candidate = '%s-%d' % (base, n)
    used.add(candidate)
    return candidate


def render_inline(text):
    """Escape then apply inline formatting. Code spans are protected first."""
    placeholders = []

    def stash(match):
        placeholders.append(match.group(1))
        return '\x00%d\x00' % (len(placeholders) - 1)

    text = CODE_SPAN_RE.sub(stash, text)
    text = html.escape(text, quote=False)

    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', text)
    text = INLINE_IMAGE_RE.sub(
        lambda m: '<img src="%s" alt="%s">'
                  % (html.escape(m.group(2), quote=True),
                     html.escape(m.group(1), quote=True)),
        text)
    text = re.sub(r'\[([^\]]+)\]\(([^)\s]+)\)',
                  lambda m: '<a href="%s" rel="noopener">%s</a>'
                            % (html.escape(m.group(2), quote=True), m.group(1)),
                  text)

    def restore(match):
        idx = int(match.group(1))
        return '<code>%s</code>' % html.escape(placeholders[idx])

    text = re.sub(r'\x00(\d+)\x00', restore, text)
    return text


def decorate_badges(fragment):
    """Turn reliability markers rendered as <code>C</code> into colored badges."""
    for token, (cls, title) in BADGE_TOKENS.items():
        pattern = '<code>%s</code>' % html.escape(token)
        replacement = '<span class="badge %s" title="%s">%s</span>' % (
            cls, html.escape(title, quote=True), html.escape(token))
        fragment = fragment.replace(pattern, replacement)
    return fragment


def split_table_cells(line):
    inner = TABLE_ROW_RE.match(line).group(1)
    return [cell.strip() for cell in inner.split('|')]


def is_separator(line):
    return bool(TABLE_ROW_RE.match(line)) and bool(
        re.match(r'^[\s|:-]+$', line)) and '-' in line


def parse(lines):
    """Convert markdown lines into (html_body, toc_entries)."""
    out = []
    toc = []
    used_ids = set()
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        fence = FENCE_RE.match(line)
        if fence:
            lang = fence.group(1).lower()
            i += 1
            block = []
            while i < n and not FENCE_RE.match(lines[i]):
                block.append(lines[i])
                i += 1
            i += 1
            body = html.escape('\n'.join(block))
            if lang == 'mermaid':
                out.append('<div class="mermaid">%s</div>' % body)
            else:
                label = ' data-lang="%s"' % html.escape(lang, quote=True) if lang else ''
                out.append('<pre><code%s>%s</code></pre>' % (label, body))
            continue

        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2).strip()
            anchor = slugify(text, used_ids)
            out.append('<h%d id="%s">%s</h%d>'
                       % (level, anchor, decorate_badges(render_inline(text)), level))
            if 1 <= level <= 3:
                toc.append((level, anchor, text))
            i += 1
            continue

        if HR_RE.match(line):
            out.append('<hr>')
            i += 1
            continue

        if TABLE_ROW_RE.match(line) and i + 1 < n and is_separator(lines[i + 1]):
            header = split_table_cells(line)
            i += 2
            rows = []
            while i < n and TABLE_ROW_RE.match(lines[i]) and not is_separator(lines[i]):
                rows.append(split_table_cells(lines[i]))
                i += 1
            parts = ['<div class="table-wrap"><table>', '<thead><tr>']
            for cell in header:
                parts.append('<th>%s</th>' % decorate_badges(render_inline(cell)))
            parts.append('</tr></thead><tbody>')
            for row in rows:
                parts.append('<tr>')
                for idx in range(len(header)):
                    cell = row[idx] if idx < len(row) else ''
                    parts.append('<td>%s</td>' % decorate_badges(render_inline(cell)))
                parts.append('</tr>')
            parts.append('</tbody></table></div>')
            out.append(''.join(parts))
            continue

        quote = QUOTE_RE.match(line)
        if quote:
            collected = []
            while i < n and QUOTE_RE.match(lines[i]):
                collected.append(QUOTE_RE.match(lines[i]).group(1))
                i += 1
            out.append('<blockquote>%s</blockquote>'
                       % decorate_badges(render_inline(' '.join(collected))))
            continue

        ul = UL_RE.match(line)
        ol = OL_RE.match(line)
        if ul or ol:
            tag = 'ul' if ul else 'ol'
            items = []
            matcher = UL_RE if ul else OL_RE
            while i < n and matcher.match(lines[i]):
                items.append('<li>%s</li>'
                             % decorate_badges(render_inline(matcher.match(lines[i]).group(2))))
                i += 1
            out.append('<%s>%s</%s>' % (tag, ''.join(items), tag))
            continue

        paragraph = []
        while i < n and lines[i].strip() and not HEADING_RE.match(lines[i]) \
                and not FENCE_RE.match(lines[i]) and not HR_RE.match(lines[i]) \
                and not QUOTE_RE.match(lines[i]) and not TABLE_ROW_RE.match(lines[i]) \
                and not UL_RE.match(lines[i]) and not OL_RE.match(lines[i]):
            paragraph.append(lines[i].strip())
            i += 1
        if paragraph:
            joined = ' '.join(paragraph)
            image_match = STANDALONE_IMAGE_RE.match(joined)
            if image_match:
                alt, src_url = image_match.group(1), image_match.group(2)
                parts = ['<figure class="fig">']
                parts.append('<img src="%s" alt="%s">'
                             % (html.escape(src_url, quote=True),
                                html.escape(alt, quote=True)))
                if alt:
                    parts.append('<figcaption>%s</figcaption>'
                                 % decorate_badges(render_inline(alt)))
                parts.append('</figure>')
                out.append(''.join(parts))
            else:
                out.append('<p>%s</p>' % decorate_badges(render_inline(joined)))

    return '\n'.join(out), toc


def build_toc(entries):
    if not entries:
        return ''
    items = []
    for level, anchor, text in entries:
        items.append('<li class="toc-l%d"><a href="#%s">%s</a></li>'
                     % (level, anchor, html.escape(text)))
    return '<nav class="toc"><h2>目录</h2><ul>%s</ul></nav>' % ''.join(items)


def read_meta(lines):
    """Pull title, version and date out of the leading metadata lines."""
    title, version, date = None, None, None
    for line in lines[:12]:
        heading = HEADING_RE.match(line)
        if heading and len(heading.group(1)) == 1 and title is None:
            title = heading.group(2).strip()
        bold = re.match(r'^\*\*(版本|日期|Version)\*\*[：:]\s*(.+)$', line.strip())
        if bold:
            value = bold.group(2).strip()
            if bold.group(1) in ('版本', 'Version'):
                version = value
            else:
                date = value
        if re.match(r'^\*\*版本\*\*', line.strip()) and version is None:
            version = line.strip()
    return title or 'Untitled Report', version, date


TEMPLATE = u"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{
  --fg: #1a1a1a; --fg-soft: #4a4a4a; --bg: #ffffff; --bg-soft: #f6f7f9;
  --border: #e3e6ea; --accent: #b8442e; --code-bg: #f4f5f7;
  --c: #1f7a4d; --cstar: #2563a8; --s: #a86b1f; --p: #7a4fa3; --q: #a33a3a;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --fg: #e6e6e6; --fg-soft: #a8a8a8; --bg: #14161a; --bg-soft: #1b1e24;
    --border: #2c313a; --accent: #e0705a; --code-bg: #1e2229;
    --c: #58c08a; --cstar: #6aa8e0; --s: #d8a45a; --p: #b088d8; --q: #e07a7a;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue",
               "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  font-size: 16px; line-height: 1.75; -webkit-font-smoothing: antialiased;
}}
.layout {{ display: flex; max-width: 1400px; margin: 0 auto; }}
.toc {{
  width: 280px; flex: 0 0 280px; position: sticky; top: 0; align-self: flex-start;
  max-height: 100vh; overflow-y: auto; padding: 32px 20px 32px 28px;
  border-right: 1px solid var(--border); font-size: 13.5px;
}}
.toc h2 {{
  font-size: 12px; letter-spacing: .12em; text-transform: uppercase;
  color: var(--fg-soft); margin: 0 0 12px; font-weight: 600;
}}
.toc ul {{ list-style: none; margin: 0; padding: 0; }}
.toc li {{ margin: 0; }}
.toc a {{
  display: block; padding: 5px 0; color: var(--fg-soft); text-decoration: none;
  border-left: 2px solid transparent; padding-left: 10px;
}}
.toc a:hover {{ color: var(--accent); border-left-color: var(--accent); }}
.toc-l1 a {{ font-weight: 600; color: var(--fg); }}
.toc-l2 a {{ padding-left: 10px; }}
.toc-l3 a {{ padding-left: 24px; font-size: 12.5px; }}
main {{ flex: 1 1 auto; min-width: 0; padding: 40px 56px 96px; max-width: 940px; }}
h1 {{
  font-size: 30px; line-height: 1.35; margin: 0 0 8px; font-weight: 650;
  letter-spacing: -.01em;
}}
h2 {{
  font-size: 21px; margin: 44px 0 14px; padding-bottom: 8px; font-weight: 620;
  border-bottom: 1px solid var(--border);
}}
h3 {{ font-size: 17px; margin: 30px 0 10px; font-weight: 600; }}
h4 {{ font-size: 15px; margin: 22px 0 8px; font-weight: 600; color: var(--fg-soft); }}
p {{ margin: 0 0 14px; }}
a {{ color: var(--accent); }}
hr {{ border: 0; border-top: 1px solid var(--border); margin: 32px 0; }}
code {{
  font-family: "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
  font-size: .875em; background: var(--code-bg); padding: 2px 5px;
  border-radius: 4px;
}}
pre {{
  background: var(--code-bg); border: 1px solid var(--border); border-radius: 8px;
  padding: 14px 16px; overflow-x: auto; margin: 0 0 18px; line-height: 1.6;
}}
pre code {{ background: none; padding: 0; font-size: 13px; }}
blockquote {{
  margin: 0 0 18px; padding: 12px 18px; background: var(--bg-soft);
  border-left: 3px solid var(--accent); border-radius: 0 6px 6px 0;
  color: var(--fg-soft);
}}
blockquote p {{ margin: 0; }}
ul, ol {{ margin: 0 0 16px; padding-left: 26px; }}
li {{ margin: 5px 0; }}
.table-wrap {{ overflow-x: auto; margin: 0 0 20px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 14.5px; }}
th, td {{
  border: 1px solid var(--border); padding: 9px 12px; text-align: left;
  vertical-align: top;
}}
th {{ background: var(--bg-soft); font-weight: 600; white-space: nowrap; }}
tbody tr:nth-child(even) {{ background: var(--bg-soft); }}
.badge {{
  display: inline-block; font-family: "SF Mono", Menlo, Consolas, monospace;
  font-size: 11px; font-weight: 700; padding: 1px 6px; border-radius: 4px;
  color: #fff; vertical-align: 1px; letter-spacing: .02em;
}}
.badge-c {{ background: var(--c); }}
.badge-cstar {{ background: var(--cstar); }}
.badge-s {{ background: var(--s); }}
.badge-p {{ background: var(--p); }}
.badge-q {{ background: var(--q); }}
figure.fig {{
  margin: 28px auto 20px;
  text-align: center;
}}
figure.fig img {{
  max-width: 100%;
  height: auto;
  border-radius: 6px;
}}
figure.fig figcaption {{
  font-size: 13px;
  color: var(--soft, #666);
  margin-top: 10px;
  line-height: 1.5;
}}
.mermaid {{
  background: var(--bg-soft); border: 1px solid var(--border); border-radius: 8px;
  padding: 20px; margin: 0 0 20px; text-align: center; overflow-x: auto;
}}
.mermaid-fallback {{
  text-align: left; font-family: "SF Mono", Menlo, Consolas, monospace;
  font-size: 12.5px; white-space: pre-wrap; color: var(--fg-soft);
}}
.doc-meta {{
  display: flex; flex-wrap: wrap; gap: 10px; margin: 0 0 28px;
  font-size: 13px; color: var(--fg-soft);
}}
.doc-meta span {{
  background: var(--bg-soft); border: 1px solid var(--border);
  padding: 3px 10px; border-radius: 20px;
}}
@media (max-width: 1000px) {{
  .toc {{ display: none; }}
  main {{ padding: 28px 20px 64px; }}
}}
@media print {{
  .toc {{ display: none; }}
  main {{ max-width: none; padding: 0; }}
  a {{ color: var(--fg); text-decoration: none; }}
}}
</style>
</head>
<body>
<div class="layout">
{toc}
<main>
<h1>{title}</h1>
{meta}
{body}
</main>
</div>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"
        onerror="window.__mermaidMissing=true"></script>
<script>
(function () {{
  var nodes = document.querySelectorAll('.mermaid');
  if (!nodes.length) return;
  function fallback() {{
    nodes.forEach(function (n) {{
      if (n.getAttribute('data-processed')) return;
      var pre = document.createElement('pre');
      pre.className = 'mermaid-fallback';
      pre.textContent = n.textContent;
      n.textContent = '';
      n.appendChild(pre);
    }});
  }}
  if (window.__mermaidMissing || typeof mermaid === 'undefined') {{ fallback(); return; }}
  try {{
    mermaid.initialize({{ startOnLoad: false, theme: 'neutral', securityLevel: 'strict' }});
    mermaid.run({{ nodes: nodes }}).catch(fallback);
  }} catch (e) {{ fallback(); }}
}})();
</script>
</body>
</html>
"""


def convert(source_path, output_path):
    with open(source_path, 'r', encoding='utf-8') as handle:
        raw = handle.read()
    lines = raw.split('\n')

    body, toc_entries = parse(lines)
    title, version, date = read_meta(lines)

    chips = []
    if version:
        chips.append('<span>%s</span>' % html.escape(version))
    if date:
        chips.append('<span>%s</span>' % html.escape(date))
    chips.append('<span>由 %s 生成</span>' % html.escape(os.path.basename(source_path)))
    meta = '<div class="doc-meta">%s</div>' % ''.join(chips)

    document = TEMPLATE.format(
        title=html.escape(title),
        toc=build_toc(toc_entries),
        meta=meta,
        body=body,
    )

    with open(output_path, 'w', encoding='utf-8') as handle:
        handle.write(document)
    return title, len(toc_entries)


def main():
    parser = argparse.ArgumentParser(description='Convert a markdown report to styled HTML.')
    parser.add_argument('source', help='input .md file')
    parser.add_argument('-o', '--output', help='output .html file (default: alongside source)')
    args = parser.parse_args()

    if not os.path.isfile(args.source):
        sys.stderr.write('source not found: %s\n' % args.source)
        return 1

    output = args.output or os.path.splitext(args.source)[0] + '.html'
    title, sections = convert(args.source, output)
    sys.stdout.write('ok: %s -> %s (%d TOC entries)\n' % (args.source, output, sections))
    return 0


if __name__ == '__main__':
    sys.exit(main())
