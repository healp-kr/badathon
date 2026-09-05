# -*- coding: utf-8 -*-
"""마크다운 → .docx 변환. **표를 진짜 Word 표로 만든다.**

    python docs/md2docx.py docs/발표_부록.md
    python docs/md2docx.py docs/발표_부록.md -o docs/발표_부록.docx

Notion에 붙일 때는 `.md` 가 정본이고, 이 스크립트는 **한글(HWP)·Word 로 돌려야 하는
제출본**을 만들기 위한 것이다. 파이프 표를 텍스트로 흘려보내지 않고 테두리 있는 표로
변환하며, 헤더 행 음영·굵게, 열 너비 자동, 셀 안의 `**굵게**`·`` `코드` `` 도 살린다.

지원: #~#### 제목 · 파이프 표 · 불릿/번호 목록 · 인용(>) · 코드펜스 · 수평선 ·
      인라인 **굵게**, `코드`, [링크](url)
"""
import argparse
import io
import os
import re
import sys

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm

BODY_FONT = "맑은 고딕"
CODE_FONT = "D2Coding"          # 없으면 Word 가 대체 폰트를 쓴다
CODE_FALLBACK = "Consolas"

HEADER_FILL = "EFEFEF"
CODE_FILL = "F5F5F5"
ACCENT = RGBColor(0x1A, 0x4E, 0x8A)
MUTED = RGBColor(0x66, 0x66, 0x66)


# ------------------------------------------------------------------ 저수준 헬퍼
def _set_font(run, name=BODY_FONT, size=None, bold=None, color=None, mono=False):
    """한글은 eastAsia 폰트를 따로 지정하지 않으면 적용되지 않는다."""
    face = CODE_FALLBACK if mono else name
    run.font.name = face
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    rfonts.set(qn("w:ascii"), face)
    rfonts.set(qn("w:hAnsi"), face)
    rfonts.set(qn("w:eastAsia"), name)          # 한글은 항상 본문 폰트로
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def _shade(element, fill):
    tc_pr = element.get_or_add_tcPr() if hasattr(element, "get_or_add_tcPr") else None
    target = tc_pr if tc_pr is not None else element
    shd = target.makeelement(qn("w:shd"), {})
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    target.append(shd)


def _repeat_header(row):
    """표가 페이지를 넘어갈 때 헤더 행을 반복한다."""
    tr_pr = row._tr.get_or_add_trPr()
    el = tr_pr.makeelement(qn("w:tblHeader"), {})
    el.set(qn("w:val"), "true")
    tr_pr.append(el)


# ------------------------------------------------------------------ 인라인 파싱
INLINE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))")


def _add_inline(paragraph, text, size=10, base_bold=False, color=None):
    """**굵게** · `코드` · [링크](url) 를 런으로 나눠 붙인다."""
    for chunk in INLINE.split(text):
        if not chunk:
            continue
        if chunk.startswith("**") and chunk.endswith("**"):
            run = paragraph.add_run(chunk[2:-2])
            _set_font(run, size=size, bold=True, color=color)
        elif chunk.startswith("`") and chunk.endswith("`"):
            run = paragraph.add_run(chunk[1:-1])
            _set_font(run, size=size - 0.5, bold=base_bold, mono=True,
                      color=color or RGBColor(0xB0, 0x30, 0x30))
        elif chunk.startswith("[") and "](" in chunk:
            label, url = chunk[1:-1].split("](", 1)
            run = paragraph.add_run(label)
            _set_font(run, size=size, bold=base_bold, color=ACCENT)
            run.font.underline = True
            # 각주처럼 URL 을 회색으로 덧붙인다 — 인쇄본에서 링크가 죽지 않게
            tail = paragraph.add_run(f" ({url})")
            _set_font(tail, size=size - 1.5, color=MUTED)
        else:
            run = paragraph.add_run(chunk)
            _set_font(run, size=size, bold=base_bold, color=color)


# ------------------------------------------------------------------ 블록 파싱
def _split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def _is_separator(line):
    return bool(re.fullmatch(r"\|?[\s:\-|]+\|?", line.strip())) and "-" in line


def _blocks(lines):
    """(종류, 페이로드) 스트림으로 자른다."""
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("```"):
            body, i = [], i + 1
            while i < n and not lines[i].strip().startswith("```"):
                body.append(lines[i].rstrip("\n"))
                i += 1
            i += 1
            yield ("code", body)
            continue

        if re.fullmatch(r"-{3,}|\*{3,}|_{3,}", stripped):
            yield ("hr", None)
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            yield ("heading", (len(m.group(1)), m.group(2).strip()))
            i += 1
            continue

        # 표 — 헤더 + 구분선 + 본문
        if stripped.startswith("|") and i + 1 < n and _is_separator(lines[i + 1]):
            header = _split_row(stripped)
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i]))
                i += 1
            yield ("table", (header, rows))
            continue

        if stripped.startswith(">"):
            body = []
            while i < n and lines[i].strip().startswith(">"):
                body.append(lines[i].strip().lstrip(">").strip())
                i += 1
            yield ("quote", body)
            continue

        m = re.match(r"^(\s*)([-*+])\s+(.*)$", raw)
        if m:
            yield ("bullet", (len(m.group(1)) // 2, m.group(3).strip()))
            i += 1
            continue

        m = re.match(r"^(\s*)(\d+)\.\s+(.*)$", raw)
        if m:
            yield ("number", (len(m.group(1)) // 2, m.group(3).strip()))
            i += 1
            continue

        # 이어지는 본문 줄은 한 문단으로 합친다
        body = [stripped]
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if (not nxt or nxt.startswith(("#", "|", ">", "```", "- ", "* "))
                    or re.fullmatch(r"-{3,}", nxt) or re.match(r"^\d+\.\s", nxt)):
                break
            body.append(nxt)
            i += 1
        yield ("para", " ".join(body))


# ------------------------------------------------------------------ 렌더링
HEADING_SPEC = {1: (18, True), 2: (14, True), 3: (11.5, True), 4: (10.5, True)}


def _add_heading(doc, level, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(16 if level <= 2 else 10)
    p.paragraph_format.space_after = Pt(6 if level <= 2 else 3)
    p.paragraph_format.keep_with_next = True
    size, bold = HEADING_SPEC.get(level, (10.5, True))
    color = ACCENT if level <= 2 else None
    _add_inline(p, text, size=size, base_bold=bold, color=color)
    if level <= 2:
        for run in p.runs:
            run.font.bold = True
    if level == 2:
        _bottom_border(p)


def _bottom_border(paragraph):
    p_pr = paragraph._p.get_or_add_pPr()
    borders = p_pr.makeelement(qn("w:pBdr"), {})
    bottom = borders.makeelement(qn("w:bottom"), {})
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "3")
    bottom.set(qn("w:color"), "BBBBBB")
    borders.append(bottom)
    p_pr.append(borders)


def _add_table(doc, header, rows):
    ncol = len(header)
    table = doc.add_table(rows=1, cols=ncol)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = True

    hdr = table.rows[0]
    _repeat_header(hdr)
    for idx, text in enumerate(header):
        cell = hdr.cells[idx]
        cell.text = ""
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(2)
        _add_inline(p, text, size=9, base_bold=True)
        for run in p.runs:
            run.font.bold = True
        _shade(cell._tc, HEADER_FILL)

    for row in rows:
        cells = table.add_row().cells
        for idx in range(ncol):
            text = row[idx] if idx < len(row) else ""
            cell = cells[idx]
            cell.text = ""
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(1)
            if idx > 0 and re.fullmatch(r"[\d.,%+\-~ ]+p?", text.replace("**", "")):
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            _add_inline(p, text, size=9)

    after = doc.add_paragraph()
    after.paragraph_format.space_after = Pt(6)
    return table


def _add_bullet(doc, level, text, numbered=False):
    style = "List Number" if numbered else "List Bullet"
    try:
        p = doc.add_paragraph(style=style)
    except KeyError:
        p = doc.add_paragraph()
        text = ("• " if not numbered else "") + text
    p.paragraph_format.left_indent = Cm(0.6 + 0.5 * level)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(2)
    _add_inline(p, text, size=10)


def _add_quote(doc, body):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.5)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(6)
    p_pr = p._p.get_or_add_pPr()
    borders = p_pr.makeelement(qn("w:pBdr"), {})
    left = borders.makeelement(qn("w:left"), {})
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), "18")
    left.set(qn("w:space"), "8")
    left.set(qn("w:color"), "A0A0A0")
    borders.append(left)
    p_pr.append(borders)
    _add_inline(p, " ".join(body), size=9.5, color=RGBColor(0x44, 0x44, 0x44))


def _add_code(doc, body):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.3)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(8)
    _shade(p._p.get_or_add_pPr(), CODE_FILL)
    for idx, line in enumerate(body):
        if idx:
            p.add_run().add_break()
        run = p.add_run(line)
        _set_font(run, size=9, mono=True)


def _add_hr(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    _bottom_border(p)


def convert(md_path, out_path):
    with io.open(md_path, encoding="utf-8") as f:
        lines = f.read().splitlines()

    doc = Document()

    section = doc.sections[0]
    section.left_margin = Cm(2.0)
    section.right_margin = Cm(2.0)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)

    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(10)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)

    n_tables = 0
    for kind, payload in _blocks(lines):
        if kind == "heading":
            level, text = payload
            _add_heading(doc, level, text)
        elif kind == "table":
            header, rows = payload
            _add_table(doc, header, rows)
            n_tables += 1
        elif kind == "bullet":
            level, text = payload
            _add_bullet(doc, level, text)
        elif kind == "number":
            level, text = payload
            _add_bullet(doc, level, text, numbered=True)
        elif kind == "quote":
            _add_quote(doc, payload)
        elif kind == "code":
            _add_code(doc, payload)
        elif kind == "hr":
            _add_hr(doc)
        elif kind == "para":
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(5)
            _add_inline(p, payload, size=10)

    doc.save(out_path)
    return n_tables


def main():
    ap = argparse.ArgumentParser(description="마크다운을 표가 살아 있는 .docx 로 변환")
    ap.add_argument("md")
    ap.add_argument("-o", "--out")
    args = ap.parse_args()

    out = args.out or os.path.splitext(args.md)[0] + ".docx"
    n = convert(args.md, out)
    print(f"{args.md} → {out}  (표 {n}개)")


if __name__ == "__main__":
    sys.exit(main())
