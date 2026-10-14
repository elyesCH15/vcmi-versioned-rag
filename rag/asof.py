"""Date-based routing for the live demo.

In the evaluation, the version was read from the question text ("as of 1 March 2024", "under version 2.1").
In the demo, the user picks a date on a slider instead, so the date decides the version:

  plain question           -> the version in force on the selected date
  "how did X change"       -> every version published up to the selected date (history as known on that date)
  question names a version -> that version; the slider is ignored and the app says so
  question names a date    -> the version in force on that date; the slider is ignored and the app says so

Retrieval, prompts and the answer format are reused unchanged from rag.py, so the demo runs the
same pipeline that was evaluated; only the routing input differs.
"""
import csv, importlib.util, re
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
_spec = importlib.util.spec_from_file_location("ragcore", HERE / "rag.py")
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)

CHANGE = re.compile(r"\bwhich version\b|\bwhen did\b|\blast change|\bfirst (?:introduced|appear)|\bhow (?:has|have|did)\b.*\bchange"
                    r"|\bwhat changed\b|\bchanges? (?:to|in)\b|\bevolv", re.I)
NAMED = re.compile(r"\b(?:version|v)\s?(\d+(?:\.\d+)?)\b", re.I)
DATED = re.compile(r"\b(\d{1,2}) (" + "|".join(R.MONTHS) + r") (\d{4})\b", re.I)


def load(today=None):
    """Chunks, versions (with fresh version cards and source links) and the BM25 index."""
    R.TODAY = today or date.today()
    chunks, versions, bm25 = R.load_index()
    links = {r["version"]: r["source_page"] for r in csv.DictReader(open(ROOT / "data" / "manifest.csv", encoding="utf-8-sig"))}
    for v in versions:
        if isinstance(v.get("superseded_on"), str):
            v["superseded_on"] = date.fromisoformat(v["superseded_on"])
        v["card"] = R.version_card(v, versions)
        v["source"] = links.get(v["version"])
    return chunks, versions, bm25


def in_force(d, versions):
    """The version in force on date d: the latest one published on or before d (None before the first)."""
    cands = [v for v in versions if v["published"] <= d]
    return cands[-1] if cands else None


def plan(question, d, versions):
    """Decide which versions to search. Returns a dict: mode, versions, reason, override."""
    vmap = {v["version"]: v for v in versions}
    m = NAMED.search(question)
    if m:
        ver = m.group(1) if "." in m.group(1) else m.group(1) + ".0"
        if ver not in vmap:
            return {"mode": "missing", "versions": [], "override": True,
                    "reason": f"The question names version {ver}, which is not in the collection."}
        return {"mode": "single", "versions": [vmap[ver]], "override": True,
                "reason": f"The question names version {ver}, so the date slider is ignored."}
    m = DATED.search(question)
    if m:
        qd = date(int(m.group(3)), R.MONTHS[m.group(2).lower()], int(m.group(1)))
        v = in_force(qd, versions)
        if v is None:
            return {"mode": "missing", "versions": [], "override": True,
                    "reason": f"The question names {qd:%d %B %Y}, before the first version was published."}
        return {"mode": "single", "versions": [v], "override": True,
                "reason": f"The question names {qd:%d %B %Y}, so the date slider is ignored (version {v['version']} was in force)."}
    v = in_force(d, versions)
    if v is None:
        return {"mode": "missing", "versions": [], "override": False,
                "reason": f"No version had been published by {d:%d %B %Y}."}
    if CHANGE.search(question):
        known = [x for x in versions if x["published"] <= d]
        return {"mode": "history", "versions": known, "override": False,
                "reason": f"History question: searching every version published up to {d:%d %B %Y}."}
    return {"mode": "single", "versions": [v], "override": False,
            "reason": f"Version {v['version']} was in force on {d:%d %B %Y}."}


def retrieve(question, p, chunks, bm25):
    """Passages for a plan, with the same rules as the evaluated version-aware config."""
    if p["mode"] == "missing":
        return []
    scores = bm25.scores(R.search_query(question))
    order = sorted(range(len(chunks)), key=lambda i: -scores[i])
    is_notice = lambda c: c["chunk_id"].endswith("-notice")
    out = []
    k = R.K if p["mode"] == "single" else R.PER_VERSION
    for v in p["versions"]:
        ver = v["version"]
        out += [c for c in chunks if c["version"] == ver and is_notice(c)]
        out += [chunks[i] for i in order if chunks[i]["version"] == ver and not is_notice(chunks[i])][:k]
    return out


def notes(d, p, versions):
    """Version notes for the prompt: the cards of the versions searched, plus what the selected date means."""
    lines = [v["card"] for v in p["versions"]] or [versions[-1]["card"]]
    if p["mode"] == "single" and not p["override"]:
        lines.insert(0, f"The user selected the date {d:%d %B %Y}. Version {p['versions'][0]['version']} was in force on that date; "
                        "answer for that version.")
    elif p["mode"] == "history":
        lines.insert(0, f"The user selected the date {d:%d %B %Y}. Answer as the history stood on that date: "
                        "versions published later do not exist yet for this question.")
    return lines


def system_prompt(today):
    return re.sub(r"^Today is [^.]+\.", f"Today is {today:%d %B %Y}.", R.ANSWER_SYSTEM)


def user_prompt(question, passages, note_lines):
    return R.build_prompt(question, passages, note_lines)
