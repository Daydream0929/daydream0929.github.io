#!/usr/bin/env python3
"""Publish rendered research report HTML to the personal site repository.

The site repository (Daydream0929/daydream0929.github.io, Jekyll + GitHub Pages)
serves standalone report HTML from reports/ and lists them through
_data/reports.yml. This script copies one or more rendered HTML files into the
site repo, upserts their metadata entries, then commits and pushes so GitHub
Actions redeploys the site (roughly one minute).

Single report:
    python3 publish_site.py reports/foo.html --summary "一句话摘要" --tags RISC-V,Linux

Bulk (manifest: YAML list of {file, title?, summary?, tags?, date?}):
    python3 publish_site.py --manifest .skillsearch/reports-manifest.yml

Options:
    --site PATH   site repository path (default: env TECH_REPORT_SITE or
                  ~/github/daydream0929.github.io)
    --date DATE   publish date YYYY-MM-DD (default: today)
    --no-push     commit locally without pushing
    --dry-run     show planned actions without writing anything
"""

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys

import yaml

DEFAULT_SITE = os.path.expanduser(
    os.environ.get("TECH_REPORT_SITE", "~/github/daydream0929.github.io"))
DATA_REL = os.path.join("_data", "reports.yml")
HEADER = ("# 技术调研报告集数据；由 document skill 的 publish_site.py 维护，"
          "按 id 合并条目，字段顺序 id/title/summary/date/tags/url。\n")
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)


def read_title(path):
    text = open(path, encoding="utf-8", errors="replace").read(4096 * 4)
    match = TITLE_RE.search(text)
    return match.group(1).strip() if match else os.path.splitext(os.path.basename(path))[0]


def normalize_tags(raw):
    if raw is None:
        return []
    if isinstance(raw, str):
        return [t.strip() for t in raw.split(",") if t.strip()]
    return [str(t).strip() for t in raw if str(t).strip()]


def load_entries(data_path):
    if not os.path.exists(data_path):
        return []
    with open(data_path, encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    return loaded if isinstance(loaded, list) else []


def upsert_entry(entries, entry):
    for index, old in enumerate(entries):
        if old.get("id") == entry["id"]:
            merged = dict(old)
            for key, value in entry.items():
                if value not in (None, "", []) or key not in merged:
                    merged[key] = value
            ordered = {key: merged[key] for key in
                       ("id", "title", "summary", "date", "tags", "url")
                       if key in merged}
            ordered.update({k: v for k, v in merged.items() if k not in ordered})
            entries[index] = ordered
            return "updated"
    entries.append(entry)
    return "added"


def build_items(args):
    if args.manifest:
        manifest_path = os.path.abspath(args.manifest)
        with open(manifest_path, encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        if not isinstance(raw, list) or not raw:
            sys.exit("manifest 必须是非空的 YAML 列表")
        base = os.path.dirname(manifest_path)
        items = []
        for record in raw:
            html = str(record.get("file", "")).strip()
            if not html:
                sys.exit("manifest 条目缺少 file 字段: %r" % record)
            path = html if os.path.isabs(html) else os.path.abspath(html)
            if not os.path.exists(path):
                path = os.path.join(base, html)
            items.append({
                "file": path,
                "title": record.get("title"),
                "summary": record.get("summary"),
                "date": record.get("date"),
                "tags": record.get("tags"),
            })
        return items

    if len(args.html) != 1:
        sys.exit("单份发布只接受 1 个 HTML 文件；批量请使用 --manifest")
    path = os.path.abspath(args.html[0])
    return [{
        "file": path,
        "title": args.title,
        "summary": args.summary,
        "date": args.date,
        "tags": args.tags,
    }]


def git(*cmd, cwd):
    return subprocess.run(["git"] + list(cmd), cwd=cwd,
                          capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(
        description="Publish rendered report HTML to the personal site repo.")
    parser.add_argument("html", nargs="*", help="rendered report HTML (single file)")
    parser.add_argument("--manifest", help="YAML manifest for bulk publish")
    parser.add_argument("--title", help="override <title> (single-file mode)")
    parser.add_argument("--summary", help="one-line summary for the index page")
    parser.add_argument("--tags", help="comma separated tags, e.g. RISC-V,Linux")
    parser.add_argument("--date", help="publish date YYYY-MM-DD (default: today)")
    parser.add_argument("--site", default=DEFAULT_SITE, help="site repo path")
    parser.add_argument("--no-push", action="store_true", help="commit without pushing")
    parser.add_argument("--dry-run", action="store_true", help="preview only")
    args = parser.parse_args()
    if not args.html and not args.manifest:
        parser.error("需要 1 个 HTML 文件或 --manifest")

    site = os.path.abspath(os.path.expanduser(args.site))
    if not os.path.isdir(os.path.join(site, ".git")):
        sys.exit("站点仓库不存在或不是 git 仓库: %s" % site)

    today = datetime.date.today().isoformat()
    items = build_items(args)
    reports_dir = os.path.join(site, "reports")
    data_path = os.path.join(site, DATA_REL)
    entries = load_entries(data_path)

    plan = []
    for item in items:
        src = item["file"]
        if not os.path.isfile(src):
            sys.exit("找不到报告 HTML: %s" % src)
        with open(src, "rb") as handle:
            head = handle.read(4)
        if head.startswith(b"---\n"):
            sys.exit("报告以 YAML front matter 开头，会被 Jekyll 当作页面处理: %s" % src)
        name = os.path.basename(src)
        dst = os.path.join(reports_dir, name)
        entry = {
            "id": os.path.splitext(name)[0],
            "title": item["title"] or read_title(src),
            "summary": item["summary"] or "",
            "date": str(item["date"] or today),
            "tags": normalize_tags(item["tags"]),
            "url": "/reports/" + name,
        }
        state = "new" if not os.path.exists(dst) else (
            "identical" if open(dst, "rb").read() == open(src, "rb").read() else "updated")
        plan.append((src, dst, name, entry, state))

    for src, dst, name, entry, state in plan:
        action = upsert_entry(entries, entry)
        print("%-9s %s  [yml %s]" % (state, name, action))

    if args.dry_run:
        print("dry-run：未写入任何文件")
        return 0

    os.makedirs(reports_dir, exist_ok=True)
    touched = []
    for src, dst, name, _entry, state in plan:
        if state != "identical":
            shutil.copy2(src, dst)
        touched.append("reports/" + name)

    with open(data_path, "w", encoding="utf-8") as handle:
        handle.write(HEADER)
        handle.write(yaml.safe_dump(entries, allow_unicode=True,
                                    sort_keys=False, default_flow_style=False,
                                    width=1000))
    touched.append(DATA_REL)

    check = git("status", "--porcelain", "--", *touched, cwd=site)
    if check.returncode != 0:
        sys.exit("git status 失败: %s" % check.stderr.strip())
    if not check.stdout.strip():
        print("站点仓库无变化，无需提交")
        return 0

    add = git("add", "--", *touched, cwd=site)
    if add.returncode != 0:
        sys.exit("git add 失败: %s" % add.stderr.strip())
    ids = [entry["id"] for _s, _d, _n, entry, _st in plan]
    subject = ("feat(reports): publish %s" % ids[0] if len(ids) == 1
               else "feat(reports): publish %d reports" % len(ids))
    commit = git("commit", "-m", subject, cwd=site)
    if commit.returncode != 0:
        sys.exit("git commit 失败: %s" % commit.stderr.strip())
    print("committed: %s" % subject)

    if args.no_push:
        print("已提交，未推送（--no-push）")
        return 0

    branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=site).stdout.strip()
    push = git("push", "origin", branch, cwd=site)
    if push.returncode != 0:
        print("git push 失败，请手动检查站点仓库:\n%s" % push.stderr.strip(),
              file=sys.stderr)
        return 3
    print("pushed: origin/%s" % branch)
    print("GitHub Actions 约 1 分钟后完成部署：")
    print("  https://daydream0929.github.io/reports/")
    for _src, _dst, name, _entry, _state in plan:
        print("  https://daydream0929.github.io/reports/%s" % name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
