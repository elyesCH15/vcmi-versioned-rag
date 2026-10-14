"""Version-aware RAG over the VCMI Claims Code of Practice (v1.0 to v3.2).

Steps (run from the project root):
  python -I rag/rag.py index                     # PDFs -> rag/index/chunks.jsonl (no API)
  python -I rag/rag.py retrieval-eval            # retrieval metrics for all configs (no API)
  python -I rag/rag.py show q010 --config version_aware   # see what one question retrieves
  python -I rag/rag.py answer --config version_aware --provider groq --model openai/gpt-oss-120b
then grade with the same judge as the baseline:
  python -I eval/run_baseline.py judge  --run rag__version_aware__groq__openai-gpt-oss-120b --judge-provider groq --judge-model qwen/qwen3.8-27b
  python -I eval/run_baseline.py report --run rag__version_aware__groq__openai-gpt-oss-120b --judge-model qwen/qwen3.8-27b

Configs (one change at a time, so differences can be attributed):
  naive          search every version together (what a plain RAG demo does)
  latest_only    search only the newest version
  version_aware  route each question to the right version: named version, as-of date, current,
                 or all versions for "when did it change" questions; adds a version card
"""
import argparse, csv, json, math, re, sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "rag" / "index"
TODAY = date(2026, 10, 10)
CONFIGS = ["naive", "latest_only", "version_aware"]
K = 5                      # chunks per single-version query
PER_VERSION = 2            # chunks per version for "how did it change" questions
CHUNK_WORDS = 150          # target chunk size
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], 1)}

# ------------------------------------------------------------------ manifest
def load_versions():
    """Versions in publication order, each with its date, file and validity window."""
    rows = list(csv.DictReader(open(ROOT / "data" / "manifest.csv", encoding="utf-8-sig")))
    vs = sorted(({"version": r["version"], "doc_id": r["doc_id"], "file": r["local_filename"],
                  "published": date.fromisoformat(r["publication_date"])} for r in rows),
                key=lambda v: v["published"])
    for i, v in enumerate(vs):
        v["superseded_by"] = vs[i + 1]["version"] if i + 1 < len(vs) else None
        v["superseded_on"] = vs[i + 1]["published"] if i + 1 < len(vs) else None
        v["status"] = "current" if v["superseded_by"] is None else "superseded"
    return vs

def version_card(v, versions):
    """A short metadata passage given to the model with the passages of that version."""
    if v["status"] == "current":
        s = (f"Version {v['version']} of the VCMI Claims Code of Practice, published {v['published']:%d %B %Y}, "
             f"is the latest version in this collection and is current as of {TODAY:%d %B %Y}.")
    else:
        s = (f"Version {v['version']} of the VCMI Claims Code of Practice was published {v['published']:%d %B %Y} "
             f"and was superseded by version {v['superseded_by']} on {v['superseded_on']:%d %B %Y}.")
    return s + " Versions in this collection: " + ", ".join(
        f"{x['version']} ({x['published']:%d %b %Y})" for x in versions) + "."

# ------------------------------------------------------------------ chunking
def clean_pages(pdf_path):
    """Raw page text with repeated boilerplate (footers, banners, page numbers) removed."""
    import pymupdf
    doc = pymupdf.open(pdf_path)
    pages = [[l.strip() for l in p.get_text().split("\n")] for p in doc]
    key = lambda l: re.sub(r"\d+", "#", l)
    freq = Counter(k for lines in pages for k in {key(l) for l in lines if l})
    boiler = {k for k, n in freq.items() if n >= max(3, 0.25 * len(pages)) and len(k) > 1}
    out, removed = [], Counter()
    # Long repeated lines are notices (e.g. v3.2's "VCMI is not issuing claims" banner): drop them from every
    # page, but keep ONE copy as its own passage on the first page where they appear.
    notice_lines, notice_page = [], None
    for pno, lines in enumerate(pages, 1):
        for l in lines:
            if key(l) in boiler and len(l) > 55 and l not in notice_lines:
                notice_lines.append(l)
                notice_page = notice_page or pno
    for lines in pages:
        keep = []
        for l in lines:
            if not l or re.fullmatch(r"[#\d\s]+", key(l)) and len(l) <= 3:
                continue
            if key(l) in boiler:
                removed[l] += 1
                continue
            keep.append(l)
        text = ""
        for l in keep:   # join lines; keep real hyphens at line ends ("science-" + "aligned")
            text = text + l if text.endswith("-") else (text + " " + l if text else l)
        out.append(re.sub(r"\s+", " ", text).strip())
    notice = re.sub(r"\s+", " ", " ".join(notice_lines)).strip() if notice_lines else None
    return out, removed, (notice_page, notice)

def split_sentences(text):
    parts = re.split(r"(?<=[.!?;:])\s+(?=[A-Z0-9•“\"(])|\s+(?=•)", text)
    return [p.strip() for p in parts if p.strip()]

def chunk_page(text, target=CHUNK_WORDS):
    """Pack sentences into ~target-word chunks within one page, with one sentence of overlap."""
    sents, chunks, cur = split_sentences(text), [], []
    for s in sents:
        cur.append(s)
        if sum(len(x.split()) for x in cur) >= target:
            chunks.append(" ".join(cur))
            cur = cur[-1:]
    if cur and (not chunks or " ".join(cur) not in chunks[-1]):
        chunks.append(" ".join(cur))
    return chunks

def step_index(args):
    versions = load_versions()
    INDEX.mkdir(parents=True, exist_ok=True)
    rows, log = [], []
    for v in versions:
        pages, removed, (npage, notice) = clean_pages(ROOT / "data" / "raw" / v["file"])
        n0 = len(rows)
        if notice:
            rows.append({"chunk_id": f"v{v['version']}-p{npage}-notice", "version": v["version"], "doc_id": v["doc_id"],
                         "page": npage, "published": v["published"].isoformat(), "status": v["status"],
                         "text": "Notice repeated on every page of this version: " + notice})
        for pno, text in enumerate(pages, 1):
            if len(text.split()) < 8:
                continue
            for i, c in enumerate(chunk_page(text)):
                rows.append({"chunk_id": f"v{v['version']}-p{pno}-c{i}", "version": v["version"],
                             "doc_id": v["doc_id"], "page": pno, "published": v["published"].isoformat(),
                             "status": v["status"], "text": c})
        log.append(f"v{v['version']}: {len(pages)} pages -> {len(rows) - n0} chunks; removed boilerplate: "
                   + "; ".join(f"'{l[:50]}' x{n}" for l, n in removed.most_common(4)))
    with open(INDEX / "chunks.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump([{**v, "published": v["published"].isoformat(),
                "superseded_on": v["superseded_on"].isoformat() if v["superseded_on"] else None,
                "card": version_card(v, versions)} for v in versions],
              open(INDEX / "versions.json", "w", encoding="utf-8"), indent=1)
    print("\n".join(log))
    print(f"wrote {len(rows)} chunks to {INDEX / 'chunks.jsonl'}")

# ------------------------------------------------------------------ BM25
STOP = set("""a an the of to in on for and or is are was were be by with as at from that this which what who whom
whose how when where does do did can may must should shall it its their there these those under according
vcmi claims code practice version current""".split())

def tokens(text):
    return [t for t in re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower()) if t not in STOP]

class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = [tokens(d) for d in docs]
        self.k1, self.b = k1, b
        self.avg = sum(map(len, self.docs)) / max(1, len(self.docs))
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = [Counter(d) for d in self.docs]
    def scores(self, query):
        q = tokens(query)
        out = []
        for tf, d in zip(self.tf, self.docs):
            s = 0.0
            for t in q:
                if t in tf:
                    s += self.idf[t] * tf[t] * (self.k1 + 1) / (tf[t] + self.k1 * (1 - self.b + self.b * len(d) / self.avg))
            out.append(s)
        return out

# ------------------------------------------------------------------ routing
def route(question, versions):
    """Decide which version(s) a question is about. Returns (mode, version, reason)."""
    known = {v["version"] for v in versions}
    m = re.search(r"\b(?:version|v)\s?(\d+(?:\.\d+)?)\b", question, re.I)
    if m:
        ver = m.group(1) if "." in m.group(1) else m.group(1) + ".0"
        return ("single", ver, "named version") if ver in known else ("missing", ver, "named version not in collection")
    if re.search(r"\bwhich version\b|\bwhen did\b|\blast change|\bfirst (?:introduced|appear)", question, re.I):
        return ("all", None, "asks how the rule changed across versions")
    m = re.search(r"\b(\d{1,2}) (" + "|".join(MONTHS) + r") (\d{4})\b", question, re.I)
    if m:
        d = date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
        cands = [v for v in versions if v["published"] <= d]
        if not cands:
            return ("missing", None, f"no version in force on {d}")
        return ("single", cands[-1]["version"], f"version in force on {d.isoformat()}")
    return ("single", versions[-1]["version"], "default: current version")

TEMPLATE_WORDS = re.compile(r"\b(?:in which version|which version|did the rule on|the rule on|last change[ds]?|"
                            r"and how|in force on|according to|under version [\d.]+|today|\d{1,2} \w+ \d{4})\b", re.I)

def search_query(question):
    """Remove question-template words (they describe WHEN, which routing handles) before keyword search."""
    return TEMPLATE_WORDS.sub(" ", question)

def retrieve(question, config, chunks, bm25, versions):
    """Returns (passages, cards, routing) for one question."""
    scores = bm25.scores(search_query(question) if config == "version_aware" else question)
    order = sorted(range(len(chunks)), key=lambda i: -scores[i])
    vmap = {v["version"]: v for v in versions}
    latest = versions[-1]["version"]
    pick = lambda pred, k: [chunks[i] for i in order if pred(chunks[i])][:k]
    if config == "naive":
        return pick(lambda c: True, K), [], ("none", None, "no routing")
    if config == "latest_only":
        return pick(lambda c: c["version"] == latest, K), [vmap[latest]["card"]], ("single", latest, "latest only")
    mode, ver, why = route(question, versions)
    notices = lambda vv: [c for c in chunks if c["version"] == vv and c["chunk_id"].endswith("-notice")]
    if mode == "single":
        found = pick(lambda c: c["version"] == ver and not c["chunk_id"].endswith("-notice"), K)
        return notices(ver) + found, [vmap[ver]["card"]], (mode, ver, why)
    if mode == "all":
        out = []
        for v in versions:   # status notices + best passages from every version, oldest first
            out += notices(v["version"])
            out += pick(lambda c, vv=v["version"]: c["version"] == vv and not c["chunk_id"].endswith("-notice"), PER_VERSION)
        return out, [v["card"] for v in versions], (mode, None, why)
    return pick(lambda c: c["version"] == latest, 3), [v["card"] for v in versions], (mode, ver, why)

def load_index():
    chunks = [json.loads(l) for l in open(INDEX / "chunks.jsonl", encoding="utf-8")]
    versions = json.load(open(INDEX / "versions.json", encoding="utf-8"))
    for v in versions:
        v["published"] = date.fromisoformat(v["published"])
    return chunks, versions, BM25([c["text"] for c in chunks])

def load_questions():
    return [json.loads(l) for l in open(ROOT / "eval" / "questions.jsonl", encoding="utf-8")]

# ------------------------------------------------------------------ retrieval metrics (no API)
def norm(s):
    s = s.replace("’", "'").replace("“", '"').replace("”", '"').replace("ﬁ", "fi").replace("ﬂ", "fl")
    s = re.sub(r"[-‐‑–—]\s*", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()

def span_version(span):
    v = span["version"].lstrip("v")
    return v if "." in v else v + ".0"

def span_hit(span, chunk):
    """'quote': the gold quote is in the chunk and the chunk is from the gold version (any page, since the same
    sentence often appears on several pages); 'page': gold version and gold page, quote not fully inside."""
    if chunk["version"] != span_version(span):
        return None
    if norm(span["quote"]) in norm(chunk["text"]):
        return "quote"
    return "page" if chunk["page"] == span["page"] else None

def step_retrieval_eval(args):
    chunks, versions, bm25 = load_index()
    Q = [q for q in load_questions() if args.split == "all" or q["split"] == args.split]
    lines = [f"# Retrieval evaluation (no LLM). Split: {args.split}. k={K} per single-version query.", "",
             "Hit = a retrieved passage of the gold version contains the gold quote (strict), or is the gold page (page).",
             "Change questions need both sides of the change; other questions need any one gold span. "
             "Removed-rule questions are excluded (their evidence is in an older version by design).",
             "Wrong-version share = retrieved passages from a version other than the one the question targets.", "",
             "| Config | Questions with gold | Hit, strict | Hit, page | Wrong-version share | Routing correct |",
             "|---|---|---|---|---|---|"]
    per_q = {}
    for cfg in CONFIGS:
        hits_s = hits_p = n = 0
        wrong = total = 0
        route_ok = route_n = 0
        for q in Q:
            passages, _, routing = retrieve(q["question"], cfg, chunks, bm25, versions)
            if q.get("target_version") and q["type"] != "change_version":
                tgt = q["target_version"]
                total += len(passages)
                wrong += sum(p["version"] != tgt for p in passages)
                route_n += 1
                route_ok += routing[1] == tgt
            spans = q["gold_spans"]
            if not spans or q["answerable"] is False or q["type"] == "current_removed":
                continue
            n += 1
            res = [span_hit(s, p) for s in spans for p in passages]
            # change questions need evidence from BOTH sides of the change; elsewhere, several gold spans are
            # alternative evidence for the same fact, so any one is enough
            agg = all if q["type"] == "change_version" else any
            cover_s = agg(any(span_hit(s, p) == "quote" for p in passages) for s in spans)
            cover_p = agg(any(span_hit(s, p) in ("quote", "page") for p in passages) for s in spans)
            hits_s += cover_s; hits_p += cover_p
            per_q.setdefault(q["id"], {})[cfg] = "quote" if cover_s else "page" if cover_p else "miss"
        lines.append(f"| {cfg} | {n} | {hits_s}/{n} ({hits_s / n:.0%}) | {hits_p}/{n} ({hits_p / n:.0%}) | "
                     f"{wrong}/{total} ({wrong / max(1, total):.0%}) | {route_ok}/{route_n} |")
    # breakdown by question type for the version-aware config vs naive
    lines += ["", "## Strict hit by question type", "", "| Type | n | " + " | ".join(CONFIGS) + " |",
              "|---|---|" + "---|" * len(CONFIGS)]
    types = defaultdict(list)
    Qd = {q["id"]: q for q in Q}
    for qid, res in per_q.items():
        t = Qd[qid]["type"]
        t = "current" if t.startswith("current") else t.replace("_subtle", "")
        types[t].append(res)
    for t, rs in sorted(types.items()):
        lines.append(f"| {t} | {len(rs)} | " + " | ".join(f"{sum(r[c] == 'quote' for r in rs)}" for c in CONFIGS) + " |")
    misses = [qid for qid, r in per_q.items() if r["version_aware"] == "miss"]
    lines += ["", f"version_aware misses ({len(misses)}): " + ", ".join(misses)]
    out = ROOT / "rag" / "runs"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"retrieval_eval__{args.split}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

def step_show(args):
    chunks, versions, bm25 = load_index()
    q = next(q for q in load_questions() if q["id"] == args.qid)
    passages, cards, routing = retrieve(q["question"], args.config, chunks, bm25, versions)
    print(f"{q['id']} [{q['type']}] {q['question']}\nrouting: {routing}\ngold: {q['gold_value']}")
    for s in q["gold_spans"]:
        print(f"  gold span: {s['version']} p{s['page']}: {s['quote'][:90]}")
    for c in cards:
        print(f"card: {c[:110]}")
    for p in passages:
        hit = [span_hit(s, p) for s in q["gold_spans"]]
        print(f"- {p['chunk_id']} ({p['status']}) {'HIT' if 'quote' in hit else ''}: {p['text'][:160]}")

# ------------------------------------------------------------------ answering
ANSWER_SYSTEM = (
    f"Today is {TODAY:%d %B %Y}. You answer questions about the VCMI Claims Code of Practice using ONLY the passages "
    "provided. Each passage is labelled with its version, publication date, status and page.\n"
    "Rules:\n"
    "1. Use only the passages. Do not add conditions, numbers or names that the passages do not state.\n"
    "2. Answer for the version the question asks about (a named version, the version in force on a given date, or "
    "the current version). The version notes say which versions exist and when each applied.\n"
    "3. Cite the chunk_id of every passage you rely on.\n"
    "4. If the passages do not answer the question, say so and set declined to true. If the question asks about a "
    "version that is not in the collection, say so. If only part of the question is answered, answer that part and "
    "say which part the passages do not cover.\n"
    "5. If passages of the same version contradict each other, prefer statements about the document's status "
    "(cover notes, notices) over older body text, and mention the contradiction."
)
ANSWER_TOOL = {
    "name": "submit_answer",
    "description": "Submit your answer.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "description": "One to three sentences."},
            "citations": {"type": "array", "items": {"type": "string"}, "description": "chunk_ids relied on; empty if declined."},
            "version_relied_on": {"type": "string", "description": "Version number the answer is based on, or 'none'."},
            "declined": {"type": "boolean", "description": "True if the passages do not answer the question."},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        },
        "required": ["answer", "citations", "version_relied_on", "declined", "confidence"],
    },
}

def build_prompt(question, passages, cards):
    parts = []
    if cards:
        parts.append("VERSION NOTES:\n" + "\n".join(f"- {c}" for c in cards))
    parts.append("PASSAGES:\n" + "\n\n".join(
        f"[{p['chunk_id']} | version {p['version']} | published {p['published']} | {p['status']} | page {p['page']}]\n{p['text']}"
        for p in passages))
    parts.append(f"QUESTION: {question}")
    return "\n\n".join(parts)

def load_runner():
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_baseline", ROOT / "eval" / "run_baseline.py")
    rb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rb)
    return rb

def step_answer(args):
    rb = load_runner()
    chunks, versions, bm25 = load_index()
    # RAG prompts are ~2K tokens; Groq's free tier allows 8K tokens/min, so pace calls further apart.
    base, env, pause = rb.PROVIDERS[args.provider]
    rb.PROVIDERS[args.provider] = (base, env, max(pause, args.pause))
    client = None if args.mock else rb.make_client(args.provider)
    cache = rb.Cache(rb.RUNS / "cache.sqlite")
    run = f"rag__{args.config}__{rb.safe(args.provider)}__{rb.safe(args.model)}" + (f"__{rb.safe(args.tag)}" if args.tag else "")
    out = rb.RUNS / run
    out.mkdir(parents=True, exist_ok=True)
    mock = (lambda user: {"answer": "Mock answer.", "citations": re.findall(r"\[(v[\d.]+-p\d+-c\d+)", user)[:1],
                          "version_relied_on": "3.2", "declined": False, "confidence": "low"}) if args.mock else None
    rows = []
    Q = [q for q in load_questions() if args.split == "all" or q["split"] == args.split]
    for q in Q:
        passages, cards, routing = retrieve(q["question"], args.config, chunks, bm25, versions)
        a = rb.call(client, cache, args.provider, args.model, ANSWER_SYSTEM, build_prompt(q["question"], passages, cards),
                    ANSWER_TOOL, mock)
        valid = {p["chunk_id"] for p in passages}
        a = {**a, "citations_invalid": [c for c in a.get("citations", []) if c not in valid],
             "retrieved": [p["chunk_id"] for p in passages], "routing": list(routing)}
        rows.append({"id": q["id"], **a})
        print(f"{q['id']}: {a['answer'][:80]}  {a.get('citations', [])[:3]}", flush=True)
    with open(out / "answers.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # citation check against the gold quotes (no judge needed)
    Qd = {q["id"]: q for q in Q}
    cmap = {c["chunk_id"]: c for c in chunks}
    ok = n = 0
    for r in rows:
        q = Qd[r["id"]]
        if q["gold_spans"] and q["answerable"] is True and r.get("citations"):
            n += 1
            ok += any(span_hit(s, cmap[c]) == "quote" for s in q["gold_spans"] for c in r["citations"] if c in cmap)
    invalid = sum(len(r["citations_invalid"]) for r in rows)
    print(f"wrote {len(rows)} answers to {out / 'answers.jsonl'}")
    print(f"answers citing a passage that contains the gold quote: {ok}/{n}; invented chunk ids: {invalid}")
    print(f"next: python -I eval/run_baseline.py judge --run {run} --judge-provider groq --judge-model qwen/qwen3.8-27b")

# ------------------------------------------------------------------ main
def main():
    p = argparse.ArgumentParser()
    p.add_argument("step", choices=["index", "retrieval-eval", "show", "answer"])
    p.add_argument("qid", nargs="?")
    p.add_argument("--config", default="version_aware", choices=CONFIGS)
    p.add_argument("--provider", default="groq")
    p.add_argument("--model", default="openai/gpt-oss-120b")
    p.add_argument("--split", default="all", choices=["all", "dev", "test"])
    p.add_argument("--pause", type=float, default=16.0, help="seconds between answer calls (free-tier rate limits)")
    p.add_argument("--mock", action="store_true")
    p.add_argument("--tag", help="suffix for the run folder, so a new run does not overwrite an earlier one")
    args = p.parse_args()
    {"index": step_index, "retrieval-eval": step_retrieval_eval, "show": step_show, "answer": step_answer}[args.step](args)

if __name__ == "__main__":
    main()