#!/usr/bin/env python3
"""Validate the fixed structure for Chinese technical research reports.

Two structure generations are recognized:

* current structure (2026-10-10 版): 摘要 / 背景与现状 / 技术详解 / (故障定位速查) /
  总结与展望 / 参考来源 / 附录 A-C / (附录 D)，正文承载技术内容，过程性材料进附录，
  正文禁用 Meta 词汇与证据标记；
* legacy structure (2026-10-10 前): frozen. Only the generic checks run
  (metadata / sources / figures / tables / open markers) so that historical
  reports are not blocked by the new rules.

This validator deliberately uses only the Python standard library so it can run
in the same lightweight environments as the document publishing scripts.
"""

from __future__ import print_function

import argparse
import json
import os
import re
import sys
from urllib.parse import unquote


# ---------------------------------------------------------------------------
# 当前固定结构（2026-10-10 版）
# ---------------------------------------------------------------------------

ABSTRACT_TITLE = "摘要"
BACKGROUND_TITLE = "背景与现状"
DEEP_DIVE_TITLE_RE = re.compile(r"^技术详解(：.+)?$")
FAULT_TITLE_RE = re.compile(r"^故障")
OUTLOOK_TITLE = "总结与展望"
REFERENCE_TITLE = "参考来源"
REQUIRED_APPENDICES = (
    "附录 A：主要结论与依据对照",
    "附录 B：检查与验收清单",
    "附录 C：研究方法与局限",
)

# 旧版固定结构（冻结识别用）。历史报告命中其一即按冻结处理。
LEGACY_H2_DOMESTIC = (
    "版本历史",
    "术语与缩略语",
    "可靠性标记",
    "1. 核心判断（TL;DR）",
    "2. 问题、范围与方法",
    "3. 全球技术基线",
    "4. 国内发展、差距与机会",
    "5. 关键机制深挖",
    "6. 演进方向与情景",
    "7. 建议与验收",
    "8. 不确定性与研究限制",
    "参考来源",
    "附录：研究方法",
)

LEGACY_H2_GENERAL = (
    "版本历史",
    "术语与缩略语",
    "可靠性标记",
    "1. 核心判断（TL;DR）",
    "2. 问题、范围与方法",
    "3. 技术基线",
    "4. 关键机制深挖",
    "5. 演进方向与情景",
    "6. 建议与验收",
    "7. 不确定性与研究限制",
    "参考来源",
    "附录：研究方法",
)

METADATA_FIELDS = (
    "文档类型",
    "版本",
    "状态",
    "密级",
    "作者",
    "生成日期",
    "研究截点",
    "目标读者",
    "调研问题",
    "覆盖范围",
    "排除范围",
)

PROFILES = {
    "technical-research": {"label": "档位 A（含国内小节）", "domestic": True},
    "technical-research-general": {"label": "档位 B（通用）", "domestic": False},
}

# 正文禁用的 Meta 词汇（2026-10-10 语言规范）。报告正文只承载技术内容，
# 过程性表述与证据标记一律改写或移入附录。
BANNED_META_TOKENS = (
    ("【C】", "删除【C】等标记前缀；来源用 [Snn] 与自然句式交代"),
    ("【C*】", "删除【C*】等标记前缀；来源用 [Snn] 与自然句式交代"),
    ("【S】", "删除【S】等标记前缀；来源用 [Snn] 与自然句式交代"),
    ("【P】", "删除【P】等标记前缀；来源用 [Snn] 与自然句式交代"),
    ("【?】", "删除【?】等标记前缀；来源用 [Snn] 与自然句式交代"),
    ("主张—证据", "“主张—证据”改为“主要结论与依据对照”并移入附录 A"),
    ("证据", "“证据”写为依据/来源/源码/实测；方法讨论移入附录 C"),
    ("可证伪", "“可证伪”写为“可验证的”"),
    ("可靠性标记", "删除可靠性标记体系"),
    ("TL;DR", "“TL;DR”写为“摘要”"),
    ("契约", "“契约”写为约定/接口/要求"),
)

# 摘要要点、技术详解与各章节的深度门槛（2026-10-10 起）。
SUMMARY_BULLET_MIN_HAN = 40
DEEP_DIVE_MIN_COUNT = 3
DEEP_DIVE_MIN_HAN = 800
DEEP_DIVE_TOTAL_MIN_HAN = 4000
DEEP_DIVE_MIN_SOURCES = 2
DEEP_DIVE_MIN_ANCHORS = 12
DEEP_DIVE_MIN_SOURCE_ANCHORS = 2
DEEP_DIVE_MIN_CODESPANS = 2
DEEP_DIVE_TOTAL_MIN_SOURCE_ANCHORS = 12
DEEP_DIVE_TOTAL_MIN_FENCES = 2
BACKGROUND_MIN_HAN = 600
BACKGROUND_MIN_ANCHORS = 8
DOMESTIC_MIN_HAN = 260
OUTLOOK_MIN_HAN = 400
FAULT_MIN_HAN = 260
APPENDIX_C_MIN_HAN = 260

HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
SOURCE_ID_RE = re.compile(r"\[S\d{2,}\]")
SOURCE_TOKEN_RE = re.compile(r"\[S[^\]\s]*\]")
BULLET_RE = re.compile(r"^[ \t]*[-*+][ \t]+(.+?)\s*$")
IMAGE_RE = re.compile(
    r"!\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)"
)
CAPTION_RE = re.compile(r"^\s*(?:\*{1,2}|_{1,2})?\s*图\s*(\d+)\s*：")
TODO_RE = re.compile(
    r"\b(?:TODO|TBD|FIXME|XXX)\b|待补充|待确认|待完善|待定", re.IGNORECASE
)
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3007]")

# 源码级锚点：用于强制机制章节落到可定位的具体事实，而不是概念名词堆叠。
ANCHOR_FUNC_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}\(\)")
ANCHOR_FILE_RE = re.compile(
    r"[A-Za-z0-9_./-]+"
    r"\.(?:c|h|S|lds|dts|dtsi|dtso|py|sh|rst|adoc|its|cfg|conf|yaml|yml|toml|json|txt|md|mk|rs|go|ts|js|xml|ini|defconfig)\b"
)
ANCHOR_REG_RE = re.compile(r"\b[A-Z][A-Z0-9_]{3,}\b")
ANCHOR_FIELD_RE = re.compile(r"\b[a-z][a-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*\b")
CODESPAN_RE = re.compile(r"`([^`\n]+)`")
ORDERED_STEP_RE = re.compile(r"^[ \t]*(?:\d+[.、)]|[①②③④⑤⑥⑦⑧⑨⑩])")
ANCHOR_URL_HINTS = ("://", "github.com", "git.kernel.org", "docs.kernel.org", "www.", "blob/")


class UsageError(Exception):
    """Raised instead of argparse's default exit code 2 for bad usage."""


class ResearchArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def _error(errors, rule, line, message):
    errors.append("%s:%d:%s" % (rule, max(0, int(line)), message))


def _without_fenced_code(text):
    """Blank fenced-code lines while retaining original line numbers."""
    clean = []
    fence_char = None
    fence_width = 0
    for line in text.splitlines():
        match = FENCE_RE.match(line)
        if fence_char is not None:
            clean.append("")
            if match and match.group(1)[0] == fence_char and len(match.group(1)) >= fence_width:
                fence_char = None
                fence_width = 0
            continue
        if match:
            fence = match.group(1)
            fence_char = fence[0]
            fence_width = len(fence)
            clean.append("")
            continue
        clean.append(line)
    return clean


def _heading_records(lines):
    records = []
    for index, line in enumerate(lines):
        match = HEADING_RE.match(line)
        if not match:
            continue
        title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2)).strip()
        records.append((len(match.group(1)), title, index + 1))
    return records


def _section_bounds(headings, title, level=2, total_lines=0):
    """Return one-based inclusive/exclusive content bounds for a heading."""
    for position, (heading_level, heading_title, line_number) in enumerate(headings):
        if heading_level == level and heading_title == title:
            end = total_lines + 1
            for next_level, _next_title, next_line in headings[position + 1 :]:
                if next_level <= level:
                    end = next_line
                    break
            return line_number + 1, end
    return None


def _section_bounds_re(headings, pattern, total_lines=0):
    """Like _section_bounds but matches the level-2 title against a regex.

    Returns (title, start, end) or None.
    """
    for position, (heading_level, heading_title, line_number) in enumerate(headings):
        if heading_level == 2 and pattern.match(heading_title):
            end = total_lines + 1
            for next_level, _next_title, next_line in headings[position + 1 :]:
                if next_level <= 2:
                    end = next_line
                    break
            return heading_title, line_number + 1, end
    return None


def _table_cells(line):
    stripped = line.strip()
    if "|" not in stripped:
        return None
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_table_separator(line):
    cells = _table_cells(line)
    if not cells or len(cells) < 2:
        return False
    return all(re.match(r"^:?-{3,}:?$", cell) is not None for cell in cells)


def _find_line(lines, token):
    for index, line in enumerate(lines):
        if token in line:
            return index + 1
    return 1


def _caption_context(lines, index):
    """Allow a caption's provenance to occupy its next two prose lines."""
    pieces = [lines[index].strip()]
    for following in range(index + 1, min(len(lines), index + 3)):
        candidate = lines[following].strip()
        if not candidate:
            break
        if candidate.startswith("#") or candidate.startswith("!") or CAPTION_RE.search(candidate):
            break
        pieces.append(candidate)
    return " ".join(pieces)


def _is_relative_local_path(target):
    if not target or target.startswith("#"):
        return False
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("//"):
        return False
    return not os.path.isabs(target)


def _validate_summary(lines, headings, errors):
    """摘要：3–5 个要点，每个 ≥40 汉字且带 [Snn]；不使用任何标记前缀。"""
    bounds = _section_bounds(headings, ABSTRACT_TITLE, total_lines=len(lines))
    if bounds is None:
        _error(errors, "SUMMARY-SECTION", 1, "缺少“摘要”章节")
        return
    start, end = bounds
    bullets = []
    for index in range(start - 1, end - 1):
        match = BULLET_RE.match(lines[index])
        if match:
            bullets.append((index + 1, match.group(1)))
    if not 3 <= len(bullets) <= 5:
        _error(errors, "SUMMARY-COUNT", start - 1, "摘要必须包含 3–5 个项目符号，当前为 %d 个" % len(bullets))
    for line_number, text in bullets:
        if not SOURCE_ID_RE.search(text):
            _error(errors, "SUMMARY-SOURCE", line_number, "摘要要点必须包含 [Snn] 来源 ID")
        han_count = len(HAN_RE.findall(text))
        if han_count < SUMMARY_BULLET_MIN_HAN:
            _error(
                errors,
                "SUMMARY-LENGTH",
                line_number,
                "摘要要点过短（%d 个汉字），至少需要 %d 个汉字；要点应能脱离正文独立成立"
                % (han_count, SUMMARY_BULLET_MIN_HAN),
            )


def _collect_anchors(text):
    """Return (funcs, files, regs, fields, codespans) sets of locatable anchors."""
    funcs = set(ANCHOR_FUNC_RE.findall(text))
    files = set()
    for candidate in ANCHOR_FILE_RE.findall(text):
        if any(hint in candidate for hint in ANCHOR_URL_HINTS):
            continue
        files.add(candidate)
    regs = set(ANCHOR_REG_RE.findall(text))
    fields = set(ANCHOR_FIELD_RE.findall(text))
    codespans = set()
    for span in CODESPAN_RE.findall(text):
        value = span.strip()
        if len(value) >= 4 and re.search(r"[A-Za-z]", value):
            if any(hint in value for hint in ANCHOR_URL_HINTS):
                continue
            codespans.add(value)
    return funcs, files, regs, fields, codespans


def _anchor_union(funcs, files, regs, fields, codespans):
    return funcs | files | regs | fields | codespans


def _source_anchors(funcs, files):
    return funcs | files


def _fence_block_count(raw_lines):
    count = 0
    for line in raw_lines:
        if FENCE_RE.match(line):
            count += 1
    return count // 2


def _has_step_sequence(lines_slice):
    """True when the section exposes a reproducible step chain."""
    arrow_total = sum(line.count("→") for line in lines_slice)
    if arrow_total >= 3:
        return True
    ordered_steps = sum(1 for line in lines_slice if ORDERED_STEP_RE.match(line))
    return ordered_steps >= 3


def _has_markdown_table(lines_slice):
    for index in range(len(lines_slice) - 1):
        if _table_cells(lines_slice[index]) and _is_table_separator(lines_slice[index + 1]):
            return True
    return False


def _validate_background(lines, headings, errors, domestic_required):
    """背景与现状：≥600 汉字、≥8 锚点；档位 A 必须含“国内”三级小节。"""
    bounds = _section_bounds(headings, BACKGROUND_TITLE, total_lines=len(lines))
    if bounds is None:
        _error(errors, "H2-SEQUENCE", 1, "缺少“背景与现状”章节")
        return
    start, end = bounds
    content = "\n".join(lines[start - 1 : end - 1])
    han_count = len(HAN_RE.findall(content))
    if han_count < BACKGROUND_MIN_HAN:
        _error(
            errors,
            "BACKGROUND-LENGTH",
            start - 1,
            "“背景与现状”需要至少 %d 个汉字，当前为 %d 个" % (BACKGROUND_MIN_HAN, han_count),
        )
    if not SOURCE_ID_RE.search(content):
        _error(errors, "BACKGROUND-SOURCE", start - 1, "“背景与现状”至少需要一个 [Snn] 来源")
    funcs, files, regs, fields, codespans = _collect_anchors(content)
    union = _anchor_union(funcs, files, regs, fields, codespans)
    if len(union) < BACKGROUND_MIN_ANCHORS:
        _error(
            errors,
            "BACKGROUND-ANCHORS",
            start - 1,
            "“背景与现状”可定位锚点不足：当前 %d 个（函数名/源码文件/寄存器/字段/行内代码），门槛为 %d"
            % (len(union), BACKGROUND_MIN_ANCHORS),
        )
    domestic = [
        (title, line_number)
        for level, title, line_number in headings
        if level == 3 and start <= line_number < end and "国内" in title
    ]
    if domestic_required and not domestic:
        _error(
            errors,
            "DOMESTIC-SECTION",
            start - 1,
            "档位 A 必须在“背景与现状”下设置标题含“国内”的三级小节",
        )
    if not domestic_required and domestic:
        _error(
            errors,
            "DOMESTIC-SECTION",
            domestic[0][1],
            "档位 B 不含国内小节；若存在真实国内外对照信息量，请改用档位 A",
        )
    for title, line_number in domestic[:1]:
        next_line = end
        for level, _t, following in headings:
            if level == 3 and following > line_number:
                next_line = following
                break
            if level <= 2 and following > line_number:
                next_line = following
                break
        section_lines = lines[line_number:next_line - 1]
        text = "\n".join(section_lines)
        han = len(HAN_RE.findall(text))
        if han < DOMESTIC_MIN_HAN:
            _error(
                errors,
                "DOMESTIC-LENGTH",
                line_number,
                "国内小节“%s”内容不足：当前 %d 个汉字，门槛为 %d" % (title, han, DOMESTIC_MIN_HAN),
            )
        if not SOURCE_ID_RE.search(text):
            _error(errors, "DOMESTIC-SOURCE", line_number, "国内小节“%s”至少需要一个 [Snn] 来源" % title)


def _validate_deep_dives(lines, headings, errors, raw_lines):
    """技术详解：全章与逐小节的源码级深度门槛。"""
    found = _section_bounds_re(headings, DEEP_DIVE_TITLE_RE, total_lines=len(lines))
    if found is None:
        _error(errors, "DEEP-DIVE-SECTION", 1, "缺少“技术详解”章节")
        return
    section_title, start, end = found
    chapter_text = "\n".join(lines[start - 1:end - 1])
    chapter_han = len(HAN_RE.findall(chapter_text))
    if chapter_han < DEEP_DIVE_TOTAL_MIN_HAN:
        _error(
            errors,
            "DEEP-DIVE-TOTAL-LENGTH",
            start - 1,
            "“%s”整体过薄：当前 %d 个汉字，专家级门槛为 %d；应逐个机制给出源码级路径而非压缩成概览"
            % (section_title, chapter_han, DEEP_DIVE_TOTAL_MIN_HAN),
        )
    c_funcs, c_files, c_regs, c_fields, c_spans = _collect_anchors(chapter_text)
    chapter_sources = _source_anchors(c_funcs, c_files)
    if len(chapter_sources) < DEEP_DIVE_TOTAL_MIN_SOURCE_ANCHORS:
        _error(
            errors,
            "DEEP-DIVE-TOTAL-ANCHORS",
            start - 1,
            "“%s”可定位源码锚点（函数名/源码文件）共 %d 个，门槛为 %d；请以源码级材料重写机制小节"
            % (section_title, len(chapter_sources), DEEP_DIVE_TOTAL_MIN_SOURCE_ANCHORS),
        )
    chapter_fences = _fence_block_count(raw_lines[start - 1:end - 1])
    if chapter_fences < DEEP_DIVE_TOTAL_MIN_FENCES:
        _error(
            errors,
            "DEEP-DIVE-TOTAL-FENCES",
            start - 1,
            "“%s”只有 %d 段围栏代码块，门槛为 %d；请给出逐字源码片段、关键日志或可复制的命令记录"
            % (section_title, chapter_fences, DEEP_DIVE_TOTAL_MIN_FENCES),
        )
    deep_dives = []
    for level, title, line_number in headings:
        if level == 3 and start <= line_number < end:
            deep_dives.append((title, line_number))
    if len(deep_dives) < DEEP_DIVE_MIN_COUNT:
        _error(
            errors,
            "DEEP-DIVE-COUNT",
            start - 1,
            "技术详解至少需要 %d 个三级小节，当前为 %d 个" % (DEEP_DIVE_MIN_COUNT, len(deep_dives)),
        )
    for position, (title, line_number) in enumerate(deep_dives):
        next_line = end
        if position + 1 < len(deep_dives):
            next_line = deep_dives[position + 1][1]
        section_lines = lines[line_number:next_line - 1]
        text = "\n".join(section_lines)
        han_count = len(HAN_RE.findall(text))
        if han_count < DEEP_DIVE_MIN_HAN:
            _error(
                errors,
                "DEEP-DIVE-LENGTH",
                line_number,
                "机制小节“%s”内容不足：当前 %d 个汉字，门槛为 %d；请补充调用链、寄存器/字段细节、失败模式与逐字片段"
                % (title, han_count, DEEP_DIVE_MIN_HAN),
            )
        sources = set(SOURCE_ID_RE.findall(text))
        if len(sources) < DEEP_DIVE_MIN_SOURCES:
            _error(
                errors,
                "DEEP-DIVE-SOURCES",
                line_number,
                "机制小节“%s”仅引用 %d 个来源，至少需要 %d 个不同的 [Snn]"
                % (title, len(sources), DEEP_DIVE_MIN_SOURCES),
            )
        funcs, files, regs, fields, codespans = _collect_anchors(text)
        union = _anchor_union(funcs, files, regs, fields, codespans)
        if len(union) < DEEP_DIVE_MIN_ANCHORS:
            _error(
                errors,
                "DEEP-DIVE-ANCHORS",
                line_number,
                "机制小节“%s”可定位锚点不足：当前 %d 个（函数名/源码文件/寄存器/字段/行内代码），门槛为 %d"
                % (title, len(union), DEEP_DIVE_MIN_ANCHORS),
            )
        source_anchors = _source_anchors(funcs, files)
        if len(source_anchors) < DEEP_DIVE_MIN_SOURCE_ANCHORS:
            _error(
                errors,
                "DEEP-DIVE-SOURCE-ANCHORS",
                line_number,
                "机制小节“%s”缺少源码级锚点：函数名或源码文件路径仅 %d 个，至少需要 %d 个（如 `sbi_init()`、`lib/sbi/sbi_init.c`）"
                % (title, len(source_anchors), DEEP_DIVE_MIN_SOURCE_ANCHORS),
            )
        if len(codespans) < DEEP_DIVE_MIN_CODESPANS:
            _error(
                errors,
                "DEEP-DIVE-CODESPANS",
                line_number,
                "机制小节“%s”行内代码片段仅 %d 处，至少需要 %d 处（错误串、寄存器名、命令或参数应写成 `...`）"
                % (title, len(codespans), DEEP_DIVE_MIN_CODESPANS),
            )
        if not _has_step_sequence(section_lines):
            _error(
                errors,
                "DEEP-DIVE-SEQUENCE",
                line_number,
                "机制小节“%s”缺少步骤序列：请给出可复述的调用链（≥3 个环节，如 `A() → B() → C()`）或编号步骤"
                % title,
            )
        has_basis = bool(re.search(r"接口|API|ABI|协议", text, re.IGNORECASE)) and bool(
            re.search(r"实现|依据|规范|源码|版本", text)
        )
        has_boundary = bool(re.search(r"失效边界|失败边界|边界条件|故障|异常|限制", text))
        has_validation = bool(re.search(r"验证条件|验收条件|验证|测试条件|复现|测试", text))
        has_tradeoff = bool(re.search(r"成本|权衡|取舍|代价|开销|资源消耗", text, re.IGNORECASE))
        missing = []
        if not has_basis:
            missing.append("实现与接口依据")
        if not has_boundary:
            missing.append("失效边界")
        if not has_validation:
            missing.append("验证条件")
        if not has_tradeoff:
            missing.append("成本与权衡")
        if missing:
            _error(
                errors,
                "DEEP-DIVE-FIELDS",
                line_number,
                "机制小节“%s”缺少%s" % (title, "、".join(missing)),
            )


def _validate_simple_section(lines, headings, errors, title, min_han, rule_prefix, need_source=True):
    bounds = _section_bounds(headings, title, total_lines=len(lines))
    if bounds is None:
        return False
    start, end = bounds
    content = "\n".join(lines[start - 1 : end - 1])
    han_count = len(HAN_RE.findall(content))
    if han_count < min_han:
        _error(
            errors,
            rule_prefix + "-LENGTH",
            start - 1,
            "“%s”需要至少 %d 个汉字，当前为 %d 个" % (title, min_han, han_count),
        )
    if need_source and not SOURCE_ID_RE.search(content):
        _error(errors, rule_prefix + "-SOURCE", start - 1, "“%s”至少需要一个 [Snn] 来源" % title)
    return True


def _validate_appendices(lines, headings, errors, appendix_titles):
    """附录 A/B 需含表格与来源；附录 C 记录方法与局限。"""
    for required_title in REQUIRED_APPENDICES:
        if required_title not in appendix_titles:
            _error(
                errors,
                "H2-SEQUENCE",
                1,
                "参考来源之后缺少“%s”章节" % required_title,
            )
    for title in REQUIRED_APPENDICES[:2]:
        bounds = _section_bounds(headings, title, total_lines=len(lines))
        if bounds is None:
            continue
        start, end = bounds
        content_lines = lines[start - 1 : end - 1]
        content = "\n".join(content_lines)
        if not _has_markdown_table(content_lines):
            _error(errors, "APPENDIX-TABLE", start - 1, "“%s”必须包含一个 Markdown 表格" % title)
        if not SOURCE_ID_RE.search(content):
            _error(errors, "APPENDIX-SOURCE", start - 1, "“%s”表格条目需要 [Snn] 来源" % title)
    _validate_simple_section(
        lines, headings, errors, REQUIRED_APPENDICES[2], APPENDIX_C_MIN_HAN, "APPENDIX-C", need_source=False
    )


def _validate_meta_language(lines, headings, errors, main_body_end):
    """正文（参考来源之前）禁用 Meta 词汇与证据标记。"""
    body = lines[: main_body_end - 1]
    for token, hint in BANNED_META_TOKENS:
        hits = [index + 1 for index, line in enumerate(body) if token in line]
        if hits:
            _error(
                errors,
                "META-LANGUAGE",
                hits[0],
                "正文出现 Meta 词汇“%s”（共 %d 处）：%s" % (token, len(hits), hint),
            )


def validate_report(report_path, profile="technical-research"):
    """Return a JSON-serializable validation result or raise an I/O exception."""
    with open(report_path, "r", encoding="utf-8-sig") as handle:
        raw_text = handle.read()
    raw_lines = raw_text.splitlines()
    lines = _without_fenced_code(raw_text)

    errors = []
    warnings = []
    headings = _heading_records(lines)

    first_nonblank = None
    for index, line in enumerate(lines):
        if line.strip():
            first_nonblank = index + 1
            break
    if first_nonblank is None:
        _error(errors, "H1-FIRST", 1, "报告为空，第一处非空行必须是一级标题")
    else:
        match = HEADING_RE.match(lines[first_nonblank - 1])
        if not match or len(match.group(1)) != 1:
            _error(errors, "H1-FIRST", first_nonblank, "第一处非空行必须是一级标题")

    h2_records = [(title, line_number) for level, title, line_number in headings if level == 2]
    actual_h2 = [title for title, _line_number in h2_records]

    metadata = {}
    for line in lines:
        cells = _table_cells(line)
        if cells and len(cells) >= 2:
            metadata[cells[0]] = cells[1]
    for field in METADATA_FIELDS:
        if field not in metadata:
            _error(errors, "META-FIELD", 1, "元数据表缺少“%s”字段" % field)
    document_type = metadata.get("文档类型", "").strip()
    if document_type != "技术调研报告":
        _error(errors, "META-TYPE", _find_line(lines, "文档类型"), "文档类型必须为“技术调研报告”")

    table_count = 0
    for index in range(len(lines) - 1):
        if _table_cells(lines[index]) and _is_table_separator(lines[index + 1]):
            table_count += 1
    if table_count < 4:
        _error(errors, "TABLE-COUNT", 1, "至少需要 4 个 Markdown 表格，当前为 %d 个" % table_count)

    reference_bounds = _section_bounds(headings, REFERENCE_TITLE, total_lines=len(lines))
    source_ledger = set()
    reference_start = len(lines) + 1
    if reference_bounds is None:
        _error(errors, "SOURCE-LEDGER", 1, "缺少“参考来源”章节中的来源 ID 台账")
    else:
        reference_start, reference_end = reference_bounds
        for index in range(reference_start - 1, reference_end - 1):
            source_ledger.update(SOURCE_ID_RE.findall(lines[index]))
        if not source_ledger:
            _error(errors, "SOURCE-LEDGER", reference_start - 1, "参考来源章节必须包含 [Snn] 来源 ID 台账")

    cited_sources = set()
    first_citation_line = {}
    for index, line in enumerate(lines):
        for source_id in SOURCE_ID_RE.findall(line):
            cited_sources.add(source_id)
            first_citation_line.setdefault(source_id, index + 1)
        for source_token in SOURCE_TOKEN_RE.findall(line):
            if not SOURCE_ID_RE.fullmatch(source_token):
                _error(errors, "SOURCE-ID-FORMAT", index + 1, "来源 ID 必须采用 [Snn] 格式：%s" % source_token)
    for source_id in sorted(cited_sources - source_ledger):
        _error(
            errors,
            "SOURCE-UNRESOLVED",
            first_citation_line[source_id],
            "引用 %s 未在参考来源台账中定义" % source_id,
        )

    valid_images = []
    for index, line in enumerate(lines):
        for match in IMAGE_RE.finditer(line):
            target = unquote((match.group(1) or match.group(2) or "").strip())
            if _is_relative_local_path(target):
                local_path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(report_path)), target))
                if os.path.isfile(local_path):
                    valid_images.append((index + 1, target))
    if len(valid_images) < 3:
        _error(
            errors,
            "FIGURE-LOCAL",
            valid_images[0][0] if valid_images else 1,
            "至少需要 3 张路径存在的相对本地图片，当前为 %d 张" % len(valid_images),
        )

    captions = []
    for index, line in enumerate(lines):
        match = CAPTION_RE.search(line)
        if match:
            captions.append((match.group(1), index + 1, _caption_context(lines, index)))
    if len(captions) < 3:
        _error(errors, "FIGURE-CAPTION", 1, "至少需要 3 条以“图 N：”开头的图注，当前为 %d 条" % len(captions))
    for number, line_number, context in captions:
        if not re.search(r"来源|数据", context) or not SOURCE_ID_RE.search(context):
            _error(
                errors,
                "FIGURE-PROVENANCE",
                line_number,
                "图 %s 图注必须写明来源/数据口径并包含 [Snn]" % number,
            )
        body_reference = re.compile(r"图\s*%s" % re.escape(number))
        caption_like = re.compile(r"^\s*图\s*%s\s*：" % re.escape(number))
        cited_in_body = False
        for index, line in enumerate(lines[: reference_start - 1]):
            if index + 1 == line_number or line.lstrip().startswith("!"):
                continue
            if caption_like.match(line):
                continue
            if body_reference.search(line):
                cited_in_body = True
                break
        if not cited_in_body:
            _error(errors, "FIGURE-BODY-CITATION", line_number, "图 %s 必须在正文中以“见图 %s”等方式引用" % (number, number))

    # 旧版结构（2026-10-10 前）：冻结处理，仅执行通用检查。
    if actual_h2 == list(LEGACY_H2_DOMESTIC) or actual_h2 == list(LEGACY_H2_GENERAL):
        warnings.append(
            "LEGACY:检测到 2026-10-10 前的旧版结构，按冻结处理：仅执行通用检查（元数据/来源/图/表格/未决标记）"
        )
        for index, line in enumerate(lines):
            match = TODO_RE.search(line)
            if match:
                _error(errors, "TODO", index + 1, "发现未解决标记“%s”" % match.group(0))
        return {"ok": not errors, "errors": errors, "warnings": warnings, "profile": "legacy"}

    # ---- 当前结构（2026-10-10 版） ----
    _validate_summary(lines, headings, errors)

    background_found = _section_bounds(headings, BACKGROUND_TITLE, total_lines=len(lines))
    deep_found = _section_bounds_re(headings, DEEP_DIVE_TITLE_RE, total_lines=len(lines))
    outlook_found = _section_bounds(headings, OUTLOOK_TITLE, total_lines=len(lines))
    fault_found = _section_bounds_re(headings, FAULT_TITLE_RE, total_lines=len(lines))
    ref_index = None
    for index, (title, line_number) in enumerate(h2_records):
        if title == REFERENCE_TITLE:
            ref_index = index
            break

    domestic_present = False
    if background_found is not None:
        bg_start, bg_end = background_found
        domestic_present = any(
            level == 3 and bg_start <= line_number < bg_end and "国内" in title
            for level, title, line_number in headings
        )
    if profile == "auto":
        resolved_name = "technical-research" if domestic_present else "technical-research-general"
    else:
        resolved_name = profile
    domestic_required = PROFILES[resolved_name]["domestic"]

    # 顺序与未识别章节：(摘要) < 背景与现状 < 技术详解 < (故障定位速查) < 总结与展望 < 参考来源 < 附录 A-C (—附录 D…)
    if actual_h2 and actual_h2[0] != ABSTRACT_TITLE:
        _error(errors, "H2-SEQUENCE", h2_records[0][1] if h2_records else 1, "第一个二级标题必须为“摘要”")
    for required, found in ((
        (BACKGROUND_TITLE, background_found),
        ("技术详解", deep_found),
        (OUTLOOK_TITLE, outlook_found),
    )):
        if found is None:
            _error(errors, "H2-SEQUENCE", 1, "缺少“%s”章节" % required)
    body_h2_limit = ref_index if ref_index is not None else len(h2_records)
    allowed_fixed = (ABSTRACT_TITLE, BACKGROUND_TITLE, OUTLOOK_TITLE)
    for index in range(body_h2_limit):
        title, line_number = h2_records[index]
        if title in allowed_fixed or DEEP_DIVE_TITLE_RE.match(title) or FAULT_TITLE_RE.match(title):
            continue
        _error(errors, "H2-SEQUENCE", line_number, "未识别的二级标题“%s”；正文标题只能是 摘要/背景与现状/技术详解/故障定位速查/总结与展望" % title)
    order_positions = []
    if actual_h2 and actual_h2[0] == ABSTRACT_TITLE:
        order_positions.append(("摘要", 0))
    if background_found is not None:
        order_positions.append(("背景与现状", h2_records.index((BACKGROUND_TITLE, background_found[0] - 1))))
    if deep_found is not None:
        order_positions.append(("技术详解", h2_records.index((deep_found[0], deep_found[1] - 1))))
    if fault_found is not None:
        order_positions.append(("故障定位速查", h2_records.index((fault_found[0], fault_found[1] - 1))))
    if outlook_found is not None:
        order_positions.append(("总结与展望", h2_records.index((OUTLOOK_TITLE, outlook_found[0] - 1))))
    if ref_index is not None:
        order_positions.append(("参考来源", ref_index))
    positions = [position for _title, position in order_positions]
    if positions != sorted(positions):
        _error(
            errors,
            "H2-SEQUENCE",
            h2_records[0][1] if h2_records else 1,
            "二级标题顺序必须为：摘要 < 背景与现状 < 技术详解 < 故障定位速查（可选）< 总结与展望 < 参考来源",
        )

    appendix_titles = []
    if ref_index is not None:
        appendix_titles = [title for title, _line in h2_records[ref_index + 1 :]]
        for offset, expected in enumerate(REQUIRED_APPENDICES):
            if offset >= len(appendix_titles):
                break
            if appendix_titles[offset] != expected:
                line = h2_records[ref_index + 1 + offset][1]
                _error(
                    errors,
                    "H2-SEQUENCE",
                    line,
                    "附录顺序错误：第 %d 个附录应为“%s”，当前为“%s”" % (offset + 1, expected, appendix_titles[offset]),
                )
        for extra in appendix_titles[len(REQUIRED_APPENDICES):]:
            if not extra.startswith("附录"):
                _error(errors, "H2-SEQUENCE", 1, "参考来源之后的章节“%s”必须为附录" % extra)

    _validate_background(lines, headings, errors, domestic_required)
    _validate_deep_dives(lines, headings, errors, raw_lines)
    if fault_found is not None:
        _validate_simple_section(lines, headings, errors, fault_found[0], FAULT_MIN_HAN, "FAULT")
    _validate_simple_section(lines, headings, errors, OUTLOOK_TITLE, OUTLOOK_MIN_HAN, "OUTLOOK")
    if appendix_titles:
        _validate_appendices(lines, headings, errors, appendix_titles)

    main_body_end = reference_start
    _validate_meta_language(lines, headings, errors, main_body_end)

    for index, line in enumerate(lines):
        match = TODO_RE.search(line)
        if match:
            _error(errors, "TODO", index + 1, "发现未解决标记“%s”" % match.group(0))

    return {"ok": not errors, "errors": errors, "warnings": warnings, "profile": resolved_name}


def format_text_result(result):
    lines_out = []
    if result["ok"]:
        label = PROFILES.get(result.get("profile", ""), {}).get("label", "")
        if result.get("profile") == "legacy":
            lines_out.append("PASS: 技术调研报告校验通过（旧结构冻结，仅通用检查）")
        elif label:
            lines_out.append("PASS: 技术调研报告校验通过（%s）" % label)
        else:
            lines_out.append("PASS: 技术调研报告校验通过")
    else:
        lines_out.extend(result["errors"])
    lines_out.extend("WARNING: %s" % warning for warning in result.get("warnings", []))
    return "\n".join(lines_out)


def _emit(result, as_json):
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(format_text_result(result))


def main(argv=None):
    parser = ResearchArgumentParser(
        prog="validate_research_report.py",
        description="校验中文技术调研报告的固定结构和可追溯性。",
    )
    parser.add_argument("report", help="要校验的 Markdown 报告")
    parser.add_argument(
        "--profile",
        required=True,
        choices=("technical-research", "technical-research-general", "auto"),
        help="技术调研报告结构档位：含国内小节（technical-research）、通用（technical-research-general）或自动识别（auto）",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="输出 JSON 结果")
    try:
        args = parser.parse_args(argv)
    except UsageError as exc:
        result = {"ok": False, "errors": ["USAGE:0:%s" % exc], "warnings": []}
        _emit(result, "--json" in (argv if argv is not None else sys.argv[1:]))
        return 1

    try:
        result = validate_report(args.report, args.profile)
    except (OSError, UnicodeError) as exc:
        result = {"ok": False, "errors": ["IO:0:无法读取报告：%s" % exc], "warnings": []}
        _emit(result, args.as_json)
        return 1

    _emit(result, args.as_json)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
