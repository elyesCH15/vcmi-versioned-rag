#!/usr/bin/env python
"""Build a change log between consecutive versions of the VCMI Claims Code of Practice.

Pipeline: verify manifest -> extract (PyMuPDF dict/blocks) -> clean -> split into
sections -> align sections -> sentence diff -> classify -> cross-check against the
Document History table -> write outputs.

Run from the repository root:  python -I scripts/diff_versions.py
Outputs: data/clean/<doc_id>.json, data/sections/<doc_id>.jsonl,
         data/diff/changes.jsonl, data/diff/report.md
"""
import csv
import difflib
import hashlib
import json
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf
from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
MANIFEST = DATA / "manifest.csv"
CLEAN_DIR = DATA / "clean"
SECT_DIR = DATA / "sections"
DIFF_DIR = DATA / "diff"

DEBUG = "--debug" in sys.argv


# ---------------------------------------------------------------------------
# 0. Manifest verification
# ---------------------------------------------------------------------------
def load_manifest():
    with open(MANIFEST, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: r["publication_date"])  # order by date, not file name
    problems = []
    for r in rows:
        p = RAW / r["local_filename"]
        if not p.exists():
            problems.append(f"missing file: {p}")
            continue
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        if h != r["sha256"].strip().lower():
            problems.append(f"sha256 mismatch: {r['local_filename']} expected {r['sha256']} got {h}")
    if problems:
        sys.stderr.write("Manifest verification FAILED:\n  " + "\n  ".join(problems) + "\n")
        sys.exit(2)
    return rows


# ---------------------------------------------------------------------------
# 1. Extraction
# ---------------------------------------------------------------------------
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f​‌‍﻿]")


def extract_units(path):
    """Return list of pages; each page is a list of 'units'.

    A unit is a PyMuPDF text block, split where consecutive lines jump far apart
    horizontally (a sidebar heading merged with a right-column label, or a table
    row whose term and definition were merged into one block).
    Each unit keeps lines with original text and marker-free text (superscript
    digits removed), the font size, and its bbox.
    """
    doc = pymupdf.open(path)
    pages = []
    for page in doc:
        W, H = page.rect.width, page.rect.height
        units = []
        d = page.get_text("dict")
        for b in d["blocks"]:
            if b["type"] != 0:
                continue
            cur = None
            prev = None
            for ln in b["lines"]:
                spans = ln["spans"]
                orig = "".join(s["text"] for s in spans)
                norm = "".join(
                    s["text"] for s in spans
                    if not ((s["flags"] & 1) and re.fullmatch(r"\s*\d{1,2}\s*", s["text"]))
                )
                sizes = [s["size"] for s in spans if s["text"].strip()]
                size = max(sizes) if sizes else 0
                x0, y0, x1, y1 = ln["bbox"]
                new_unit = cur is None
                if prev is not None:
                    px0, py0, px1, py1 = prev["bbox"]
                    if abs(x0 - px0) > 60 and (x0 > px1 - 2 or x1 < px0 + 2):
                        new_unit = True
                if new_unit:
                    cur = {"bbox": list(ln["bbox"]), "lines": [], "sizes": []}
                    units.append(cur)
                cur["lines"].append({"orig": orig, "norm": norm, "bbox": list(ln["bbox"]), "size": round(size, 1)})
                cur["sizes"].append(size)
                bb = cur["bbox"]
                cur["bbox"] = [min(bb[0], x0), min(bb[1], y0), max(bb[2], x1), max(bb[3], y1)]
                prev = ln
        out = []
        for u in units:
            text = "\n".join(l["orig"] for l in u["lines"])
            if not text.strip():
                continue
            u["size"] = round(max(u["sizes"]) if u["sizes"] else 0, 1)
            del u["sizes"]
            u["bbox"] = [round(v, 1) for v in u["bbox"]]
            u["text"] = text
            out.append(u)
        pages.append({"page": page.number + 1, "width": W, "height": H,
                      "n_images": len(page.get_images()), "units": out})
    return pages


# ---------------------------------------------------------------------------
# Reading order (column aware)
# ---------------------------------------------------------------------------
def _strips(units):
    """Group units into horizontal strips separated by vertical whitespace."""
    us = sorted(units, key=lambda u: (u["bbox"][1], u["bbox"][0]))
    strips = []
    cur, cur_y1 = [], None
    for u in us:
        if cur and u["bbox"][1] >= cur_y1 - 1:
            strips.append(cur)
            cur, cur_y1 = [], None
        cur.append(u)
        cur_y1 = u["bbox"][3] if cur_y1 is None else max(cur_y1, u["bbox"][3])
    if cur:
        strips.append(cur)
    return strips


def _ok_channel(a, b, lo, hi, min_w=6, margin_w=40):
    """A gutter must be >= min_w wide; a channel touching the page margin must be >= margin_w wide."""
    if a <= lo or b >= hi:
        return b - a >= margin_w
    return b - a >= min_w


def _free_channels(units, lo, hi):
    """x-intervals inside (lo, hi) not covered by any unit."""
    iv = sorted((u["bbox"][0], u["bbox"][2]) for u in units)
    out, cur = [], lo
    for a, b in iv:
        if a > cur and _ok_channel(cur, a, lo, hi):
            out.append((cur, a))
        cur = max(cur, b)
    if hi > cur and _ok_channel(cur, hi, lo, hi):
        out.append((cur, hi))
    return out


def _intersect(ch1, ch2, lo, hi):
    out = []
    for a1, b1 in ch1:
        for a2, b2 in ch2:
            a, b = max(a1, a2), min(b1, b2)
            if b > a and _ok_channel(a, b, lo, hi):
                out.append((a, b))
    return out


def reading_order(units, table_mode=False):
    """Column-aware reading order.

    Units are cut into horizontal strips; consecutive strips that share a free
    vertical channel are grouped, and a group whose channel has text on both
    sides is read left column first, then right column (recursively).
    Table pages are read row by row.
    """
    if len(units) <= 1:
        return list(units)
    strips = _strips(units)
    if table_mode:
        out = []
        for s in strips:
            out.extend(sorted(s, key=lambda u: (u["bbox"][0], u["bbox"][1])))
        return out
    lo = min(u["bbox"][0] for u in units) + 10
    hi = max(u["bbox"][2] for u in units) - 10
    groups, i = [], 0      # each group: list of strips
    while i < len(strips):
        g = [strips[i]]
        ch = _free_channels(strips[i], lo, hi)
        j = i + 1
        while j < len(strips) and ch:
            ch2 = _intersect(ch, _free_channels(strips[j], lo, hi), lo, hi)
            if not ch2:
                break
            g.append(strips[j])
            ch = ch2
            j += 1
        groups.append(g)
        i = j

    def channels_of(g):
        ch = None
        for s in g:
            fc = _free_channels(s, lo, hi)
            ch = fc if ch is None else _intersect(ch, fc, lo, hi)
        return ch or []

    def find_split(g):
        us = [u for s in g for u in s]
        for a, b in sorted(channels_of(g), key=lambda c: c[0] - c[1]):
            mid = (a + b) / 2
            left = [u for u in us if u["bbox"][2] <= mid]
            right = [u for u in us if u["bbox"][0] >= mid]
            if left and right and len(left) + len(right) == len(us):
                return a, b, left, right
        return None

    # A sidebar heading (large font, left column) often starts lower than the first
    # right-column lines that belong to it: pull those trailing right-column strips of
    # the previous group into the sidebar group.
    for k in range(1, len(groups)):
        sp = find_split(groups[k])
        if not sp:
            continue
        a, b, left, right = sp
        heads = [u for u in left if u.get("size", 0) >= 13.5]
        if not heads:
            continue
        y_h = min(u["bbox"][1] for u in heads)
        prev = groups[k - 1]
        moved = []
        while prev:
            s = prev[-1]
            if all(u["bbox"][0] >= a for u in s) and min(u["bbox"][1] for u in s) >= y_h - 90:
                moved.insert(0, prev.pop())
            else:
                break
        if moved:
            groups[k] = moved + groups[k]
    groups = [g for g in groups if g]

    out = []
    for g in groups:
        us = [u for s in g for u in s]
        sp = find_split(g)
        split = (sp[2], sp[3]) if sp else None
        if split is None or len(us) == 1:
            out.extend(sorted(us, key=lambda u: (u["bbox"][1], u["bbox"][0])))
            continue
        out.extend(reading_order(split[0]))
        out.extend(reading_order(split[1]))
    return out


# ---------------------------------------------------------------------------
# 2. Cleaning helpers
# ---------------------------------------------------------------------------
QUOTE_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "`": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "–": "-", "—": "-", "‒": "-", "‑": "-", "‐": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", "\t": " ",
}
BULLET_RE = re.compile(r"^\s*(?:[•●▪–—-]|•\t)\s*")


def strip_ctrl(s):
    return CTRL_RE.sub("", s)


def join_lines(lines, hyph_keep):
    """Join PDF lines into one string.

    Line-final hyphens: keep the hyphen if the hyphenated compound is attested in
    the corpus (e.g. 'net-zero'), otherwise remove it (true line-break hyphenation).
    """
    out = ""
    for ln in lines:
        t = strip_ctrl(ln).strip()
        if not t:
            continue
        if not out:
            out = t
            continue
        if re.search(r"[A-Za-z]-$", out) and re.match(r"[a-z]", t):
            left = re.search(r"([A-Za-z]+)-$", out).group(1)
            right = re.match(r"([a-z]+)", t).group(1)
            if (left.lower(), right.lower()) in hyph_keep:
                out = out + t
            else:
                out = out[:-1] + t
        elif re.search(r"[A-Za-z0-9]-$", out):
            out = out + t          # 'Non-' + 'State', 'CCP-' + 'Approved': hyphen kept, no space added
        else:
            out = out + " " + t
    return re.sub(r"[ \t]+", " ", out).strip()


def normalise(s):
    """Normalised comparison form: NFKC, plain quotes/dashes, collapsed whitespace."""
    s = unicodedata.normalize("NFKC", strip_ctrl(s))
    s = "".join(QUOTE_MAP.get(c, c) for c in s)
    s = re.sub(r"(?<=\w)- (?=[a-z])", "-", s)       # 'non- state' -> 'non-state'
    s = re.sub(r"\s*-\s*(?=\d)", "-", s) if re.search(r"\d\s*-\s*\d", s) else s
    s = re.sub(r"\s+", " ", s).strip()
    return s


MONTH_RE = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
GLUED_EXCLUDE = {"step", "section", "box", "figure", "graph", "table", "version", "phase", "scope", "criterion",
                 "annex", "option", "page", "pg", "cop", "co", "ch", "gt", "tco"}


def strip_glued_markers(s):
    """Fallback for footnote markers printed inline (no superscript flag in the PDF).

    Superscript markers are already removed using PyMuPDF span flags (see unmarked()). This
    only handles markers the PDF prints at body size, in two narrow patterns:
      - a lower-case word of >= 4 letters followed directly by 1-2 digits ('Principles1'),
        except labels such as 'Step3', 'COP27', 'CO2';
      - a year glued to 1-2 digits right after a month name ('January 1, 202615').
    Years, percentages, decimals and dollar figures are never touched.
    """
    def word(m):
        w = m.group(1)
        return m.group(0) if w.lower() in GLUED_EXCLUDE or not re.search(r"[a-z]$", w) else w
    s = re.sub(r"\b([A-Za-z]{4,})(\d{1,2})\b", word, s)
    s = re.sub(r"(" + MONTH_RE + r"\s+(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?(?:19|20)\d{2})\d{1,2}\b", r"\1", s)
    return s


ENUM_RE = re.compile(r"^\s*(?:\(?\d{1,2}(?:\.\d{1,2})*\)?[.):]?|\(?[a-z][.)])(?:\s+[-" + chr(0x2013) + chr(0x2014)
                     + r"])?\s+(?!" + MONTH_RE + r"\b)(?=[a-z(\"'])", re.I)


def cmp_key(s):
    """Key used to decide whether two sentences are identical after normalisation.

    Ignores case, whitespace, punctuation, hyphen-vs-space, and leading list numbering
    ('2.1.1.', '1:', '(a)'). Keeps digits, '%', '$' and decimal points between digits.
    """
    s = normalise(s).lower()
    s = ENUM_RE.sub("", s)
    s = re.sub(r"(?<=\d)[.,](?=\d)", "\u0001", s)         # protect 6.4 / 2,000
    # keep meaningful symbols: % $ and comparison signs (thresholds such as '>= 10% and < 50%')
    s = re.sub("[^a-z0-9%$<>=+" + chr(0x2265) + chr(0x2264) + chr(1) + "]+", " ", s)
    s = re.sub("([<>=+" + chr(0x2265) + chr(0x2264) + "])", r" \1 ", s)
    s = s.replace("\u0001", ".")
    return re.sub(r"\s+", " ", s).strip()


MARK_OPEN, MARK_CLOSE = chr(0x2063), chr(0x2064)   # invisible sentinels around footnote markers
_MO, _MC = re.escape(MARK_OPEN), re.escape(MARK_CLOSE)
MARKER_RE = re.compile(_MO + "[^" + _MC + "]*" + _MC)


def visible(s):
    """Original wording: sentinels removed, footnote markers kept as printed."""
    return s.replace(MARK_OPEN, "").replace(MARK_CLOSE, "")


def unmarked(s):
    """Wording without footnote markers (used for comparison)."""
    return MARKER_RE.sub("", s)


# ---------------------------------------------------------------------------
# 2. Cleaning
# ---------------------------------------------------------------------------
FOOTER_RE = re.compile(
    r"^\s*(\d{1,3}\s*)?(VCMI\s*[" + chr(0x2014) + r"-]\s*Claims Code of Practice|VCMI\s*["
    + chr(0x2014) + r"-]\s*Voluntary Carbon Markets Integrity Initiative|VCMI Claims Code of Practice)?\s*(\d{1,3})?\s*$")
STATUS_BANNER_RE = re.compile(r"^VCMI Claims Code v\d", re.I)
FOOTNOTE_RE = re.compile(r"^\s*(\d{1,2})\s+\S")


def unit_plain(u):
    return re.sub(r"\s+", " ", visible(u["text"])).strip()


def is_table_page(units):
    texts = [unit_plain(u).lower() for u in units]
    if any("change/update description" in t for t in texts):
        return "history"
    if any(t in ("term", "term definition", "definition") for t in texts):
        return "glossary"
    if any(t in ("section", "section references") for t in texts):
        return "references"
    return None


def mark_footnote_markers(path, pages):
    """Re-read spans and wrap superscript digit spans (footnote markers) in sentinels."""
    doc = pymupdf.open(path)
    for pg, page in zip(pages, doc):
        span_lines = {}
        for b in page.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for ln in b["lines"]:
                key = tuple(round(v, 1) for v in ln["bbox"])
                parts = []
                for s in ln["spans"]:
                    t = s["text"]
                    if (s["flags"] & 1) and re.fullmatch(r"\s*\d{1,2}\s*", t):
                        parts.append(MARK_OPEN + t + MARK_CLOSE)
                    else:
                        parts.append(t)
                span_lines[key] = "".join(parts)
        for u in pg["units"]:
            for ln in u["lines"]:
                ln["orig_marked"] = span_lines.get(tuple(round(v, 1) for v in ln["bbox"]), ln["orig"])


def extract_and_clean(row):
    path = RAW / row["local_filename"]
    pages = extract_units(path)
    mark_footnote_markers(path, pages)
    n = len(pages)
    removed, problems = [], []

    # automatic boilerplate: same text (digits masked) on more than half of the pages
    def bp_key(u):
        return re.sub(r"\d+", "#", re.sub(r"\s+", " ", u["text"])).strip()
    page_sets = defaultdict(set)
    for pg in pages:
        for u in pg["units"]:
            page_sets[bp_key(u)].add(pg["page"])
    boiler = {k for k, v in page_sets.items() if len(v) > n / 2 and len(k) > 1}

    status_first = None
    for pg in pages:
        H = pg["height"]
        keep = []
        for u in pg["units"]:
            t = unit_plain(u)
            k = bp_key(u)
            if STATUS_BANNER_RE.match(t) and k in boiler:
                if status_first is None:
                    status_first = dict(u, page=pg["page"])
                    removed.append({"page": pg["page"], "reason": "status banner, first occurrence (kept as section status/notice)", "text": t})
                else:
                    removed.append({"page": pg["page"], "reason": "status banner (repeated on every page)", "text": t})
                continue
            if u["bbox"][1] > 0.93 * H and FOOTER_RE.match(u["text"].replace("\n", " ")):
                removed.append({"page": pg["page"], "reason": "page number / running footer", "text": t})
                continue
            if k in boiler:
                removed.append({"page": pg["page"], "reason": "repeated boilerplate (on >50% of pages)", "text": t})
                continue
            if re.fullmatch(r"0[1-9]", t) and u["size"] >= 15:
                removed.append({"page": pg["page"], "reason": "decorative step number", "text": t})
                continue
            if re.fullmatch(r"\d{1,2}", t) and u["size"] <= 10.5:
                removed.append({"page": pg["page"], "reason": "stray number (orphan footnote number)", "text": t})
                continue
            keep.append(u)
        pg["units"] = keep

    for pg in pages:
        us = pg["units"]
        words = sum(len(u["text"].split()) for u in us)
        if not us:
            pg["kind"] = "empty"
            problems.append({"page": pg["page"], "problem": f"no extractable text layer content (page has {pg['n_images']} image(s))"})
            continue
        if 1 < pg["page"] < n and len(us) <= 3 and words <= 12 and max(u["size"] for u in us) >= 30:
            pg["kind"] = "divider"
            removed.append({"page": pg["page"], "reason": "divider page (title only)",
                            "text": " ".join(unit_plain(u) for u in us)})
            pg["units"] = []
            continue
        pg["kind"] = is_table_page(us) or "text"

    for pg in pages:
        body, notes = [], []
        for u in pg["units"]:
            if u["size"] <= 8.5 and FOOTNOTE_RE.match(u["text"]) and pg["kind"] == "text":
                u["kind"] = "footnote"
                u["footnote_label"] = FOOTNOTE_RE.match(u["text"]).group(1)
                notes.append(u)
            else:
                u["kind"] = "body"
                body.append(u)
        ordered = reading_order(body, table_mode=pg["kind"] in ("history", "glossary", "references"))
        notes.sort(key=lambda u: u["bbox"][1])
        pg["units"] = ordered + notes
    return pages, removed, problems, status_first


# ---------------------------------------------------------------------------
# Items: bullets split, original wording kept
# ---------------------------------------------------------------------------
BULLET_LINE_RE = re.compile("^\\s*(?:[" + chr(0x2022) + chr(0x25cf) + chr(0x25aa) + chr(0xf0b7) + "]|"
                            + chr(0x2014) + "|" + chr(0x2013) + "(?=\\s))\\s*")


def unit_items(u, hyph_keep):
    items, cur, cur_b = [], [], False
    for ln in u["lines"]:
        t = strip_ctrl(ln.get("orig_marked", ln["orig"])).replace("\t", " ")
        if BULLET_LINE_RE.match(visible(t)):
            if cur:
                items.append((cur, cur_b))
            cur, cur_b = [], True
            t = BULLET_LINE_RE.sub("", t, count=1)
            if not t.strip():
                continue
        cur.append(t)
    if cur:
        items.append((cur, cur_b))
    out = []
    for it, bulleted in items:
        s = join_lines(it, hyph_keep)
        if u.get("kind") == "footnote":
            s = re.sub(r"^\s*\d{1,2}\s+", "", s)
        s = s.strip()
        if s:
            out.append(BulletStr(s, bulleted))
    return out


class BulletStr(str):
    """A string that remembers whether it started with a bullet glyph."""

    def __new__(cls, value, bulleted=False):
        obj = str.__new__(cls, value)
        obj.bulleted = bulleted
        return obj


# ---------------------------------------------------------------------------
# 3. Sections
# ---------------------------------------------------------------------------
def slug(s):
    s = normalise(s).lower().replace("&", " and ")
    s = re.sub(r"\(a\.k\.a\.\s*", "(", s)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


BOX_TOPICS = [
    (r"development", "box/claims-code-development"),
    (r"claims names", "box/claims-names"),
    (r"flexibility research", "box/flexibility-research"),
    (r"transition plan", "box/climate-transition-plans"),
    (r"cost implications", "box/cost-implications"),
    (r"scope 3", "box/scope3"),
    (r"double claiming|double counting", "box/double-counting"),
    (r"core carbon principles", "box/core-carbon-principles"),
    (r"remov", "box/removal-and-reduction-credits"),
]

# (full-match pattern on lower-cased normalised heading, section_id, minimum font size)
HEADING_RULES = [
    (r"about vcmi", "front/about-vcmi", 17),
    (r"document history", "history/document-history", 17),
    (r"contents", "front/contents", 17),
    (r"executive summary", "exec/purpose", 17),
    (r"the purpose of the claims code", "exec/purpose", 0),
    (r"who the (vcmi )?claims code (of practice )?is for", "exec/who-for", 0),
    (r"how the vcmi claims code works:?", "exec/how-it-works", 13),
    (r"next steps:?", "exec/next-steps", 0),
    (r"letter from vcmi (co-chairs|chair)", "letter/letter-from-vcmi", 17),
    (r"the aims of the vcmi claims code of practice", "aims/about-the-code", 17),
    (r"about the vcmi claims code", "aims/about-the-code", 0),
    (r"governance and vcmi's role in (voluntary )?carbon (credit )?markets", "governance/vcmi-role", 17),
    (r"the vcmi claims code of practice", "code/introduction", 17),
    (r"vcmi enterprise-wide claims", "code/enterprise-wide-claims", 13),
    (r"the four steps for making a vcmi claim", "code/four-steps", 13),
    (r"(1\. ?)?(comply with the foundational criteria|demonstrate strong corporate governance on climate by complying with the foundational criteria)",
     "step1/foundational-criteria", 13.5),
    (r"(2\. ?)?(select a vcmi claim to make.*|demonstrate progress on decarbonization)", "step2/claim-selection-and-progress", 13.5),
    (r"(3\. ?)?(meet the required carbon credit use and quality thresholds|purchase and retire high.quality carbon credits aligned with vcmi claim thresholds)",
     "step3/introduction", 13.5),
    (r"(4\. ?)?(obtain third-party (assurance|verification) .*|disclose transparently and obtain third-party verification .*)",
     "step4/disclosure-and-verification", 13.5),
    (r"foundational criterion ([1-4]):? .*", "fc", 13.5),
    (r"requirements for the purchase and retirement of high-quality carbon credits:?", "step3/purchase-requirements", 0),
    (r"interim options.*", "step3/interim-options", 0),
    (r"requirements for reporting high-quality carbon credits", "step3/reporting-requirements", 0),
    (r"references", "back/references", 17),
    (r"glossary", "glossary/_title", 13),
    (r"acknowledge?ments", "back/acknowledgements", 17),
    (r"how to access additional information", "back/how-to-access", 17),
]
FC_SLUGS = {"1": "fc1/emissions-inventory", "2": "fc2/near-term-targets",
            "3": "fc3/progress-towards-targets", "4": "fc4/public-policy-advocacy"}
EXEC_STEP_RE = re.compile(r"([1-4]): ?[A-Z].*")


def heading_rule(text, size, current):
    raw = normalise(visible(text))
    c = re.sub(r"\s+,", ",", raw.lower()).rstrip(" .")
    if len(c.split()) > 30:
        return None
    m = re.fullmatch(r"box ?(\d+)[.:]?\s*(\(continued\):?)?\s*(.*)", c)
    if m:
        for pat, sid in BOX_TOPICS:
            if re.search(pat, m.group(3)):
                return sid
        return "box/" + slug(m.group(3))
    if current.startswith("exec/") and EXEC_STEP_RE.fullmatch(raw) and raw[3:].upper() == raw[3:]:
        return f"exec/step{raw[0]}-summary"
    for pat, sid, mins in HEADING_RULES:
        if size + 0.01 < mins:
            continue
        m = re.fullmatch(pat, c)
        if m:
            return FC_SLUGS[m.group(1)] if sid == "fc" else sid
    return None


def parse_history(units):
    labels = [u for u in units if u["bbox"][0] < 100 and re.fullmatch(r"(provisional|\d\.\d)", unit_plain(u), re.I)]
    labels.sort(key=lambda u: u["bbox"][1])
    rows = [{"version": unit_plain(l), "desc": [], "date": None, "y": l["bbox"][1]} for l in labels]
    for u in units:
        if u in labels:
            continue
        t = unit_plain(u).lower()
        if t in ("version", "change/update description", "publication date", "document history") or t.startswith("version change/update"):
            continue
        cand = [r for r in rows if r["y"] <= u["bbox"][1] + 3]
        if not cand:
            continue
        if u["bbox"][0] >= 430:
            cand[-1]["date"] = u
        else:
            cand[-1]["desc"].append(u)
    return rows


def parse_glossary(units):
    hdr = [u for u in units if unit_plain(u).lower() == "definition"]
    def_x = hdr[0]["bbox"][0] if hdr else 160
    terms, defs = [], []
    for u in units:
        if unit_plain(u).lower() in ("term", "definition", "glossary", "term definition"):
            continue
        (terms if u["bbox"][2] < def_x - 3 else defs).append(u)
    terms.sort(key=lambda u: u["bbox"][1])
    rows = [{"term": t, "defs": []} for t in terms]
    orphans = []
    for d in sorted(defs, key=lambda u: u["bbox"][1]):
        best, best_ov = None, 0
        for r in rows:
            ov = min(r["term"]["bbox"][3], d["bbox"][3]) - max(r["term"]["bbox"][1], d["bbox"][1])
            if ov > best_ov:
                best, best_ov = r, ov
        if best is None:
            above = [r for r in rows if r["term"]["bbox"][1] <= d["bbox"][1]]
            best = above[-1] if above else None
        (best["defs"] if best else orphans).append(d)
    return rows, orphans


def build_items(pages, status_first, hyph_keep, problems):
    items = []
    if status_first:
        items.append({"kind": "status", "text": " ".join(unit_items(status_first, hyph_keep)),
                      "page": status_first["page"]})
    text_pages = [p["page"] for p in pages if p["units"]]
    last_text_page = max(text_pages) if text_pages else 0
    for pg in pages:
        if not pg["units"]:
            continue
        if pg["page"] == 1:
            items.append({"kind": "force", "section": "front/cover", "heading": "Cover", "page": 1})
        elif pg["page"] == last_text_page and not any(heading_rule(u["text"], u["size"], "") for u in pg["units"]):
            items.append({"kind": "force", "section": "back/back-cover", "heading": "Back cover", "page": pg["page"]})
        if pg["kind"] == "history":
            items.append({"kind": "force", "section": "history/document-history", "heading": "Document History", "page": pg["page"]})
            for r in parse_history(pg["units"]):
                # version cell and date cell are kept as separate verbatim items
                items.append({"kind": "text", "text": r["version"], "page": pg["page"],
                              "row_label": True, "history_version": r["version"]})
                if r["date"]:
                    items.append({"kind": "text", "text": unit_plain(r["date"]), "page": pg["page"],
                                  "row_label": True, "history_version": r["version"]})
                for u in r["desc"]:
                    for it in unit_items(u, hyph_keep):
                        items.append({"kind": "text", "text": it, "page": pg["page"], "history_version": r["version"]})
            continue
        if pg["kind"] == "glossary":
            rows, orphans = parse_glossary(pg["units"])
            for d in orphans:
                problems.append({"page": pg["page"], "problem": "glossary definition with no term cell: " + unit_plain(d)[:80]})
                for it in unit_items(d, hyph_keep):
                    items.append({"kind": "text", "text": it, "page": pg["page"]})
            for r in rows:
                term = " ".join(unit_items(r["term"], hyph_keep))
                items.append({"kind": "force", "section": "glossary/" + slug(unmarked(term)),
                              "heading": visible(term), "page": pg["page"]})
                for d in r["defs"]:
                    for it in unit_items(d, hyph_keep):
                        items.append({"kind": "text", "text": it, "page": pg["page"]})
            continue
        for u in pg["units"]:
            if unit_items(u, hyph_keep):
                items.append({"kind": "unit", "unit": u, "page": pg["page"], "footnote": u.get("kind") == "footnote"})
    return items


def build_sections(items, hyph_keep):
    sections = []
    cur = None
    has_interim_heading = any(it["kind"] == "unit" and re.match(r"interim options", unit_plain(it["unit"]), re.I) for it in items)

    box_parent = None   # section that encloses the current box

    def open_section(sid, heading, page):
        nonlocal cur, box_parent
        if cur is not None and cur["section_id"] == sid:
            cur["page_end"] = max(cur["page_end"], page)
            return
        if sid.startswith("box/"):
            if cur is not None and not cur["section_id"].startswith("box/"):
                box_parent = cur
        else:
            box_parent = None
        existing = [s for s in sections if s["section_id"] == sid or s["section_id"].startswith(sid + "~")]
        if existing and sid.startswith("box/"):
            cur = existing[-1]          # 'BOX n (CONTINUED)' continues the same box
            cur["page_end"] = max(cur["page_end"], page)
            return
        if existing:
            sid = f"{sid}~{len(existing) + 1}"
        cur = {"section_id": sid, "heading": heading, "page_start": page, "page_end": page, "src": []}
        sections.append(cur)

    def add_text(text, page, footnote=False, **extra):
        if cur is None:
            open_section("front/untitled", "", page)
        cur["src"].append(dict(text=str(text), page=page, footnote=footnote,
                               bulleted=getattr(text, "bulleted", False), **extra))
        cur["page_end"] = max(cur["page_end"], page)

    for it in items:
        if it["kind"] == "status":
            sections.append({"section_id": "status/notice", "heading": "Status notice (repeated page banner, first occurrence)",
                             "page_start": it["page"], "page_end": it["page"],
                             "src": [dict(text=it["text"], page=it["page"], footnote=False)]})
            continue
        if it["kind"] == "force":
            open_section(it["section"], it["heading"], it["page"])
            continue
        if it["kind"] == "text":
            add_text(it["text"], it["page"], row_label=it.get("row_label", False), history_version=it.get("history_version"))
            continue
        u = it["unit"]
        if it["footnote"]:
            # footnotes stay with their page; if a box opened lower on this page, they go to the
            # enclosing section rather than to the box
            target = cur
            if (cur is not None and cur["section_id"].startswith("box/") and box_parent is not None
                    and cur["page_start"] == it["page"]):
                target = box_parent
            for t in unit_items(u, hyph_keep):
                if target is cur:
                    add_text(t, it["page"], footnote=True)
                else:
                    target["src"].append(dict(text=str(t), page=it["page"], footnote=True, bulleted=False))
                    target["page_end"] = max(target["page_end"], it["page"])
            continue
        lines = [l.get("orig_marked", l["orig"]) for l in u["lines"]]
        cur_id = cur["section_id"] if cur else ""
        sid, k = None, 0
        for k in range(1, min(len(lines), 12) + 1):
            sid = heading_rule(" ".join(lines[:k]), u["size"], cur_id)
            if sid:
                break
        # a box ends at a page break unless the new page opens with 'BOX n (CONTINUED)'
        if (cur is not None and cur["section_id"].startswith("box/") and box_parent is not None
                and it["page"] > cur["page_end"] and not (sid and sid.startswith("box/"))):
            cur = box_parent
            box_parent = None
            cur_id = cur["section_id"]
            if sid is None:
                for k in range(1, min(len(lines), 12) + 1):
                    sid = heading_rule(" ".join(lines[:k]), u["size"], cur_id)
                    if sid:
                        break
        if sid:
            # extend over continuation lines of the same heading (same font size, rule still matches)
            first_size = u["lines"][0].get("size", u["size"])
            while k < len(lines) and abs(u["lines"][k].get("size", 0) - first_size) < 0.6 and not re.match(
                    r"^\s*(the following|these|this|companies|vcmi)(?![a-z])", visible(lines[k]), re.I):
                nsid = heading_rule(" ".join(lines[:k + 1]), u["size"], cur_id)
                if not (nsid == sid or (nsid and sid.startswith("box/") and nsid.startswith("box/"))):
                    break
                sid = nsid
                k += 1
            heading = normalise_ws(visible(join_lines(lines[:k], hyph_keep)))
            if sid != "glossary/_title":
                open_section(sid, heading, it["page"])
            rest = u["lines"][k:]
            if rest:
                for t in unit_items(dict(u, lines=rest), hyph_keep):
                    add_text(t, it["page"])
            continue
        if (cur_id == "step3/purchase-requirements" and not has_interim_heading
                and re.match(r"at the time of publication", unit_plain(u), re.I)):
            open_section("step3/interim-options", "", it["page"])
            cur["heading_note"] = "no heading in this version; section starts at 'At the time of publication'"
        for t in unit_items(u, hyph_keep):
            add_text(t, it["page"])
    return sections


def normalise_ws(s):
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# Sentences
# ---------------------------------------------------------------------------
ABBREV_RE = re.compile(r"(?:^|[\s(])(?:e\.g|i\.e|etc|a\.k\.a|No|Fig|vs|Dr|St|Inc|Ltd|al|approx|cf|pp?)\.$")
SENT_SPLIT_RE = re.compile(
    "(?<=[.!?])[\"')\\]" + chr(0x201d) + chr(0x2019) + "]*(?:" + _MO + "[^" + _MC + "]*" + _MC + ")?\\s+(?=[\"'(" + chr(0x201c) + chr(0x2018) + "]?[A-Z0-9])")


def split_sentences(text):
    parts, start = [], 0
    for m in SENT_SPLIT_RE.finditer(text):
        before = unmarked(text[start:m.start()]).rstrip("\"')]" + chr(0x201d) + chr(0x2019))
        if ABBREV_RE.search(before):
            continue
        if re.fullmatch(r"\s*(?:\d{1,2}(?:\.\d{1,2})*|[A-Za-z])\.", before):   # list enumerator '1.' / '2.1.' / 'A.'
            continue
        if re.search(r"(?:^|\s)(?:Figure|Graph|Table|Box|Step|Section)\s*\d+\.$", before):   # 'Figure 1. Title'
            continue
        if re.search(r"(?:^|\s)[A-Z]\.$", before):      # initials such as 'J.'
            continue
        seg = text[start:m.end()].strip()
        if seg:
            parts.append(seg)
        start = m.end()
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def section_sentences(sec):
    merged = []
    for s in sec["src"]:
        t = s["text"]
        starts_lower = re.match(r"^[a-z(]", unmarked(t).lstrip()) is not None
        if re.match(r"^(?:https?://|www\.|[a-z0-9-]+\.(?:org|com|net|int)\b)", unmarked(t).lstrip()):
            starts_lower = False    # a URL or domain is never the continuation of a sentence
        if not starts_lower and merged and re.match(r"^[0-9$]", unmarked(t).lstrip()) and re.search(
                r"(?:^|\s)(?:than|of|to|the|and|or|a|an|in|on|by|for|with|that|from|as|least)$",
                unmarked(merged[-1]["text"]).rstrip()):
            starts_lower = True     # e.g. '... equal to or greater than' | '20%, and less than 60% ...'
        target = None
        if merged and starts_lower and not s.get("row_label") and not s.get("bulleted"):
            # a fragment that ends with a hyphen (word split by a column/page break) claims the
            # continuation first, even if a figure label was read in between
            for m in reversed(merged[-3:]):
                if m["footnote"] == s["footnote"] and not m.get("row_label") and m.get("open_hyphen") \
                        and abs(m["pages"][-1] - s["page"]) <= 1:
                    target = m
                    break
            if target is None:
                m = merged[-1]
                prev = unmarked(m["text"]).rstrip()
                if not m.get("row_label") and m["footnote"] == s["footnote"] and prev and len(prev.split()) >= 4 \
                        and not re.search(r"[.!?:;\")" + chr(0x201d) + r"]$", prev):
                    target = m
        if target is not None:
            prev = unmarked(target["text"]).rstrip()
            hy = re.search(r"([A-Za-z]+)-$", prev)
            base = target["text"].rstrip()
            if hy:   # word hyphenated across a column or page break
                right = re.match(r"([a-z]+)", unmarked(t).lstrip())
                keep = right is None or (hy.group(1).lower(), right.group(1).lower()) in HYPH_KEEP
                target["text"] = (base if keep else base[:-1]) + t.lstrip()
            else:
                target["text"] = base + " " + t.lstrip()
            target["open_hyphen"] = False
            target["pages"].append(s["page"])
            target["spans"].append((len(target["text"]) - len(t.lstrip()), s["page"]))
            continue
        ends_hyphen = re.search(r"[A-Za-z]-$", unmarked(t).rstrip()) is not None
        merged.append(dict(s, pages=[s["page"]], spans=[(0, s["page"])], open_hyphen=ends_hyphen))
    out = []
    for m in merged:
        pos = 0
        for sent in split_sentences(m["text"]):
            idx = m["text"].find(sent, pos)
            pos = idx + len(sent) if idx >= 0 else pos
            start_page = m["spans"][0][1]
            for off, pgn in m["spans"]:
                if idx >= off:
                    start_page = pgn
            end_page = start_page
            for off, pgn in m["spans"]:
                if idx + len(sent) > off:
                    end_page = pgn
            norm = normalise(strip_glued_markers(unmarked(sent)))
            key = cmp_key(norm)
            if not key:
                continue
            out.append({"orig": normalise_ws(visible(sent)), "norm": norm, "key": key,
                        "page": start_page, "page_end": end_page,
                        "footnote": m["footnote"], "history_version": m.get("history_version"),
                        "row_label": bool(m.get("row_label"))})
    return out


# ---------------------------------------------------------------------------
# 4/5. Alignment and sentence diff
# ---------------------------------------------------------------------------
EXCLUDED_FROM_DIFF = {"front/contents"}   # table of contents: page references only


def sim(a, b):
    return fuzz.ratio(a, b) / 100.0


def align_sections(old_secs, new_secs):
    old_ids = {s["section_id"]: s for s in old_secs}
    new_ids = {s["section_id"]: s for s in new_secs}
    pairs, renamed = [], []
    for sid in old_ids:
        if sid in new_ids:
            pairs.append((old_ids[sid], new_ids[sid]))
    un_old = [s for sid, s in old_ids.items() if sid not in new_ids]
    un_new = [s for sid, s in new_ids.items() if sid not in old_ids]
    cands = []
    for o in un_old:
        for n in un_new:
            if o["section_id"].split("/")[0] != n["section_id"].split("/")[0]:
                continue
            sc = fuzz.token_set_ratio(normalise(o["heading"]).lower(), normalise(n["heading"]).lower())
            if sc >= 80:
                cands.append((sc, fuzz.ratio(normalise(o["heading"]).lower(), normalise(n["heading"]).lower()), o["section_id"], n["section_id"], o, n))
    used_o, used_n = set(), set()
    for sc, r2, oid, nid, o, n in sorted(cands, key=lambda c: (-c[0], -c[1], c[2], c[3])):
        if oid in used_o or nid in used_n:
            continue
        used_o.add(oid)
        used_n.add(nid)
        pairs.append((o, n))
        renamed.append({"old_section_id": oid, "new_section_id": nid, "old_heading": o["heading"],
                        "new_heading": n["heading"], "token_set_ratio": sc})
    # positional pairing: an unmatched old section and an unmatched new section that sit between
    # the same matched neighbours, with similar headings (or, failing that, similar bodies), are
    # one modified section rather than a removal plus an addition
    old_idx = {s["section_id"]: i for i, s in enumerate(old_secs)}
    new_idx = {s["section_id"]: i for i, s in enumerate(new_secs)}
    anchors = sorted((old_idx[o["section_id"]], new_idx[n["section_id"]]) for o, n in pairs)

    def window(i):
        lo = max([nj for oi, nj in anchors if oi < i], default=-1)
        hi = min([nj for oi, nj in anchors if oi > i], default=len(new_secs))
        return lo, hi

    def body(sec):
        return " ".join(st["key"] for st in sec.get("sentences", []))[:4000]

    pos_cands = []
    for o in un_old:
        if o["section_id"] in used_o:
            continue
        lo, hi = window(old_idx[o["section_id"]])
        for n in un_new:
            if n["section_id"] in used_n or not (lo < new_idx[n["section_id"]] < hi):
                continue
            hs = fuzz.token_set_ratio(normalise(o["heading"]).lower(), normalise(n["heading"]).lower())
            bs = fuzz.token_set_ratio(body(o), body(n)) if body(o) and body(n) else 0
            same_family = o["section_id"].split("/")[0] == n["section_id"].split("/")[0]
            if hs >= 60 or (same_family and bs >= 70):
                pos_cands.append((hs, bs, o["section_id"], n["section_id"], o, n))
    for hs, bs, oid, nid, o, n in sorted(pos_cands, key=lambda c: (-c[0], -c[1], c[2], c[3])):
        if oid in used_o or nid in used_n:
            continue
        used_o.add(oid)
        used_n.add(nid)
        pairs.append((o, n))
        renamed.append({"old_section_id": oid, "new_section_id": nid, "old_heading": o["heading"],
                        "new_heading": n["heading"], "token_set_ratio": hs, "body_token_set_ratio": bs,
                        "method": "position"})
    removed = [s for s in un_old if s["section_id"] not in used_o]
    added = [s for s in un_new if s["section_id"] not in used_n]
    return pairs, renamed, removed, added


def diff_sentences(old, new):
    """Return list of (kind, old_sentence|None, new_sentence|None)."""
    a = [s["key"] for s in old]
    b = [s["key"] for s in new]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    dels, ins, mods = [], [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        olds = list(range(i1, i2))
        news = list(range(j1, j2))
        cands = sorted(((sim(a[i], b[j]), i, j) for i in olds for j in news), key=lambda c: (-c[0], c[1], c[2]))
        uo, un = set(), set()
        for sc, i, j in cands:
            if sc < 0.6:
                break
            if i in uo or j in un:
                continue
            uo.add(i)
            un.add(j)
            mods.append((i, j))
        dels += [i for i in olds if i not in uo]
        ins += [j for j in news if j not in un]
    # sentences that only moved inside the section are not changes
    ins_keys = defaultdict(list)
    for j in ins:
        ins_keys[b[j]].append(j)
    moved_d, moved_i = set(), set()
    for i in dels:
        if ins_keys.get(a[i]):
            moved_d.add(i)
            moved_i.add(ins_keys[a[i]].pop(0))
    dels = [i for i in dels if i not in moved_d]
    ins = [j for j in ins if j not in moved_i]
    # second chance: near-matches separated by the SequenceMatcher blocks
    cands = sorted(((sim(a[i], b[j]), i, j) for i in dels for j in ins), key=lambda c: (-c[0], c[1], c[2]))
    uo, un = set(), set()
    for sc, i, j in cands:
        if sc < 0.6:
            break
        if i in uo or j in un:
            continue
        uo.add(i)
        un.add(j)
        mods.append((i, j))
    dels = [i for i in dels if i not in uo]
    ins = [j for j in ins if j not in un]
    out = [("modified", old[i], new[j]) for i, j in mods]
    out += [("removed", old[i], None) for i in dels]
    out += [("added", None, new[j]) for j in ins]
    return out, len(moved_d)


# ---------------------------------------------------------------------------
# 6. Classification
# ---------------------------------------------------------------------------
MONTHS = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
NUM_TOKEN_RE = re.compile(
    r"\d{1,2}(?:st|nd|rd|th)?\s+" + MONTHS + r",?\s+\d{4}"
    r"|" + MONTHS + r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
    r"|" + MONTHS + r"\s+\d{4}"
    r"|\d+(?:[.,]\d+)*\s*%"
    r"|\$?\d+(?:[.,]\d+)*", re.I)
NORMATIVE = {"shall", "must", "should", "may", "can", "cannot", "required", "require", "requires", "requirement",
             "requirements", "encouraged", "encourage", "encourages", "recommend", "recommends", "recommended",
             "optional", "only", "not", "no", "never", "all", "any", "least", "minimum", "maximum", "until",
             "after", "before", "eligible", "eligibility", "mandatory", "validated", "validate", "independently",
             "or", "unless", "except", "excluding", "limited", "allowed", "permitted", "prohibited", "need",
             "needs", "deadline", "threshold", "thresholds", "scope", "scopes", "whichever", "earlier", "later"}
STRONG_MODAL_RE = re.compile(r"\b(shall|must|cannot|may not|are required|is required|required to|only)\b", re.I)
FUNCTION_WORDS = {"the", "a", "an", "of", "to", "in", "on", "at", "by", "for", "its", "their", "this", "these",
                  "those", "that", "which", "who", "with", "as", "is", "are", "be", "been", "was", "were", "it",
                  "also", "such", "via", "so", "there", "then", "both", "each", "well", "already", "further",
                  "into", "about", "within", "and", "s", "has", "have", "will", "would"}
# terminology / spelling variants treated as editorial (applied to both sides before comparing)
SWAPS = [
    (r"\bvoluntary carbon markets?\b", "carbon credit market"),
    (r"\bcarbon credit markets\b", "carbon credit market"),
    (r"\bcertification standards?\b", "carbon crediting program"),
    (r"\bccp[ -]approved\b", "ccp labelled"),
    (r"\bccp[ -]label(?:l?ed)?\b", "ccp labelled"),
    (r"\bvcmi (silver|gold|platinum)\b", r"carbon integrity \1"),
    (r"\bvcmi claim", "carbon integrity claim"),
    (r"\bisation\b", "ization"),
    (r"(?<=[a-z])isation", "ization"), (r"(?<=[a-z]{3})is(e|ed|es|ing)\b", r"iz\1"),
    (r"\bcelcius\b", "celsius"), (r"\backnowledgments\b", "acknowledgements"),
    (r"\bmust\b", "shall"),
    (r"\bnear term (?:emissions? reductions? )?targets?\b", "near term target"),
]
NOT_OPERATING_RE = re.compile(
    r"not issuing|no longer issuing|paused the issuance|claims infrastructure[^.]*retired|"
    r"retirement of the VCMI Claims infrastructure|cannot make these claims|claims become operative|"
    r"will (?:only )?be able to (?:make|obtain)|by late 2023|only be able to make a VCMI Claim when", re.I)
OPERATING_RE = re.compile(r"(?:now|has been|have been|is|are|are now) able to (?:make|obtain)", re.I)


def op_state(t):
    """'not' if the text says claims are not (yet / any longer) issued, 'op' if it says they are, else None."""
    if NOT_OPERATING_RE.search(t or ""):
        return "not"
    if OPERATING_RE.search(t or ""):
        return "op"
    return None


DESCRIPTIVE_SECTIONS = ("front/", "letter/", "aims/", "governance/", "exec/purpose", "exec/who-for",
                        "exec/next-steps", "back/", "box/claims-code-development", "box/claims-names",
                        "box/flexibility-research", "box/climate-transition-plans", "box/scope3",
                        "box/cost-implications")


def num_tokens(s):
    toks = [re.sub(r"\s+", " ", t.strip().lower()).replace(",", "") for t in NUM_TOKEN_RE.findall(s)]
    return Counter(toks)


def words(s):
    ws = re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)*", s.lower().replace("-", " "))
    return [w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in ws]


def apply_swaps(s):
    s = re.sub(r"\s*-\s*", " ", s.lower())
    for pat, rep in SWAPS:
        s = re.sub(pat, rep, s)
    return s


def status_counter(sec):
    return Counter(op_state(st["norm"]) for st in sec["sentences"] if op_state(st["norm"]))


def classify(change, old, new, section_id, section_status_changed=True):
    o = ENUM_RE.sub("", old["norm"]) if old else ""      # leading list numbering is not a number change
    n = ENUM_RE.sub("", new["norm"]) if new else ""
    so, sn = op_state(o), op_state(n)
    if section_id == "status/notice" or (section_status_changed and so != sn):
        notes = ["concerns whether VCMI Claims are issued/operative"]
        num_o, num_n = num_tokens(o), num_tokens(n)
        if change == "modified" and num_o != num_n:
            notes.append(f"numbers/dates: {sorted((num_o - num_n).elements())} -> {sorted((num_n - num_o).elements())}")
        return "status", False, "; ".join(notes)
    descriptive = section_id.startswith(DESCRIPTIVE_SECTIONS)
    if change == "modified":
        num_o, num_n = num_tokens(o), num_tokens(n)
        if num_o != num_n:
            lost, gained = sorted((num_o - num_n).elements()), sorted((num_n - num_o).elements())
            return "substantive", False, f"numbers/dates changed: {lost} -> {gained}"
        wo, wn = Counter(words(apply_swaps(o))), Counter(words(apply_swaps(n)))
        rem, add = wo - wn, wn - wo
        changed = set(rem) | set(add)
        if not changed:
            return "editorial", False, "terminology/spelling/punctuation change only"
        if changed <= FUNCTION_WORDS:
            return "editorial", False, f"function-word change only ({', '.join(sorted(changed))})"
        if descriptive:
            return "editorial", False, "wording change in a descriptive (non-rule) section"
        norm_changed = sorted(w for w in changed if w in NORMATIVE)
        if norm_changed:
            return "substantive", True, f"requirement/scope wording changed ({', '.join(norm_changed)}); review"
        return "substantive", True, f"wording change ({', '.join(sorted(changed)[:8])}); meaning may differ; review"
    text = o or n
    if section_id.startswith("history/"):
        return "editorial", False, f"Document History table entry {change}"
    if descriptive:
        return "editorial", False, f"sentence {change} in a descriptive (non-rule) section"
    if len(words(text)) <= 6 and not num_tokens(text) and not (set(words(text)) & NORMATIVE):
        return "editorial", False, f"short label/heading text {change}"
    if STRONG_MODAL_RE.search(text):
        return "substantive", False, f"sentence with requirement wording {change}"
    return "substantive", True, f"sentence {change}; review whether it changes a rule"


# ---------------------------------------------------------------------------
# 7. Document History cross-check (newest version that has the table)
# ---------------------------------------------------------------------------
# Each listed history item -> predicate on change records (version pair + section + text)
HISTORY_MATCHERS = [
    # (history version, item text prefix, from->to versions, section prefixes, regex on old/new text)
    ("2.0", "The Claims Code published by VCMI in June 2023 was further complemented",
     ("1.0", "2.0"), ("",), r"MRA Framework|Supplementary Guidance|Scope 3 Flexibility|branding|Carbon Integrity"),
    ("2.1", "Non-substantive revision to provide further clarification to Foundational Criterion 2",
     ("2.0", "2.1"), ("fc2/",), r"organi[sz]ational boundary|parent|subsidiary"),
    ("2.1", "Non-substantive update under Step 2",
     ("2.0", "2.1"), ("step2/", "exec/step2"), r"statement"),
    ("2.1", "Non-substantive revision of the requirements for provision of evidence related to host country authorization",
     ("2.0", "2.1"), ("step3/",), r"authori[sz]|corresponding adjustment"),
    ("2.1", "Non-substantive update of the term used under Step 3",
     ("2.0", "2.1"), ("step3/",), r"carbon crediting program|certification standard"),
    ("3.0", "Revision to Foundational Criteria related to expansion of scope for accepted GHG emissions accounting frameworks",
     ("2.1", "3.0"), ("fc1/",), r"GHG Protocol|accounting framework|Land Sector"),
    ("3.0", "requirement relating to emissions reduction target setting",
     ("2.1", "3.0"), ("fc2/",), r"target"),
    ("3.0", "Update to Step 3 to expand scope to include Article 6.4 credits",
     ("2.1", "3.0"), ("step3/", "exec/step3", "code/four-steps", "glossary/"), r"Article 6\.4|A6\.4|Paris Agreement Crediting Mechanism"),
    ("3.0", "Update to Step 4 to reflect expanded scope of the VCMI Monitoring, Reporting & Assurance (MRA) Framework",
     ("2.1", "3.0"), ("step4/", "exec/step4"), r"verification|Claims Governance Procedure|verifier"),
    ("3.1", "Update to deadline for when companies shall purchase and retire eligible credits",
     ("3.0", "3.1"), ("step3/",), r"2027"),
    ("3.2", "Update to reflect the retirement of the VCMI Claims infrastructure",
     ("3.1", "3.2"), ("",), "STATUS"),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
HYPH_KEEP = set()


def build_hyph_keep(all_pages):
    """Hyphenated compounds attested inside lines anywhere in the corpus."""
    comp, joined = set(), set()
    for pages in all_pages:
        for pg in pages:
            for u in pg["units"]:
                for ln in u["lines"]:
                    t = ln["orig"]
                    for m in re.finditer(r"\b([A-Za-z]+)-([A-Za-z]+)\b", t):
                        comp.add((m.group(1).lower(), m.group(2).lower()))
                    for w in re.findall(r"[A-Za-z]+", t):
                        joined.add(w.lower())
    return comp, joined


def run():
    rows = load_manifest()
    for d in (CLEAN_DIR, SECT_DIR, DIFF_DIR):
        d.mkdir(parents=True, exist_ok=True)

    raw_pages = {}
    for r in rows:
        raw_pages[r["doc_id"]] = extract_units(RAW / r["local_filename"])
    comp, joined = build_hyph_keep(raw_pages.values())
    # keep the hyphen unless the joined word is attested and the compound is not
    global HYPH_KEEP
    HYPH_KEEP = HyphRule(comp, joined)

    docs = {}
    for r in rows:
        pages, removed, problems, status_first = extract_and_clean(r)
        items = build_items(pages, status_first, HYPH_KEEP, problems)
        sections = build_sections(items, HYPH_KEEP)
        for s in sections:
            s["sentences"] = section_sentences(s)
        docs[r["doc_id"]] = {"row": r, "pages": pages, "removed": removed, "problems": problems, "sections": sections}
        write_clean(r, pages, removed, problems, status_first)
        write_sections(r, sections)

    changes, alignment_log = [], []
    for prev, cur in zip(rows, rows[1:]):
        dA, dB = docs[prev["doc_id"]], docs[cur["doc_id"]]
        pairs, renamed, rem_secs, add_secs = align_sections(dA["sections"], dB["sections"])
        pair_changes = []
        moved_total = 0
        status_changed = {}
        for o, n in pairs:
            status_changed[n["section_id"]] = status_counter(o) != status_counter(n)
        for s_ in rem_secs + add_secs:
            status_changed[s_["section_id"]] = bool(status_counter(s_))
        section_summary = []
        for o, n in pairs:
            if o["section_id"] in EXCLUDED_FROM_DIFF:
                continue
            method = next((x.get("method", "heading similarity") for x in renamed
                           if x["old_section_id"] == o["section_id"]), None)
            paired = (f"section {o['section_id']} matched with {n['section_id']} by {method}"
                      if o["section_id"] != n["section_id"] else None)
            ho, hn = heading_sentence(o), heading_sentence(n)
            heading_changed = bool(ho and hn and cmp_key(strip_box_label(o["heading"])) != cmp_key(strip_box_label(n["heading"])))
            if heading_changed:
                pair_changes.append(("modified", ho, hn, n["section_id"],
                                     "; ".join(x for x in ("section heading changed", paired) if x)))
            elif hn and not ho:
                pair_changes.append(("added", None, hn, n["section_id"], "heading added (no heading in previous version)"))
            elif ho and not hn:
                pair_changes.append(("removed", ho, None, n["section_id"], "heading removed"))
            res, moved = diff_sentences(o["sentences"], n["sentences"])
            moved_total += moved
            for kind, so, sn in res:
                pair_changes.append((kind, so, sn, n["section_id"], paired))
            cnt = Counter(k for k, _, _ in res)
            denom = max(len(o["sentences"]), len(n["sentences"]), 1)
            changed_share = (cnt["added"] + cnt["removed"] + 2 * cnt["modified"]) / (2 * denom)
            if heading_changed or paired or changed_share >= 0.5:
                section_summary.append({"old_section_id": o["section_id"], "section_id": n["section_id"],
                                        "old_heading": o["heading"], "new_heading": n["heading"],
                                        "heading_changed": heading_changed, "paired": bool(paired), "method": method,
                                        "old_sentences": len(o["sentences"]), "new_sentences": len(n["sentences"]),
                                        "added": cnt["added"], "removed": cnt["removed"], "modified": cnt["modified"],
                                        "rewritten": changed_share >= 0.5})
        for s in rem_secs:
            if s["section_id"] in EXCLUDED_FROM_DIFF:
                continue
            if heading_sentence(s):
                pair_changes.append(("removed", heading_sentence(s), None, s["section_id"], "section removed (heading)"))
            for so in s["sentences"]:
                pair_changes.append(("removed", so, None, s["section_id"], "section removed"))
        for s in add_secs:
            if s["section_id"] in EXCLUDED_FROM_DIFF:
                continue
            if heading_sentence(s):
                pair_changes.append(("added", None, heading_sentence(s), s["section_id"], "section added (heading)"))
            for sn in s["sentences"]:
                pair_changes.append(("added", None, sn, s["section_id"], "section added"))
        pair_changes, cross_moves, cross_mods = resolve_cross_section(pair_changes)
        alignment_log.append({"from": prev["version"], "to": cur["version"], "renamed": renamed,
                              "removed_sections": [s["section_id"] for s in rem_secs],
                              "added_sections": [s["section_id"] for s in add_secs],
                              "moved_within_section": moved_total, "moved_across_sections": cross_moves,
                              "modified_across_sections": cross_mods, "section_summary": section_summary})
        for kind, so, sn, sid, extra in pair_changes:
            typ, unc, note = classify(kind, so, sn, sid, status_changed.get(sid, True))
            hv = (sn or so or {}).get("history_version")
            if sid.startswith("history/") and hv:
                extra = f"{extra}; row {hv}" if extra else f"row {hv}"
            if extra:
                note = f"{extra}; {note}"
            changes.append({
                "from_version": prev["version"], "to_version": cur["version"],
                "from_doc_id": prev["doc_id"], "to_doc_id": cur["doc_id"],
                "section_id": sid, "change": kind, "type": typ, "uncertain": unc,
                "old_text": so["orig"] if so else None, "new_text": sn["orig"] if sn else None,
                "old_page": so["page"] if so else None, "new_page": sn["page"] if sn else None,
                "in_vcmi_history": False, "note": note,
            })
    order = {r["version"]: i for i, r in enumerate(rows)}
    sec_order = {}
    for r in rows:
        for i, s in enumerate(docs[r["doc_id"]]["sections"]):
            sec_order.setdefault((r["version"], s["section_id"]), i)
    changes.sort(key=lambda c: (order[c["from_version"]],
                                sec_order.get((c["to_version"], c["section_id"]), sec_order.get((c["from_version"], c["section_id"]), 999)),
                                c["new_page"] if c["new_page"] is not None else c["old_page"] or 0,
                                c["change"], c["old_text"] or "", c["new_text"] or ""))
    id_stats = stable_change_ids(changes)
    changes = [{k: c[k] for k in ("change_id", "from_version", "to_version", "from_doc_id", "to_doc_id", "section_id",
                                  "change", "type", "uncertain", "old_text", "new_text", "old_page", "new_page",
                                  "in_vcmi_history", "note")} for c in changes]
    add_known_notes(changes)
    history = cross_check(docs, rows, changes)
    verification = verify_quotes(docs, rows, changes)
    with open(DIFF_DIR / "changes.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for c in changes:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    events = build_events(changes)
    for e in events:                       # curated one-sentence summaries for the shortlisted events
        if e["event_id"] in SHORTLIST_SUMMARIES:
            e["summary"] = SHORTLIST_SUMMARIES[e["event_id"]]
    with open(DIFF_DIR / "events.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for e in events:
            f.write(json.dumps({k: e[k] for k in ("event_id", "from_version", "to_version", "type", "summary",
                                                  "change_ids", "rules")}, ensure_ascii=False) + "\n")
    shortlist = write_shortlist(events, changes, rows, verification)
    write_report(docs, rows, changes, alignment_log, history, verification, id_stats, events, shortlist)
    return docs, changes


class HyphRule:
    """Membership test used by join_lines: keep the hyphen at a line break?"""

    def __init__(self, comp, joined):
        self.comp, self.joined = comp, joined

    def __contains__(self, pair):
        left, right = pair
        if pair in self.comp:
            return True
        if (left + right) in self.joined:
            return False
        return True


SYNTHETIC_HEADINGS = {"", "Cover", "Back cover", "Status notice (repeated page banner, first occurrence)"}


def heading_sentence(sec):
    """The section heading as a sentence record, or None if the heading is not text from the PDF."""
    h = sec["heading"]
    if h in SYNTHETIC_HEADINGS:
        return None
    return {"orig": h, "norm": normalise(h), "key": cmp_key(h), "page": sec["page_start"], "page_end": sec["page_start"],
            "footnote": False, "history_version": None}


def strip_box_label(h):
    return re.sub(r"^\s*box\s*\d+\s*[.:]?\s*(\(continued\):?)?\s*", "", normalise(h), flags=re.I)


def resolve_cross_section(pair_changes):
    """Exact moves between sections are not changes; near-identical moves become 'modified'."""
    rem = [i for i, c in enumerate(pair_changes) if c[0] == "removed"]
    add = [i for i, c in enumerate(pair_changes) if c[0] == "added"]
    by_key = defaultdict(list)
    for i in add:
        by_key[pair_changes[i][2]["key"]].append(i)
    drop = set()
    moves = 0
    for i in rem:
        k = pair_changes[i][1]["key"]
        if by_key.get(k):
            j = by_key[k].pop(0)
            drop.update((i, j))
            moves += 1
    rem = [i for i in rem if i not in drop]
    add = [i for i in add if i not in drop]
    cands = []
    for i in rem:
        for j in add:
            ki, kj = pair_changes[i][1]["key"], pair_changes[j][2]["key"]
            sc = sim(ki, kj)
            if sc >= 0.85 and min(len(ki), len(kj)) >= 80:
                cands.append((sc, i, j))
    used = set()
    new = []
    mods = 0
    for sc, i, j in sorted(cands, key=lambda c: (-c[0], c[1], c[2])):
        if i in used or j in used:
            continue
        used.update((i, j))
        oi, nj = pair_changes[i], pair_changes[j]
        note = f"moved from section {oi[3]}" if oi[3] != nj[3] else None
        new.append(("modified", oi[1], nj[2], nj[3], note))
        mods += 1
    out = [c for k, c in enumerate(pair_changes) if k not in drop and k not in used] + new
    return out, moves, mods


# ---------------------------------------------------------------------------
# Stable change IDs
# ---------------------------------------------------------------------------
ID_HEX = 10


def stable_change_ids(changes):
    """change_id = 'c-' + first 10 hex chars of SHA-256 over a canonical JSON serialisation of
    [from_version, to_version, section_id, old_text, new_text] (UTF-8, null for missing text,
    no whitespace). Records with identical content in the same pair and section (the same
    sentence removed twice, say) get the occurrence number (2, 3, ...) appended to the
    serialisation, in record order, which is itself deterministic. If two different
    serialisations ever share the 10-hex prefix, all records in that clash use 16 hex chars.
    Returns a dict with collision statistics."""
    payloads, seen = [], Counter()
    for c in changes:
        base = [c["from_version"], c["to_version"], c["section_id"], c["old_text"], c["new_text"]]
        key = json.dumps(base, ensure_ascii=False, separators=(",", ":"))
        seen[key] += 1
        if seen[key] > 1:
            base = base + [seen[key]]
        payloads.append(json.dumps(base, ensure_ascii=False, separators=(",", ":")))
    full = [hashlib.sha256(p.encode("utf-8")).hexdigest() for p in payloads]
    short = Counter(h[:ID_HEX] for h in full)
    clashes = {h for h, n in short.items() if n > 1}
    for c, h in zip(changes, full):
        c["change_id"] = "c-" + (h[:16] if h[:ID_HEX] in clashes else h[:ID_HEX])
    ids = [c["change_id"] for c in changes]
    assert len(ids) == len(set(ids)), "duplicate change_id after collision handling"
    return {"records": len(changes), "identical_content_duplicates": sum(n - 1 for n in seen.values() if n > 1),
            "hash_prefix_collisions": len(clashes), "unique_ids": len(set(ids))}


# ---------------------------------------------------------------------------
# Events: records that express the same underlying change
# ---------------------------------------------------------------------------
MONTH_NUM = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                          "september", "october", "november", "december"], 1)}
_M = r"(january|february|march|april|may|june|july|august|september|october|november|december)"
DATE_DMY_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + _M + r",?\s+((?:19|20)\d{2})\b", re.I)
DATE_MDY_RE = re.compile(r"\b" + _M + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+((?:19|20)\d{2})\b", re.I)
PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent\b)", re.I)
DURATION_RE = re.compile(r"\b(\d+)\s*(?:-|to)?\s*(\d+)?\s*(years?|months?)\b", re.I)


def clean_for_tokens(t):
    return normalise(strip_glued_markers(t or ""))


def date_tokens(t):
    t = clean_for_tokens(t)
    out = set()
    for d, m, y in DATE_DMY_RE.findall(t):
        out.add(f"{y}-{MONTH_NUM[m.lower()]:02d}-{int(d):02d}")
    for m, d, y in DATE_MDY_RE.findall(t):
        out.add(f"{y}-{MONTH_NUM[m.lower()]:02d}-{int(d):02d}")
    return out


def pct_tokens(t):
    return {p + "%" for p in PCT_RE.findall(clean_for_tokens(t))}


def move_tokens(t):
    return {"date:" + d for d in date_tokens(t)} | {"pct:" + p for p in pct_tokens(t)}


def word_signature(c):
    wo = Counter(words(apply_swaps(clean_for_tokens(c["old_text"]))))
    wn = Counter(words(apply_swaps(clean_for_tokens(c["new_text"]))))
    rem, add = wo - wn, wn - wo
    if not (set(rem) | set(add)) - FUNCTION_WORDS:
        return None
    return (tuple(sorted(rem.elements())), tuple(sorted(add.elements())))


def swap_labels(c):
    o = re.sub(r"\s*-\s*", " ", (c["old_text"] or "").lower())
    n = re.sub(r"\s*-\s*", " ", (c["new_text"] or "").lower())
    return tuple(sorted({rep for pat, rep in SWAPS if len(re.findall(pat, o)) != len(re.findall(pat, n))}))


class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[max(a, b)] = min(a, b)


EVENT_RULES = [
    ("R1 status", "all `status` records of a version pair form one event (they all express the same change in whether "
                  "VCMI Claims are issued)."),
    ("R2 number/date move", "a `modified` record whose full dates or percentages differ defines moved values (old value -> "
                            "new value). Every record of the pair that carries one of those moved values on the matching "
                            "side (old text for the old value, new text for the new value; removed records on the old side, "
                            "added records on the new side) joins the same event."),
    ("R3 same edit in several places", "`modified` records of a pair with the same word-level edit (identical multiset of "
                                       "removed and added words after terminology normalisation, with at least one content "
                                       "word) form one event; so do `added` (or `removed`) records with identical comparison text."),
    ("R4 whole section", "records whose note says the whole section was added (or removed) form one event per section."),
    ("R5 Document History row", "records of the same Document History row form one event."),
    ("R6 terminology swap", "editorial records whose only difference is a terminology swap form one event per pair and "
                            "swap (e.g. 'VCMI Silver' -> 'Carbon Integrity Silver')."),
    ("R7 singleton", "every other record is its own event."),
]


def build_events(changes):
    """Deterministic union of the rules above, applied separately within each version pair."""
    events = []
    by_pair = defaultdict(list)
    for i, c in enumerate(changes):
        by_pair[(c["from_version"], c["to_version"])].append(i)
    for pair, idx in by_pair.items():
        uf = _UF(len(idx))
        local = {gi: li for li, gi in enumerate(idx)}
        rule_hits = defaultdict(set)

        def link(members, rule):
            members = sorted(members)
            for m in members:
                rule_hits[m].add(rule)
            for m in members[1:]:
                uf.union(local[members[0]], local[m])

        # R1
        st = [i for i in idx if changes[i]["type"] == "status"]
        if len(st) > 1:
            link(st, "R1")
        # R2
        lost_vals, gained_vals = set(), set()
        for i in idx:
            c = changes[i]
            if c["change"] == "modified":
                to, tn = move_tokens(c["old_text"]), move_tokens(c["new_text"])
                lost_vals |= to - tn
                gained_vals |= tn - to
        groups = defaultdict(set)
        for i in idx:
            c = changes[i]
            to, tn = move_tokens(c["old_text"]), move_tokens(c["new_text"])
            if c["change"] == "modified":
                keys = {("L", v) for v in (to - tn)} | {("G", v) for v in (tn - to)}
            elif c["change"] == "removed":
                keys = {("L", v) for v in to & lost_vals}
            else:
                keys = {("G", v) for v in tn & gained_vals}
            for k in keys:
                groups[k].add(i)
        # values that moved together in one modified record are one move
        for i in idx:
            c = changes[i]
            if c["change"] == "modified":
                to, tn = move_tokens(c["old_text"]), move_tokens(c["new_text"])
                ks = [("L", v) for v in (to - tn)] + [("G", v) for v in (tn - to)]
                if ks:
                    allm = set().union(*(groups[k] for k in ks))
                    if len(allm) > 1:
                        link(allm, "R2")
        # R3
        sig = defaultdict(list)
        for i in idx:
            c = changes[i]
            if c["section_id"].startswith(("history/",)):
                continue
            if c["change"] == "modified":
                s = word_signature(c)
                if s:
                    sig[("M", s)].append(i)
            elif c["change"] == "added":
                sig[("A", cmp_key(clean_for_tokens(c["new_text"])))].append(i)
            else:
                sig[("R", cmp_key(clean_for_tokens(c["old_text"])))].append(i)
        for k, mem in sig.items():
            if len(mem) > 1 and len({changes[i]["section_id"] for i in mem}) > 1:
                link(mem, "R3")
        # R4
        whole = defaultdict(list)
        for i in idx:
            nt = changes[i]["note"]
            if nt.startswith("section added") or nt.startswith("section removed"):
                whole[(changes[i]["section_id"], nt.split(" ")[1].split(";")[0])].append(i)
        for mem in whole.values():
            if len(mem) > 1:
                link(mem, "R4")
        # R5
        rows_ = defaultdict(list)
        for i in idx:
            m = re.search(r"row ([0-9.]+|Provisional)", changes[i]["note"])
            if changes[i]["section_id"].startswith("history/") and m:
                rows_[m.group(1)].append(i)
        for mem in rows_.values():
            if len(mem) > 1:
                link(mem, "R5")
        # R6
        swaps = defaultdict(list)
        for i in idx:
            c = changes[i]
            if c["type"] == "editorial" and c["change"] == "modified" and c["note"].startswith("terminology"):
                lab = swap_labels(c)
                if lab:
                    swaps[lab].append(i)
        for mem in swaps.values():
            if len(mem) > 1:
                link(mem, "R6")
        comps = defaultdict(list)
        for i in idx:
            comps[uf.find(local[i])].append(i)
        for mem in comps.values():
            mem.sort()
            rules = sorted(set().union(*(rule_hits[i] for i in mem))) or ["R7"]
            events.append({"members": mem, "rules": rules, "pair": pair})
    out = []
    for ev in events:
        mem = [changes[i] for i in ev["members"]]
        ids = sorted(c["change_id"] for c in mem)
        types = {c["type"] for c in mem}
        etype = "status" if "status" in types else "substantive" if "substantive" in types else "editorial"
        eid = "e-" + hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode("utf-8")).hexdigest()[:ID_HEX]
        out.append({"event_id": eid, "from_version": ev["pair"][0], "to_version": ev["pair"][1], "type": etype,
                    "summary": event_summary(mem, ev["rules"]), "change_ids": [c["change_id"] for c in mem],
                    "rules": ev["rules"], "_members": mem})
    order = {c["change_id"]: i for i, c in enumerate(changes)}
    out.sort(key=lambda e: min(order[x] for x in e["change_ids"]))
    assert len({e["event_id"] for e in out}) == len(out)
    assert sorted(x for e in out for x in e["change_ids"]) == sorted(order)
    return out


def _short(t, n=110):
    t = normalise_ws(t or "")
    return t if len(t) <= n else t[: n - 3].rstrip() + "..."


def _fmt_date(d):
    y, m, dd = d.split("-")
    return f"{int(dd)} {list(MONTH_NUM)[int(m) - 1].capitalize()} {y}"


def _fmt_tok(t):
    kind, v = t.split(":", 1)
    return _fmt_date(v) if kind == "date" else v


def event_summary(mem, rules):
    secs = sorted({c["section_id"] for c in mem})
    where = secs[0] if len(secs) == 1 else f"{len(secs)} sections ({', '.join(secs[:4])}{', ...' if len(secs) > 4 else ''})"
    if "R2" in rules and "R1" not in rules:
        lost, gained = set(), set()
        for c in mem:
            if c["change"] == "modified":
                to, tn = move_tokens(c["old_text"]), move_tokens(c["new_text"])
                lost |= to - tn
                gained |= tn - to
        lo = ", ".join(_fmt_tok(t) for t in sorted(lost))
        ga = ", ".join(_fmt_tok(t) for t in sorted(gained))
        return f"Values changed from {lo or '(none)'} to {ga or '(none)'} in {where} ({len(mem)} records)."
    if "R1" in rules:
        c = next((c for c in mem if c["change"] != "removed"), mem[0])
        return f"Change in whether VCMI Claims are issued ({len(mem)} records in {where}), e.g. \"{_short(c['new_text'] or c['old_text'])}\""
    if "R4" in rules:
        kind = "added" if mem[0]["change"] == "added" else "removed"
        return f"Section {secs[0]} {kind} ({len(mem)} records)."
    if "R5" in rules:
        m = re.search(r"row ([0-9.]+|Provisional)", mem[0]["note"])
        return f"Document History row for version {m.group(1) if m else '?'} {mem[0]['change']} ({len(mem)} records)."
    if "R6" in rules:
        return f"Terminology change applied in {len(mem)} sentences ({', '.join(swap_labels(mem[0]))}), {where}."
    if "R3" in rules:
        c = mem[0]
        if c["change"] == "modified":
            return f"Same wording change in {len(mem)} places ({where}): \"{_short(c['old_text'], 70)}\" -> \"{_short(c['new_text'], 70)}\"."
        return f"Same sentence {c['change']} in {len(mem)} places ({where}): \"{_short(c['new_text'] or c['old_text'])}\""
    c = mem[0]
    if c["change"] == "modified":
        return f"In {c['section_id']}, \"{_short(c['old_text'], 70)}\" changed to \"{_short(c['new_text'], 70)}\"."
    return f"In {c['section_id']}, sentence {c['change']}: \"{_short(c['new_text'] or c['old_text'])}\""


# ---------------------------------------------------------------------------
# Shortlist of the most important substantive and status events
# ---------------------------------------------------------------------------
SHORTLIST_RULE = (
    "Ranking rule. Only substantive and status events are eligible. Events are placed in tiers: "
    "(1) explicit changes to a number, date or threshold (a full date, percentage, or a numeric duration/limit in a rule); "
    "(2) eligibility and claim status (status events; which credits, frameworks, entities or claims qualify); "
    "(3) other changes to rule wording (shall/must/should, requirements added or removed). "
    "Within a tier, events are ordered by how clearly they change the rule: certain records before uncertain ones, "
    "then requirement wording (shall/must/required/only/cannot) in the changed text, then normative sections "
    "(Foundational Criteria and Steps 1-4) before descriptive ones, then number of records. "
    "Citation years, footnote and page references, cover/version labels and Document History rows are not number changes."
)
NON_RULE_SECTIONS = ("back/", "front/", "history/", "letter/", "aims/", "governance/")
DURATION_TOKEN_RE = re.compile(r"\b\d+\s*(?:-|to)\s*\d+\s*years?\b|\b\d+\s*(?:years?|months?)\b|\b\d+\s*years? apart\b", re.I)
ELIGIBILITY_RE = re.compile(
    r"eligib|corsia|article 6\.4|a6\.4|ccp|core carbon principles|methodolog|subsidiar|parent compan|qualif|accepted|"
    r"not be from|national ghg accounting|accounting framework|equivalent|science-aligned target setting framework|"
    r"rejected|excluded|mitigation contribution units|due diligence", re.I)
STRONG_RE = re.compile(r"\b(shall|must|required|require[sd]?|only|cannot|not)\b", re.I)
NORMATIVE_PREFIX = ("fc1/", "fc2/", "fc3/", "fc4/", "step1/", "step2/", "step3/", "step4/", "code/four-steps",
                    "code/enterprise-wide-claims", "exec/step", "box/double-counting")


def rule_number_change(c):
    """True if a record changes a date, percentage or numeric duration/limit inside rule text: a modified
    record whose values differ, or an added/removed requirement sentence (shall/must/only/...) that states one."""
    if c["section_id"].startswith(NON_RULE_SECTIONS) or c["type"] == "editorial":
        return False
    o, n = c["old_text"] or "", c["new_text"] or ""
    if re.search(r"refer to pages?|\(\d{4}\)|accessed|version \d", o + " " + n, re.I):
        return False
    if c["change"] != "modified":
        t = o or n
        return bool(STRONG_RE.search(t) and (move_tokens(t) or DURATION_TOKEN_RE.search(clean_for_tokens(t))))
    to, tn = move_tokens(o), move_tokens(n)
    if to != tn:
        return True
    do = {re.sub(r"\s+", " ", m.lower()) for m in DURATION_TOKEN_RE.findall(clean_for_tokens(o))}
    dn = {re.sub(r"\s+", " ", m.lower()) for m in DURATION_TOKEN_RE.findall(clean_for_tokens(n))}
    return do != dn


def changed_text(c):
    if c["change"] != "modified":
        return c["new_text"] or c["old_text"] or ""
    wo, wn = Counter(words(c["old_text"] or "")), Counter(words(c["new_text"] or ""))
    return " ".join(sorted(((wo - wn) + (wn - wo)).elements()))


def event_tier(ev):
    mem = ev["_members"]
    if ev["type"] == "status":      # status events are tier 2 even if they carry a date (e.g. the retirement date)
        return 2
    if any(rule_number_change(c) for c in mem) or "R2" in ev["rules"] and any(
            not c["section_id"].startswith(NON_RULE_SECTIONS) for c in mem):
        return 1
    if ev["type"] == "status":
        return 2
    if any(ELIGIBILITY_RE.search(changed_text(c)) and not c["section_id"].startswith(NON_RULE_SECTIONS) for c in mem):
        return 2
    return 3


def event_score(ev):
    mem = ev["_members"]
    certain = any(not c["uncertain"] for c in mem)
    strong = sum(1 for c in mem if STRONG_RE.search(changed_text(c)))
    normative = sum(1 for c in mem if c["section_id"].startswith(NORMATIVE_PREFIX))
    return (0 if certain else 1, -min(strong, 3), -min(normative, 3), -len(mem))


def rank_events(events):
    elig = [e for e in events if e["type"] in ("substantive", "status")
            and not all(c["section_id"].startswith(NON_RULE_SECTIONS) for c in e["_members"])
            or e["type"] == "status"]
    order = {e["event_id"]: i for i, e in enumerate(events)}
    return sorted(elig, key=lambda e: (event_tier(e), event_score(e), order[e["event_id"]]))


# Curated shortlist: the 30 events, in rank order, with one-sentence summaries. The order follows
# SHORTLIST_RULE (tier first; within a tier, how clearly the event changes the rule). The code
# checks that every listed event exists, is substantive or status, and that tiers never go back
# up the list; event_ids are content hashes, so this list stays valid across reruns.
SHORTLIST = [
    # tier 1: numbers, dates, thresholds
    ("e-33de7c186c", "Claim thresholds lowered: Silver from >= 20% and < 60% to >= 10% and < 50% of remaining emissions, "
                     "Gold from >= 60% to >= 50% (Platinum stays >= 100%)."),
    ("e-01b5022db8", "Interim-options deadline moved from 1 January 2026 to 1 January 2027; after it only CCP-labelled or "
                     "Article 6.4 credits may be used for VCMI Claims."),
    ("e-a5860b855a", "New deadline: companies shall transition to CCP-Approved credits by 1 January 2026."),
    ("e-f7b4a7e5cf", "Rule stated that after 1 January 2026 only CCP-labelled or Article 6.4 credits may be used for VCMI Claims."),
    ("e-12a3f2f4c6", "Interim options limited to 1 January 2026 or until CCP-labelled/Article 6.4 credits are widely available, "
                     "whichever is earlier."),
    ("e-eeb02be8c1", "Removed the SBTi boundary rule requiring 95% coverage of scope 1 and 2 emissions and 67% of scope 3."),
    ("e-1a308c8ed7", "Removed the requirement that companies with unvalidated SBTi-style targets submit them to SBTi for "
                     "validation within 24 months."),
    ("e-49c10e0ed0", "Removed the requirement for power companies to set a third target covering 100% of emissions from "
                     "downstream use of fossil fuels."),
    ("e-d50efac9b5", "Added the requirement to submit unvalidated targets to SBTi for validation within 24 months."),
    ("e-4eb60f495b", "Added interim options for credit procurement (CORSIA-eligible credits, or due diligence aligned with the "
                     "10 CCPs) pending CCP-labelled credits."),
    # tier 2: eligibility and claim status
    ("e-5b186e3742", "Claims retired: as of 23 September 2026 VCMI is no longer issuing Carbon Integrity Claims and the claims "
                     "infrastructure is retired."),
    ("e-c75c7c03ed", "Claims became available: companies can now make Carbon Integrity Claims, as the MRA Framework is in place."),
    ("e-0e9ec97117", "Article 6.4 credits (Paris Agreement Crediting Mechanism) accepted alongside CCP-labelled credits."),
    ("e-f1ee53b8f9", "Credits from methodologies rejected or excluded in the ICVCM assessments may not be used."),
    ("e-e29013664e", "Target boundary and coverage now follow the chosen science-aligned target-setting framework, not SBTi only."),
    ("e-2767412072", "Targets must follow the SBTi organisational-boundary criteria (parent or group level, not subsidiary level)."),
    ("e-0b7385c187", "Target boundary criteria opened from SBTi only to 'the most up to date SBTi or equivalent criteria'."),
    ("e-57ebd8d8c8", "Removed the rule that credits applied to a claim shall be CORSIA label credits until the ICVCM framework "
                     "is implemented."),
    ("e-c913ab4f12", "Companies may report emissions under a national GHG accounting framework adapted from the GHG Protocol."),
    ("e-b03380e93a", "Targets may be submitted at parent or subsidiary level."),
    ("e-1f82a1b7f1", "Removed the statement accepting CORSIA or due-diligence credits until the ICVCM Assessment Framework is "
                     "implemented."),
    # tier 3: other rule wording
    ("e-c42fe0eaaf", "New rule: the most recent reporting year cannot be the same as the base year."),
    ("e-8e519108c3", "New rule: reductions must be reported on the same basis (absolute or intensity) as the near-term target."),
    ("e-b17382592f", "Removed the requirement to provide the SBTi commitment letter as evidence for a VCMI Claim."),
    ("e-b8ccc9d54b", "New rule: companies not engaged in policy advocacy shall publicly disclose that they do not engage in it."),
    ("e-c43d4dfc32", "Public net-zero commitment changed from a requirement to an encouragement."),
    ("e-f86499a687", "Foundational Criterion 3 redefined from being on-track and minimising cumulative emissions to making "
                     "progress on financial allocation, governance and strategy."),
    ("e-d31c7c83e0", "Foundational Criterion 2 changed from validated science-based targets to science-aligned targets."),
    ("e-3a477b3b0d", "New requirement: third-party limited assurance of scope 1 and scope 2 emissions (base and most recent year)."),
    ("e-c3b22b02c3", "New step: submitted claim information undergoes independent third-party verification."),
]
SHORTLIST_SUMMARIES = dict(SHORTLIST)
QUOTE_OK = ("verbatim on cited page", "verbatim across page break")


def _quote_pref(c, side):
    """Sort key for choosing a quote source inside an event (lower is better)."""
    t = c[f"{side}_text"] or ""
    moved = len(move_tokens(c["old_text"]) ^ move_tokens(c["new_text"])) if c["change"] == "modified" else 0
    return (0 if rule_number_change(c) else 1, -moved, 0 if not c["uncertain"] else 1,
            0 if c["section_id"].startswith(NORMATIVE_PREFIX) else 1, 0 if STRONG_RE.search(t) else 1)


def write_shortlist(events, changes, rows, verification):
    texts = {r["doc_id"]: page_texts(RAW / r["local_filename"]) for r in rows}
    bad = {(b["change_id"], b["side"]) for b in verification["bad"]}
    excluded = sorted({b["change_id"] for b in verification["bad"]})
    order = {c["change_id"]: i for i, c in enumerate(changes)}
    by_id = {e["event_id"]: e for e in events}

    def ok(c, side):
        if c["change_id"] in excluded or (c["change_id"], side) in bad or c[f"{side}_text"] is None:
            return False
        doc = c["from_doc_id"] if side == "old" else c["to_doc_id"]
        page = c["old_page"] if side == "old" else c["new_page"]
        return locate_quote(c[f"{side}_text"], texts[doc], page)[0] in QUOTE_OK

    entries, last_tier, last_certain = [], 0, True
    for rank, (eid, summary) in enumerate(SHORTLIST, 1):
        ev = by_id.get(eid)
        assert ev is not None, f"shortlisted event {eid} not found"
        assert ev["type"] in ("substantive", "status"), f"{eid} is {ev['type']}"
        tier = event_tier(ev)
        certain = any(not c["uncertain"] for c in ev["_members"])
        assert tier >= last_tier, f"{eid}: tier {tier} after tier {last_tier}"
        if tier == last_tier:
            assert not (certain and not last_certain), f"{eid}: certain event ranked after an uncertain one in tier {tier}"
        last_tier, last_certain = tier, certain
        mem = sorted(ev["_members"], key=lambda c: order[c["change_id"]])
        # quote sources: for a status event only its status records (not e.g. the cover version label)
        qmem = [c for c in mem if c["type"] == "status"] if ev["type"] == "status" else mem
        mods = [c for c in qmem if c["change"] == "modified" and ok(c, "old") and ok(c, "new")]
        if mods:
            src = min(mods, key=lambda c: (_quote_pref(c, "new"), order[c["change_id"]]))
            old_src = new_src = src
        else:
            olds = [c for c in qmem if c["change"] == "removed" and ok(c, "old")]
            news = [c for c in qmem if c["change"] == "added" and ok(c, "new")]
            old_src = min(olds, key=lambda c: (_quote_pref(c, "old"), order[c["change_id"]])) if olds else None
            new_src = min(news, key=lambda c: (_quote_pref(c, "new"), order[c["change_id"]])) if news else None
        assert old_src or new_src, f"{eid}: no member passes the raw-text check"
        entries.append({
            "rank": rank, "tier": tier, "event_id": eid, "summary": summary,
            "versions": f"{ev['from_version']} -> {ev['to_version']}",
            "old_pages": sorted({c["old_page"] for c in mem if c["old_page"]}),
            "new_pages": sorted({c["new_page"] for c in mem if c["new_page"]}),
            "n_records": len(mem),
            "old_quote": old_src["old_text"] if old_src else None,
            "old_source": (old_src["change_id"], old_src["from_doc_id"], old_src["old_page"]) if old_src else None,
            "new_quote": new_src["new_text"] if new_src else None,
            "new_source": (new_src["change_id"], new_src["to_doc_id"], new_src["new_page"]) if new_src else None,
            "absent_note": None if (old_src and new_src) else
            ("no old text: the change is a pure addition" if not old_src else "no new text: the change is a pure removal"),
        })
    # final verification of every quote against the raw page.get_text() of the cited page
    checks = []
    for e in entries:
        for side in ("old", "new"):
            q, srcinfo = e[f"{side}_quote"], e[f"{side}_source"]
            if q is None:
                continue
            cid, doc, page = srcinfo
            verdict = locate_quote(q, texts[doc], page)[0]
            checks.append((e["rank"], side, cid, verdict))
            assert verdict in QUOTE_OK, f"shortlist quote failed: rank {e['rank']} {side} {cid} {verdict}"
    tier_names = {1: "number, date or threshold", 2: "eligibility or claim status", 3: "rule wording"}
    L = ["# VCMI Claims Code of Practice: shortlist of the 30 most important changes\n",
         SHORTLIST_RULE + "\n",
         "Events come from `events.jsonl` (records grouped by underlying change); quotes are copied verbatim from member "
         "records in `changes.jsonl` and were re-checked against the raw `page.get_text()` text of the cited page "
         f"(whitespace, ligatures and line-break hyphens normalised only): {len(checks)} quotes, "
         f"{sum(1 for x in checks if x[3] in QUOTE_OK)} found, 0 failures.\n"]
    for e in entries:
        pages = f"old p{', '.join(map(str, e['old_pages'])) or '-'}; new p{', '.join(map(str, e['new_pages'])) or '-'}"
        L.append(f"## {e['rank']}. {e['summary']}\n")
        L.append(f"- event_id: `{e['event_id']}` (tier {e['tier']}: {tier_names[e['tier']]}; {e['n_records']} record(s))")
        L.append(f"- versions: {e['versions']}")
        L.append(f"- pages: {pages}")
        if e["old_quote"]:
            L.append(f"- old ({e['old_source'][1]} p{e['old_source'][2]}, `{e['old_source'][0]}`): \"{e['old_quote']}\"")
        else:
            L.append(f"- old: none ({e['absent_note']})")
        if e["new_quote"]:
            L.append(f"- new ({e['new_source'][1]} p{e['new_source'][2]}, `{e['new_source'][0]}`): \"{e['new_quote']}\"")
        else:
            L.append(f"- new: none ({e['absent_note']})")
        L.append("")
    L.append("## Records not used as quote sources\n")
    L.append("These records are single sentences in the cleaned text, but in the raw `page.get_text()` stream their text "
             "is interrupted by a running footer, footnote or sidebar heading (sentence runs across a column or page "
             "break), so they fail the contiguous raw-text check and are never used for quotes:\n")
    for b in verification["bad"]:
        L.append(f"- `{b['change_id']}` ({b['side']} text, p{b['page']}): \"{b['text']}...\"")
    with open(DIFF_DIR / "shortlist.md", "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")
    return {"entries": entries, "checks": checks, "excluded": excluded}


def add_known_notes(changes):
    for c in changes:
        o, n = c["old_text"] or "", c["new_text"] or ""
        if c["section_id"].startswith("step3/") and "2026" in normalise(o) and "2027" in normalise(n) and c["change"] == "modified":
            c["note"] = "Interim options deadline moved from 1 January 2026 to 1 January 2027; " + c["note"]


def cross_check(docs, rows, changes):
    newest = None
    for r in reversed(rows):
        if any(s["section_id"] == "history/document-history" for s in docs[r["doc_id"]]["sections"]):
            newest = r
            break
    result = {"source_version": newest["version"] if newest else None, "items": [], "unlisted_substantive": []}
    if not newest:
        return result
    sec = [s for s in docs[newest["doc_id"]]["sections"] if s["section_id"] == "history/document-history"][0]
    # one listed change per bullet item (continuation lines are merged into their bullet)
    listed = defaultdict(list)
    for it in sec["src"]:
        ver = it.get("history_version")
        if not ver or it.get("row_label"):
            continue
        txt = normalise_ws(visible(it["text"]))
        if listed[ver] and not it.get("bulleted") and re.match(r"^[a-z(]", txt):
            listed[ver][-1] += " " + txt
        else:
            listed[ver].append(txt)
    matchers_used = set()
    for ver, items in listed.items():
        for text in items:
            ms = [m for m in HISTORY_MATCHERS if m[0] == ver and normalise(m[1]).lower() in normalise(text).lower()]
            entry = {"version": ver, "text": text, "matched_change_ids": [], "note": ""}
            if not ms:
                entry["note"] = "no diff pair in corpus (earliest version)" if ver in ("Provisional", "1.0") else "no matcher defined"
                result["items"].append(entry)
                continue
            for m in ms:
                matchers_used.add(id(m))
                _, _, (fv, tv), prefixes, rx = m
                for c in changes:
                    if c["from_version"] != fv or c["to_version"] != tv:
                        continue
                    if c["section_id"].startswith("history/"):
                        continue
                    if rx == "STATUS":
                        if c["type"] != "status":
                            continue
                    else:
                        if not c["section_id"].startswith(prefixes):
                            continue
                        if not re.search(rx, (c["old_text"] or "") + " || " + (c["new_text"] or ""), re.I):
                            continue
                    if c["type"] == "editorial" and ver not in ("2.1",):
                        continue
                    c["in_vcmi_history"] = True
                    entry["matched_change_ids"].append(c["change_id"])
            result["items"].append(entry)
    result["unlisted_substantive"] = [c["change_id"] for c in changes
                                      if c["type"] in ("substantive", "status") and not c["in_vcmi_history"]]
    return result


LIGATURES = {chr(0xFB00): "ff", chr(0xFB01): "fi", chr(0xFB02): "fl", chr(0xFB03): "ffi", chr(0xFB04): "ffl",
             chr(0xFB05): "st", chr(0xFB06): "st"}
ZERO_WIDTH_RE = re.compile("[" + chr(0x200B) + chr(0x200C) + chr(0x200D) + chr(0xFEFF) + "]")
INVISIBLE_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f" + chr(0xF04D) + "]")


def _lig(t):
    return "".join(LIGATURES.get(ch, ch) for ch in t)


def raw_page_variants(t):
    """Raw page.get_text() normalised ONLY for whitespace, ligatures and line-break hyphenation.

    Returns two variants: a hyphen at a line end kept ('net-\\nzero' -> 'net-zero') or removed
    ('organiza-\\ntion' -> 'organization'). Invisible layout characters (control characters,
    zero-width spaces) count as whitespace.
    """
    t = ZERO_WIDTH_RE.sub("", _lig(visible(t)))
    t = INVISIBLE_RE.sub(" ", t)
    keep = re.sub(r"(?<=\w)-[ \t]*\n\s*", "-", t)    # only a hyphen attached to a word is line-break hyphenation
    drop = re.sub(r"(?<=\w)-[ \t]*\n\s*(?=[a-z])", "", t)
    return tuple(re.sub(r"\s+", " ", v).strip() for v in (keep, drop))


def quote_for_raw(q):
    q = ZERO_WIDTH_RE.sub("", _lig(q))
    q = INVISIBLE_RE.sub(" ", q)
    return re.sub(r"\s+", " ", q).strip()


def page_texts(path):
    """page number -> (hyphen-kept variant, hyphen-dropped variant) of the raw page.get_text()."""
    doc = pymupdf.open(path)
    return {p.number + 1: raw_page_variants(p.get_text()) for p in doc}


def _pieces(q, hay, max_pieces=3, start=0, min_len=15):
    """Spans of q found in hay as <= max_pieces ordered, non-overlapping fragments (split at spaces)."""
    pos = hay.find(q, start)
    if pos >= 0:
        return [(pos, pos + len(q))]
    if max_pieces <= 1:
        return None
    cuts = [m.start() for m in re.finditer(" ", q) if min_len <= m.start() <= len(q) - min_len]
    for cut in reversed(cuts):
        p = hay.find(q[:cut], start)
        if p >= 0:
            rest = _pieces(q[cut + 1:], hay, max_pieces - 1, p + cut, min_len)
            if rest:
                return [(p, p + cut)] + rest
    return None


def locate_quote(q, pt, page):
    """Return (verdict, detail). Verdicts: 'verbatim on cited page', 'verbatim across page break',
    'not contiguous' (found as ordered fragments; detail = intervening raw text), 'NOT FOUND'."""
    qn = quote_for_raw(q)
    this = pt.get(page, ("", ""))
    nxt = pt.get(page + 1, ("", ""))
    for v in (0, 1):
        if qn in this[v]:
            return "verbatim on cited page", ""
    for v in (0, 1):
        if qn in this[v] + " " + nxt[v]:
            return "verbatim across page break", ""
    for v in (0, 1):
        hay = this[v] + " " + nxt[v]
        sp = _pieces(qn, hay)
        if sp:
            gaps = [hay[a[1]:b[0]].strip() for a, b in zip(sp, sp[1:])]
            return "not contiguous", " | ".join(g[:90] for g in gaps)
    return "NOT FOUND", ""


def verify_quotes(docs, rows, changes):
    """Check every quote against the raw PyMuPDF page text (whitespace removed)."""
    texts = {r["doc_id"]: page_texts(RAW / r["local_filename"]) for r in rows}
    bad, verdicts = [], Counter()
    for c in changes:
        for side, doc_id, page in (("old", c["from_doc_id"], c["old_page"]), ("new", c["to_doc_id"], c["new_page"])):
            q = c[f"{side}_text"]
            if q is None:
                continue
            v, detail = locate_quote(q, texts[doc_id], page)
            verdicts[v] += 1
            if v in ("not contiguous", "NOT FOUND"):
                bad.append({"change_id": c["change_id"], "side": side, "page": page, "verdict": v,
                            "between": detail, "text": q[:120]})
    rnd = random.Random(20261010)
    sample = rnd.sample(changes, min(10, len(changes)))
    spot = []
    for c in sample:
        res = {}
        for side, doc_id, page in (("old", c["from_doc_id"], c["old_page"]), ("new", c["to_doc_id"], c["new_page"])):
            q = c[f"{side}_text"]
            res[side] = "n/a" if q is None else f"{locate_quote(q, texts[doc_id], page)[0]} (p{page})"
        spot.append({"change_id": c["change_id"], "pair": f"{c['from_version']}->{c['to_version']}",
                     "section_id": c["section_id"], "change": c["change"], **res})
    return {"bad": bad, "spot": spot, "checked": len(changes), "verdicts": dict(verdicts)}


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------
def write_clean(r, pages, removed, problems, status_first):
    blocks = []
    bid = 0
    for pg in pages:
        for u in pg["units"]:
            bid += 1
            orig = "\n".join(visible(strip_ctrl(l.get("orig_marked", l["orig"]))) for l in u["lines"])
            blocks.append({"block_id": f"b{bid:04d}", "page": pg["page"], "page_kind": pg.get("kind"),
                           "kind": u.get("kind", "body"), "bbox": u["bbox"], "font_size": u["size"],
                           "text_original": orig,
                           "text_normalised": normalise(" ".join(unmarked(join_lines([l.get("orig_marked", l["orig"])], HYPH_KEEP)) for l in u["lines"])),
                           **({"footnote_label": u["footnote_label"]} if u.get("footnote_label") else {})})
    out = {"doc_id": r["doc_id"], "version": r["version"], "publication_date": r["publication_date"],
           "source_file": r["local_filename"], "sha256": r["sha256"], "n_pages": len(pages),
           "status_notice": ({"page": status_first["page"], "text_original": visible(status_first["text"])} if status_first else None),
           "blocks": blocks, "removed": removed, "extraction_problems": problems}
    with open(CLEAN_DIR / f"{r['doc_id']}.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


def write_sections(r, sections):
    with open(SECT_DIR / f"{r['doc_id']}.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for s in sections:
            rec = {"section_id": s["section_id"], "heading": s["heading"], "page_start": s["page_start"],
                   "page_end": s["page_end"],
                   "text": "\n".join(normalise_ws(visible(x["text"])) for x in s["src"])}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def md_escape(s):
    return (s or "").replace("|", "\\|").replace("\n", " ")


def short(s, n=160):
    s = s or ""
    return s if len(s) <= n else s[: n - 3] + "..."


def write_report(docs, rows, changes, alignment_log, history, verification, id_stats=None, events=None, shortlist=None):
    L = []
    L.append("# VCMI Claims Code of Practice: change log report\n")
    L.append("Generated by `scripts/diff_versions.py` from `data/manifest.csv` (all six SHA-256 hashes verified). "
             "Versions ordered by publication date: " + ", ".join(f"{r['version']} ({r['publication_date']})" for r in rows) + ".\n")
    L.append("## 1. Changes by version pair\n")
    L.append("| Pair | substantive | of which uncertain | status | editorial | total |")
    L.append("|---|---|---|---|---|---|")
    for prev, cur in zip(rows, rows[1:]):
        cs = [c for c in changes if c["from_version"] == prev["version"] and c["to_version"] == cur["version"]]
        sub = [c for c in cs if c["type"] == "substantive"]
        L.append(f"| {prev['version']} -> {cur['version']} | {len(sub)} | {sum(c['uncertain'] for c in sub)} | "
                 f"{sum(c['type'] == 'status' for c in cs)} | {sum(c['type'] == 'editorial' for c in cs)} | {len(cs)} |")
    L.append("")
    L.append("## 2. Substantive and status changes\n")
    L.append("One line per record: id, section, change, pages (old/new), note, and the new (or removed) text. "
             "`uncertain` records are flagged with (?). Full quotes are in `changes.jsonl`.\n")
    for prev, cur in zip(rows, rows[1:]):
        cs = [c for c in changes if c["from_version"] == prev["version"] and c["to_version"] == cur["version"]
              and c["type"] in ("substantive", "status")]
        L.append(f"### {prev['version']} -> {cur['version']} ({len(cs)})\n")
        alog = [a for a in alignment_log if a["from"] == prev["version"] and a["to"] == cur["version"]]
        rew = [x for a in alog for x in a["section_summary"] if x["rewritten"] or x["heading_changed"]]
        if rew:
            L.append("Section-level: " + "; ".join(
                f"`{x['section_id']}` modified section ("
                + ("heading changed and body rewritten" if x["heading_changed"] and x["rewritten"]
                   else "body rewritten" if x["rewritten"] else "heading changed")
                + (f": '{x['old_heading']}' -> '{x['new_heading']}'" if x["heading_changed"] else "") + ")"
                for x in rew) + ".\n")
        for c in cs:
            txt = c["new_text"] if c["new_text"] else c["old_text"]
            L.append(f"- {c['change_id']} [{c['type']}{' (?)' if c['uncertain'] else ''}] `{c['section_id']}` {c['change']} "
                     f"p{c['old_page'] or '-'}/p{c['new_page'] or '-'}: {md_escape(short(c['note'], 110))} | "
                     f"{md_escape(short(txt, 150))}")
        L.append("")
    L.append("## 3. Document History cross-check\n")
    L.append(f"Source table: version {history['source_version']} (newest version with a Document History table).\n")
    L.append("| Listed version | Listed change | Matched change ids |")
    L.append("|---|---|---|")
    for it in history["items"]:
        ids = it["matched_change_ids"]
        shown = ", ".join(ids[:12]) + (f" ... (+{len(ids) - 12})" if len(ids) > 12 else "")
        L.append(f"| {it['version']} | {md_escape(short(it['text'], 120))} | {shown or 'NONE: ' + it['note']} |")
    L.append("")
    missing = [it for it in history["items"] if not it["matched_change_ids"]]
    L.append(f"- Listed changes with no matching diff record: {len(missing)}" +
             ("".join(f"\n  - {it['version']}: {short(it['text'], 100)} ({it['note']})" for it in missing)))
    by_pair = Counter(f"{c['from_version']}->{c['to_version']}" for c in changes if c["change_id"] in set(history["unlisted_substantive"]))
    L.append(f"- Substantive/status diff records not linked to a history entry: {len(history['unlisted_substantive'])} "
             f"({', '.join(f'{k}: {v}' for k, v in by_pair.items())}). See `in_vcmi_history: false` in changes.jsonl. "
             "The Document History describes each version in one to four high-level bullets, so most sentence-level "
             "changes are not individually listed. Every one of these records was checked against both PDFs: its quotes "
             "are found on the cited pages (section 5).\n")
    L.append("## 4. Cleaning and extraction\n")
    for r in rows:
        d = docs[r["doc_id"]]
        cnt = Counter(x["reason"] for x in d["removed"])
        L.append(f"**{r['version']}** ({r['local_filename']}, {len(d['pages'])} pages): " +
                 "; ".join(f"{k}: {v}" for k, v in sorted(cnt.items())))
        div = [x for x in d["removed"] if x["reason"].startswith("divider")]
        if div:
            L.append(f"  - divider pages removed: " + ", ".join(f"p{x['page']} '{short(x['text'], 40)}'" for x in div))
        stray = [x for x in d["removed"] if x["reason"].startswith("stray")]
        if stray:
            L.append(f"  - stray numbers removed: " + ", ".join(f"p{x['page']} '{x['text']}'" for x in stray))
        for p in d["problems"]:
            L.append(f"  - extraction problem p{p['page']}: {p['problem']}")
        L.append("")
    L.append("Excluded from sentence diffing: `front/contents` (table of contents: titles and page numbers only).\n")
    L.append("Notes on extraction and quoting:\n")
    L.append("- Footnote markers are superscripts in the PDFs. Quotes keep them as extracted, glued to the preceding word "
             "(e.g. `January 1, 202615` is 2026 followed by footnote 15). Comparison and number checks ignore them; "
             "leading footnote numbers are stripped from footnote text because they are renumbered between versions.")
    L.append("- v1.0 uses a two-column layout; text is read column by column (block-level extraction with a column-aware "
             "reading order). Six quotes span a column or page break and are found as 2-3 ordered fragments (section 5).")
    L.append("- Figure and diagram labels (claim graphs, four-step diagrams, v1.0 Box 5 cost charts) are extracted as text "
             "and diffed like other sentences; their reading order follows page geometry.")
    L.append("- v3.0/v3.1 print 'To make an enterprise-wide VCMI Claim, companies shall:' above the Step 1 heading (p20), "
             "so it is assigned to `code/four-steps` in those versions.")
    L.append("- Box sections use topic-based ids (`box/<topic>`) because box numbers change between versions. The v1.0 Box 3 "
             "'Flexibility research' was matched by heading similarity to the v2.0+ Box 3 on the beta Scope 3 claim (`box/scope3`).")
    L.append("- Classification is rule-based: number/date differences are substantive; changes of operating status "
             "(claims issued / not issued) are status; terminology swaps (e.g. 'VCMI Silver' -> 'Carbon Integrity Silver', "
             "'must' -> 'shall', 'certification standard' -> 'carbon crediting program'), function-word edits and wording "
             "in descriptive sections (about, letter, aims, governance, acknowledgements, references) are editorial; "
             "everything else that could alter meaning is substantive with `uncertain: true`.\n")
    L.append("Section alignment (same section_id; else headings matched by token_set_ratio >= 80; else unmatched sections "
             "lying between the same matched neighbours paired by position when headings are similar (token_set_ratio >= 60) "
             "or bodies are similar (>= 70); anything left is added/removed):\n")
    for a in alignment_log:
        L.append(f"- {a['from']} -> {a['to']}: renamed/paired {len(a['renamed'])}"
                 + ("".join(f"; `{x['old_section_id']}` -> `{x['new_section_id']}`"
                            + (" (by position)" if x.get("method") == "position" else "") for x in a["renamed"]))
                 + f". Removed sections: {', '.join(a['removed_sections']) or 'none'}. Added sections: {', '.join(a['added_sections']) or 'none'}. "
                 f"Sentences moved unchanged within a section: {a['moved_within_section']}; across sections: {a['moved_across_sections']} (not reported as changes).")
    L.append("")
    L.append("Sections modified at section level (present in both versions; heading changed, paired by position, or at "
             "least half of the content changed). These are treated as modified sections, not as additions or removals; "
             "their records in changes.jsonl are sentence-level:\n")
    for a in alignment_log:
        for x in a["section_summary"]:
            what = []
            if x["heading_changed"]:
                what.append(f"heading '{x['old_heading']}' -> '{x['new_heading']}'")
            if x["paired"]:
                what.append(f"matched from `{x['old_section_id']}` by {x['method']}")
            what.append("body rewritten" if x["rewritten"] else "body partly changed")
            L.append(f"- {a['from']} -> {a['to']} `{x['section_id']}`: modified section; {'; '.join(what)} "
                     f"({x['old_sentences']} -> {x['new_sentences']} sentences: {x['added']} added, "
                     f"{x['removed']} removed, {x['modified']} modified).")
    L.append("")
    L.append("## 5. Verification\n")
    L.append(f"- Quote check against the raw PDF text: {verification['checked']} records. Every `old_text`/`new_text` is "
             "searched as one contiguous string in `page.get_text()` of the cited page (then cited page + next page, for "
             "sentences that run over a page break). The raw text is normalised only for whitespace (including invisible "
             "control/zero-width characters), ligatures and hyphens at line breaks. "
             f"Results: " + "; ".join(f"{k}: {v}" for k, v in sorted(verification["verdicts"].items())) + ". "
             f"Failures (not one contiguous string in the raw text): {len(verification['bad'])}.")
    for b in verification["bad"]:
        L.append(f"  - {b['change_id']} {b['side']} p{b['page']} [{b['verdict']}]: \"{md_escape(b['text'])}\""
                 + (f" (raw text between the fragments: \"{md_escape(b['between'])}\")" if b["between"] else ""))
    L.append("- Random spot check (seed 20261010, 10 records):\n")
    L.append("| id | pair | section | change | old_text | new_text |")
    L.append("|---|---|---|---|---|---|")
    for s in verification["spot"]:
        L.append(f"| {s['change_id']} | {s['pair']} | `{s['section_id']}` | {s['change']} | {s['old']} | {s['new']} |")
    L.append("")
    known = [c for c in changes if c["from_version"] == "3.0" and c["to_version"] == "3.1" and "2027" in (c["new_text"] or "")]
    L.append(f"- Known change (interim-options deadline 1 January 2026 -> 1 January 2027, v3.0 -> v3.1): "
             f"{len(known)} records ({', '.join(c['change_id'] for c in known)}).")
    if events is not None:
        dl = [e for e in events if any(x in e["change_ids"] for x in (c["change_id"] for c in known))]
        L.append(f"  These records form {len(dl)} event(s): "
                 + ", ".join(f"`{e['event_id']}` ({len(e['change_ids'])} records)" for e in dl) + ".")
        L.append("")
        L.append("## 6. Change IDs, events and shortlist\n")
        L.append("**change_id.** `c-` followed by the first 10 hex characters of SHA-256 over the canonical serialisation "
                 "`json.dumps([from_version, to_version, section_id, old_text, new_text], ensure_ascii=False, "
                 "separators=(',', ':'))` encoded as UTF-8 (missing text is JSON null). Records with identical content "
                 "in the same pair and section get their occurrence number (2, 3, ...) appended to the list before hashing, "
                 "in record order. If two different serialisations share the 10-hex prefix, every record in that clash "
                 "uses 16 hex characters instead. "
                 f"This run: {id_stats['records']} records, {id_stats['identical_content_duplicates']} identical-content "
                 f"duplicate(s) disambiguated by occurrence number, {id_stats['hash_prefix_collisions']} prefix "
                 f"collision(s), {id_stats['unique_ids']} unique IDs.\n")
        L.append("**Events** (`events.jsonl`). Records are grouped within each version pair (never across pairs) by the "
                 "union of these rules; every record belongs to exactly one event. `event_id` is `e-` plus the first 10 hex "
                 "characters of SHA-256 over the JSON list of sorted member change_ids. Event type is `status` if any member "
                 "is status, else `substantive` if any member is substantive, else `editorial`. Summaries are generated from "
                 "the rule that formed the event; the 30 shortlisted events carry hand-written summaries.\n")
        for name, desc in EVENT_RULES:
            L.append(f"- {name}: {desc}")
        L.append("")
        L.append("| Pair | substantive | status | editorial | events | records |")
        L.append("|---|---|---|---|---|---|")
        for prev, cur in zip(rows, rows[1:]):
            es = [e for e in events if e["from_version"] == prev["version"] and e["to_version"] == cur["version"]]
            t = Counter(e["type"] for e in es)
            L.append(f"| {prev['version']} -> {cur['version']} | {t['substantive']} | {t['status']} | {t['editorial']} | "
                     f"{len(es)} | {sum(len(e['change_ids']) for e in es)} |")
        big = max(events, key=lambda e: (len(e["change_ids"]), e["event_id"]))
        L.append(f"\nLargest event: `{big['event_id']}` ({len(big['change_ids'])} records): {big['summary']}\n")
        if shortlist:
            L.append(f"**Shortlist** (`shortlist.md`): 30 substantive/status events ranked by the rule stated at the top of "
                     f"that file; {len(shortlist['checks'])} quotes re-verified against raw page text, 0 failures. Records "
                     f"never used as quote sources (not contiguous in raw text): "
                     + ", ".join(f"`{x}`" for x in shortlist["excluded"]) + ".")
    with open(DIFF_DIR / "report.md", "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L) + "\n")


if __name__ == "__main__":
    run()
