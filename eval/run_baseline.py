"""Closed-book baseline for the VCMI Claims Code versioning eval.

Asks a model every question WITHOUT any documents, then scores each answer:
  - answerable questions: correct / wrong_version (another version's value, older or newer) / incorrect / refused;
    'unsupported_details' flags answers whose core is right but that add invented specifics
  - refusal questions:    correct_refusal (says it isn't covered or corrects the premise) / hallucinated
  - partial questions:    full (answers the covered part, flags the rest) / partial_only / hallucinated / refused

Steps (run from the project root). Defaults: Gemini answers (free), a Groq-hosted model judges (free):
  python -I eval/run_baseline.py answer
  python -I eval/run_baseline.py judge
  python -I eval/run_baseline.py report
  python -I eval/run_baseline.py review      # CSV of 20 verdicts to check by hand
  python -I eval/run_baseline.py agreement   # after filling in review.csv

Providers and the key each one reads:
  gemini      GEMINI_API_KEY       (free key: Google AI Studio)
  groq        GROQ_API_KEY         (free key: console.groq.com)
  openrouter  OPENROUTER_API_KEY   (free ":free" models)
  anthropic   ANTHROPIC_API_KEY    (paid)
Choose with --provider/--model (the model answering) and --judge-provider/--judge-model.
Every API call is cached in eval/runs/cache.sqlite, so reruns cost nothing.
--mock replaces the API with a fake model (for testing the pipeline without a key).
"""
import argparse, csv, hashlib, json, os, random, re, sqlite3, sys, time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
TODAY = "10 October 2026"

ANSWER_SYSTEM = (
    f"Today is {TODAY}. You are answering questions about the VCMI Claims Code of Practice, "
    "published by the Voluntary Carbon Markets Integrity Initiative. You have no documents: answer from "
    "your own knowledge. If a question asks about the current version, answer for the version you believe "
    "is current today. If you do not know, or the Code does not address the question, say so instead of guessing."
)
ANSWER_TOOL = {
    "name": "submit_answer",
    "description": "Submit your answer to the question.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "description": "Your answer, in one to three sentences."},
            "version_relied_on": {"type": "string", "description": "The Claims Code version (and date) your answer is based on, or 'unknown'."},
            "declined": {"type": "boolean", "description": "True if you are saying you don't know or the Code doesn't cover it."},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        },
        "required": ["answer", "version_relied_on", "declined", "confidence"],
    },
}

JUDGE_SYSTEM = (
    "You grade answers about the VCMI Claims Code of Practice against a verified answer key. "
    "Grade only on meaning, not wording. Be strict about numbers, dates, thresholds and who/what is eligible."
)
JUDGE_TOOL = {
    "name": "submit_grade",
    "description": "Submit the grade for the answer.",
    "input_schema": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "enum": ["correct", "wrong_version", "incorrect", "refused",
                                                  "correct_refusal", "hallucinated",
                                                  "full", "partial_only"]},
            "matched_version": {"type": "string", "description": "If the answer matches the value of a specific version, which one (e.g. '3.0'); else 'none'."},
            "unsupported_details": {"type": "boolean", "description": "True if the answer adds specific details (conditions, numbers, names, reasons) that the answer key does not support."},
            "reason": {"type": "string", "description": "One sentence."},
        },
        "required": ["label", "matched_version", "unsupported_details", "reason"],
    },
}

# ------------------------------------------------------------------ data
def load_questions():
    return [json.loads(l) for l in open(HERE / "questions.jsonl", encoding="utf-8")]

def load_timelines():
    return {t["timeline_id"]: t for t in json.load(open(HERE / "timelines.json", encoding="utf-8"))}

VNUM = {"v1": "1.0", "v2": "2.0", "v2.1": "2.1", "v3.0": "3.0", "v3.1": "3.1", "v3.2": "3.2"}

def version_table(t):
    rows = []
    for v, e in t["values"].items():
        rows.append(f"  version {VNUM[v]}: {e['value'] if e.get('value') else 'not addressed'}")
    return "\n".join(rows)

# ------------------------------------------------------------------ providers
PROVIDERS = {
    # name: (OpenAI-compatible base URL or None for the Anthropic SDK, key env var, seconds between calls)
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY", 6.0),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", 7.0),  # free tier: 8K tokens/min
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", 3.5),
    "anthropic": (None, "ANTHROPIC_API_KEY", 0.0),
}

def make_client(provider):
    base_url, env, _ = PROVIDERS[provider]
    key = os.environ.get(env)
    if not key:
        sys.exit(f"Set {env} first (provider '{provider}').")
    if base_url is None:
        import anthropic
        return anthropic.Anthropic(api_key=key)
    import openai
    return openai.OpenAI(base_url=base_url, api_key=key, max_retries=0)

def json_instruction(tool):
    props = tool["input_schema"]["properties"]
    fields = "\n".join(f'  "{k}": {v.get("type")}' + (f' (one of {v["enum"]})' if "enum" in v else "") +
                       f' - {v.get("description", "")}' for k, v in props.items())
    return ("\n\nRespond with ONLY a JSON object, no other text, with exactly these keys:\n" + fields)

def parse_json(text, tool):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in reply")
    obj = json.loads(m.group(0))
    schema = tool["input_schema"]
    missing = [k for k in schema["required"] if k not in obj]
    if missing:
        raise ValueError(f"missing keys {missing}")
    for k, v in schema["properties"].items():
        if "enum" in v and obj[k] not in v["enum"]:
            raise ValueError(f"{k}={obj[k]!r} not in {v['enum']}")
    if isinstance(obj.get("declined"), str):
        obj["declined"] = obj["declined"].strip().lower() == "true"
    return obj

# ------------------------------------------------------------------ API with cache
class Cache:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS c (k TEXT PRIMARY KEY, v TEXT)")
    def get(self, k):
        r = self.db.execute("SELECT v FROM c WHERE k=?", (k,)).fetchone()
        return json.loads(r[0]) if r else None
    def put(self, k, v):
        self.db.execute("INSERT OR REPLACE INTO c VALUES (?,?)", (k, json.dumps(v)))
        self.db.commit()

def call(client, cache, provider, model, system, user, tool, mock=None):
    key = hashlib.sha256(json.dumps([provider, model, system, user, tool["name"]]).encode()).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        return hit
    if mock:
        out = mock(user)
        cache.put(key, out)
        return out
    pause = PROVIDERS[provider][2]
    last_err = None
    for attempt in range(6):
        try:
            if PROVIDERS[provider][0] is None:  # Anthropic: forced tool call gives structured output
                msg = client.messages.create(
                    model=model, max_tokens=600, temperature=0, system=system,
                    tools=[tool], tool_choice={"type": "tool", "name": tool["name"]},
                    messages=[{"role": "user", "content": user}])
                out = dict(next(b for b in msg.content if b.type == "tool_use").input)
                out["_usage"] = {"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}
            else:  # OpenAI-compatible: ask for JSON and validate it
                extra = {}
                if provider == "groq" and model.startswith("qwen/"):
                    # Qwen reasons before answering by default; that burns the 8K tokens/min free limit.
                    extra = {"reasoning_effort": "none"}
                resp = client.chat.completions.create(
                    model=model, temperature=0, max_tokens=800 if extra else 2000, extra_body=extra or None,
                    messages=[{"role": "system", "content": system + json_instruction(tool)},
                              {"role": "user", "content": user}])
                out = parse_json(resp.choices[0].message.content, tool)
                u = getattr(resp, "usage", None)
                if u:
                    out["_usage"] = {"input_tokens": u.prompt_tokens, "output_tokens": u.completion_tokens}
            cache.put(key, out)
            time.sleep(pause)
            return out
        except Exception as e:  # rate limits, server errors, malformed JSON: wait and retry
            last_err = e
            text = str(e)
            if re.search(r"PerDay|per day|requests per day|tokens per day|RPD|TPD", text, re.I):
                raise SystemExit(f"Daily free quota used up for {provider}/{model}. Finished calls are cached; "
                                 f"switch model or provider, or rerun tomorrow.\n{text[:300]}")
            wait = min(60, 5 * 2 ** attempt)
            print(f"  retry {attempt + 1} in {wait}s: {type(e).__name__}: {str(e)[:120]}")
            time.sleep(wait)
    raise SystemExit(f"Giving up after repeated errors: {last_err}. Rerun later: finished calls are cached.")

# ------------------------------------------------------------------ mock model (pipeline test only)
def mock_answer(user):
    r = random.Random(user)
    return {"answer": r.choice(["1 January 2026.", "I don't know.", ">= 10% and < 50%.", "Yes."]),
            "version_relied_on": r.choice(["3.0", "unknown"]), "declined": r.random() < 0.2,
            "confidence": r.choice(["low", "medium", "high"])}

def mock_judge(user):
    r = random.Random(user)
    if "REFUSAL QUESTION" in user:
        return {"label": r.choice(["correct_refusal", "hallucinated"]), "matched_version": "none", "unsupported_details": False, "reason": "mock"}
    if "PARTIAL QUESTION" in user:
        return {"label": r.choice(["full", "partial_only", "hallucinated", "refused"]), "matched_version": "none", "unsupported_details": False, "reason": "mock"}
    return {"label": r.choice(["correct", "wrong_version", "incorrect", "refused"]), "matched_version": r.choice(["3.0", "none"]),
            "unsupported_details": r.random() < 0.3, "reason": "mock"}

# ------------------------------------------------------------------ steps
def safe(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name)

def run_dir(args):
    if getattr(args, "run", None):   # any run folder, e.g. a RAG run written by rag/rag.py
        return RUNS / args.run
    return RUNS / f"closed_book__{safe(args.provider)}__{safe(args.model)}"

def step_answer(args, client):
    cache = Cache(RUNS / "cache.sqlite")
    out = run_dir(args); out.mkdir(parents=True, exist_ok=True)
    rows = []
    for q in load_questions():
        a = call(client, cache, args.provider, args.model, ANSWER_SYSTEM, q["question"], ANSWER_TOOL,
                 mock_answer if args.mock else None)
        rows.append({"id": q["id"], **a})
        print(f"{q['id']}: {a['answer'][:80]}", flush=True)
    with open(out / "answers.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} answers to {out / 'answers.jsonl'}")

def judge_prompt(q, a, timelines):
    head = f"QUESTION: {q['question']}\n\nMODEL ANSWER: {a['answer']}\nMODEL SAYS IT RELIED ON: {a['version_relied_on']}\nMODEL DECLINED: {a['declined']}\n\n"
    if q["type"].startswith("refusal"):
        return head + (
            "REFUSAL QUESTION. The answer key says:\n" + q["gold_value"] + "\n\n"
            "Label 'correct_refusal' if the answer says the Code does not cover this, or correctly rejects or "
            "corrects the question's premise as the key describes. Label 'hallucinated' if it gives a specific "
            "answer the key says does not exist.")
    if q["type"] == "partial":
        return head + (
            "PARTIAL QUESTION. The answer key says:\n" + q["gold_value"] + "\n\n"
            "Label 'full' if the answer gets the answerable part right AND says the other part is not covered. "
            "'partial_only' if it gets the answerable part right but invents or guesses the other part, or vice versa. "
            "'hallucinated' if it gets the answerable part wrong. 'refused' if it declines both parts.")
    t = timelines[q["timeline_id"]]
    return head + (
        f"The question targets version {q['target_version']}.\nCORRECT ANSWER: {q['gold_value']}\n\n"
        f"Value of this fact in every version (verified):\n{version_table(t)}\n\n"
        "Grade the CORE of the answer: the value it gives (for a yes/no question, its yes or no).\n"
        "- 'correct': the core matches the correct answer, even if the answer adds other details.\n"
        "- 'wrong_version': the core matches the value of a DIFFERENT version in the table, whether that version is "
        "older OR newer than the one asked about. Set matched_version to that version.\n"
        "- 'refused': the answer declines or says it does not know.\n"
        "- 'incorrect': anything else, including claiming the Code says nothing about a fact the correct answer gives.\n"
        "Separately, set unsupported_details to true if the answer adds specific conditions, numbers, names or reasons "
        "that the correct answer does not contain; otherwise false. This does not change the label.")

def step_judge(args, client):
    cache = Cache(RUNS / "cache.sqlite")
    d = run_dir(args)
    answers = {json.loads(l)["id"]: json.loads(l) for l in open(d / "answers.jsonl", encoding="utf-8")}
    timelines = load_timelines()
    rows = []
    for q in load_questions():
        a = answers[q["id"]]
        g = call(client, cache, args.judge_provider, args.judge_model, JUDGE_SYSTEM, judge_prompt(q, a, timelines), JUDGE_TOOL,
                 mock_judge if args.mock else None)
        rows.append({"id": q["id"], "label": g["label"], "matched_version": g["matched_version"],
                     "unsupported_details": bool(g.get("unsupported_details")), "reason": g["reason"]})
        print(f"{q['id']}: {g['label']:<16} {g['reason'][:70]}", flush=True)
    with open(d / f"grades__{safe(args.judge_model)}.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} grades")

def bootstrap(values, n=2000, seed=0):
    if not values:
        return (float("nan"),) * 3
    r = random.Random(seed); k = len(values)
    means = sorted(sum(r.choice(values) for _ in range(k)) / k for _ in range(n))
    return sum(values) / k, means[int(0.025 * n)], means[int(0.975 * n) - 1]

def step_report(args, _client):
    d = run_dir(args)
    Q = {q["id"]: q for q in load_questions()}
    G = [json.loads(l) for l in open(d / f"grades__{safe(args.judge_model)}.jsonl", encoding="utf-8")]
    A = {json.loads(l)["id"]: json.loads(l) for l in open(d / "answers.jsonl", encoding="utf-8")}
    groups = defaultdict(list)
    for g in G:
        q = Q[g["id"]]
        if args.split != "all" and q["split"] != args.split:
            continue
        family = ("refusal" if q["type"].startswith("refusal") else
                  "partial" if q["type"] == "partial" else
                  "current" if q["type"].startswith("current") else q["type"].replace("_subtle", ""))
        groups[family].append((q, g))
        if q["closed_book_risk"]:
            groups["~ changed recently (closed_book_risk)"].append((q, g))
        groups["~ ALL"].append((q, g))
    good = {"correct", "correct_refusal", "full"}
    title = args.run if getattr(args, "run", None) else f"Closed-book baseline: {args.model} ({args.provider})"
    lines = [f"# {title}", "",
             f"Judge: {args.judge_model} ({args.judge_provider}). Split: {args.split}. Today's date given to the model: {TODAY}.", "",
             "| Group | n | Correct (95% CI) | of which with invented extras | Wrong version | Wrong / hallucinated | Declined |",
             "|---|---|---|---|---|---|---|"]
    for name in sorted(groups):
        items = groups[name]
        ok = [1 if g["label"] in good else 0 for _, g in items]
        m, lo, hi = bootstrap(ok)
        stale = sum(g["label"] == "wrong_version" for _, g in items)
        extras = sum(g["label"] == "correct" and g.get("unsupported_details") for _, g in items)
        wrong = sum(g["label"] in ("incorrect", "hallucinated", "partial_only") for _, g in items)
        ref = sum(g["label"] == "refused" for _, g in items)
        lines.append(f"| {name} | {len(items)} | {m:.0%} ({lo:.0%}–{hi:.0%}) | {extras} | {stale} | {wrong} | {ref} |")
    stale_rows = [(q, g) for q, g in groups["~ ALL"] if g["label"] == "wrong_version"]
    lines += ["", "## Wrong-version answers (gave an older or newer version's value)", ""]
    lines += [f"- {q['id']} ({q['type']}, target {q['target_version']}): answered with version {g['matched_version']}'s value. {q['question']}"
              for q, g in stale_rows] or ["- none"]
    halluc = [(q, g) for q, g in groups["~ ALL"] if g["label"] == "hallucinated"]
    lines += ["", "## Hallucinated answers to unanswerable questions", ""]
    lines += [f"- {q['id']}: {q['question']} → \"{A[q['id']]['answer'][:120]}\"" for q, g in halluc] or ["- none"]
    usage = [a.get("_usage") for a in A.values() if a.get("_usage")]
    if usage:
        lines += ["", f"Tokens (answers): {sum(u['input_tokens'] for u in usage)} in, {sum(u['output_tokens'] for u in usage)} out."]
    (d / f"report__{safe(args.judge_model)}__{args.split}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

def step_review(args, _client):
    """Write 20 random verdicts for hand-checking; fill in your_label, then run 'agreement'."""
    d = run_dir(args)
    Q = {q["id"]: q for q in load_questions()}
    G = [json.loads(l) for l in open(d / f"grades__{safe(args.judge_model)}.jsonl", encoding="utf-8")]
    A = {json.loads(l)["id"]: json.loads(l) for l in open(d / "answers.jsonl", encoding="utf-8")}
    sample = random.Random(42).sample(G, min(20, len(G)))
    path = d / "review.csv"
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "question", "gold_value", "model_answer", "judge_label", "judge_reason", "your_label"])
        for g in sample:
            q = Q[g["id"]]
            w.writerow([q["id"], q["question"], q["gold_value"], A[q["id"]]["answer"], g["label"], g["reason"], ""])
    print(f"wrote {path}. Fill in your_label (same label names), save, then run: agreement")

def step_agreement(args, _client):
    d = run_dir(args)
    rows = list(csv.DictReader(open(d / "review.csv", encoding="utf-8-sig")))
    rows = [r for r in rows if r["your_label"].strip()]
    if not rows:
        sys.exit("No your_label values filled in review.csv yet.")
    agree = sum(r["your_label"].strip() == r["judge_label"] for r in rows)
    labels = sorted({r["judge_label"] for r in rows} | {r["your_label"].strip() for r in rows})
    n = len(rows); po = agree / n
    pe = sum((sum(r["judge_label"] == l for r in rows) / n) * (sum(r["your_label"].strip() == l for r in rows) / n) for l in labels)
    kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0
    print(f"agreement {agree}/{n} = {po:.0%}, Cohen's kappa = {kappa:.2f}")
    for r in rows:
        if r["your_label"].strip() != r["judge_label"]:
            print(f"  {r['id']}: judge={r['judge_label']} you={r['your_label']}")

def step_compare(args, _client):
    """Agreement between this run's judge and another grades file (--other), e.g. a second judge or your labels."""
    d = run_dir(args)
    mine = {json.loads(l)["id"]: json.loads(l) for l in open(d / f"grades__{safe(args.judge_model)}.jsonl", encoding="utf-8")}
    other = {json.loads(l)["id"]: json.loads(l) for l in open(args.other, encoding="utf-8")}
    norm = lambda l: "wrong_version" if l == "stale" else l
    ids = sorted(set(mine) & set(other)); n = len(ids)
    a = {i: norm(mine[i]["label"]) for i in ids}; b = {i: norm(other[i]["label"]) for i in ids}
    po = sum(a[i] == b[i] for i in ids) / n
    labels = set(a.values()) | set(b.values())
    pe = sum((sum(a[i] == l for i in ids) / n) * (sum(b[i] == l for i in ids) / n) for l in labels)
    print(f"{n} shared questions: agreement {po:.0%}, Cohen's kappa {(po - pe) / (1 - pe):.2f}")
    for i in ids:
        if a[i] != b[i]:
            print(f"  {i}: judge={a[i]:<15} other={b[i]:<15} {mine[i]['reason'][:60]}")

# ------------------------------------------------------------------ main
def main():
    p = argparse.ArgumentParser()
    p.add_argument("step", choices=["answer", "judge", "report", "review", "agreement", "compare"])
    p.add_argument("--other", help="compare: path to another grades .jsonl")
    p.add_argument("--run", help="judge/report/review/compare a named run folder in eval/runs (e.g. a RAG run)")
    p.add_argument("--provider", default="gemini", choices=list(PROVIDERS), help="provider of the model being tested")
    p.add_argument("--model", default="gemini-3.8-flash", help="model being tested")
    p.add_argument("--judge-provider", default="groq", choices=list(PROVIDERS), help="provider of the judge")
    p.add_argument("--judge-model", default="openai/gpt-oss-120b", help="model that grades the answers")
    p.add_argument("--split", default="all", choices=["all", "dev", "test"], help="report only")
    p.add_argument("--mock", action="store_true", help="fake model, for testing without an API key")
    args = p.parse_args()
    client = None
    if args.step in ("answer", "judge") and not args.mock:
        client = make_client(args.provider if args.step == "answer" else args.judge_provider)
    {"answer": step_answer, "judge": step_judge, "report": step_report,
     "review": step_review, "agreement": step_agreement, "compare": step_compare}[args.step](args, client)

if __name__ == "__main__":
    main()