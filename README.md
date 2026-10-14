# Version-aware RAG for a changing climate standard

**Question answering over the six versions of the VCMI Claims Code of Practice (2023–2026) that answers from the version in force on the date you ask about, cites the page, and says so when the documents do not contain the answer.**

▶ **Live demo:** [ADD LINK AFTER DEPLOYING] · type a question, move the date slider, watch the answer change when the rules did.

---

## Why this is a hard problem

Climate standards are rewritten often, and most of the text survives each rewrite. The VCMI Claims Code of Practice has six versions in three years, and the important changes are small:

| What changed | Before | After |
|---|---|---|
| Deadline after which only CCP-labelled credits count | 1 January 2026 (v2.0–v3.0) | 1 January 2027 (v3.1, Aug 2025) |
| Silver claim threshold | ≥ 20% and < 60% (v1.0) | ≥ 10% and < 50% (v2.0) |
| Is VCMI issuing claims at all? | Yes (v2.0–v3.1) | **No** (v3.2, Sep 2026) |

A model asked from memory gives the old answer with confidence. A standard RAG system searches all versions together and mixes them: in my tests, **77% of the passages it retrieved came from the wrong version**. Both are failures a consultancy cannot afford: advice based on a superseded rule.

Two behaviours matter, and both are measured here:
1. **Right version:** answer from the version that applies (current, a named version, or the one in force on a date), or say how a rule changed between versions.
2. **Knowing what is not there:** decline questions the documents do not answer instead of inventing a plausible rule.

## Results

Same model (`openai/gpt-oss-120b`), same 76 questions, three set-ups. Graded by a second model with a fixed rubric (see [Evaluation](#how-the-answers-were-graded)).

| | No documents | Plain RAG | **Version-aware RAG** |
|---|---|---|---|
| **Answerable questions correct** | 8/66 (12%) | 28/66 (42%) | **48/66 (73%)** |
| · about the current version | 5/21 | 9/21 | **18/21** |
| · about a named version | 2/17 | 10/17 | **14/17** |
| · "as of" a date | 1/9 | 4/9 | **5/9** |
| · "when did this rule change, and how?" | 0/19 | 5/19 | **11/19** |
| **Unanswerable questions declined** | 4/8 | 8/8 | 7/8 \* |
| Answers built on the wrong version | 4 | 8 | **5** |
| Retrieval: gold passage found (no LLM) | — | 25/67 (37%) | **51/67 (76%)** |
| Retrieval: passages from the wrong version | — | 77% | **0%** |

\* One of the seven was an empty reply that the judge accepted as a refusal; counted strictly, 6/8.

What the numbers say:
- Documents alone more than triple accuracy (12% → 42%), but plain RAG still mixes versions and often gives up: the right passage is buried under near-identical passages from other versions.
- Routing each question to the right version is the biggest single gain (42% → 73%) and removes wrong-version retrieval entirely.
- The weak spot is **rules that were removed** (e.g. an SBTi commitment-letter requirement dropped in v3.0): the system finds the old rule but struggles to say "this no longer exists". This is the clearest next step.

The test set is small (76 questions), so differences of a few questions are within noise; 95% confidence intervals are in each run's report.

## How it works

```
6 PDFs ──► manifest (dates, SHA-256) ──► change log (what changed, where) ──► 76 test questions with gold quotes
                                                                                     │
question ──► route: which version(s)? ──► BM25 search inside those versions ──► LLM answers with citations ──► judge
             (named version / date / current /        + version notes                  or declines
              "how did it change" = all versions)    + pinned status notices
```

1. **Data you can verify** ([`data/`](data/README.md)). One row per version in `manifest.csv`: source URL, SHA-256 hash, publication date. The dates were checked against the PDFs' own Document History tables; the VCMI website listed three of them wrong.
2. **A verified change log** ([`data/diff/`](data/README.md#the-change-log)). Every pair of consecutive versions compared sentence by sentence: 1,117 changes grouped into 759 events, classified as substantive, status or editorial. Checked three ways: a known change must be found (the 2026 → 2027 deadline), every quote is searched in the raw PDF text (1,510 of 1,516 found; the 6 that are interrupted by page footers are excluded from later use), and the result is cross-checked against VCMI's own Document History.
3. **A test set grounded in the documents** ([`eval/`](eval/README.md)). 19 facts tracked across all six versions (`eval/timelines.md`), each cell backed by an exact quote and page. From them, 76 questions: current, named version, as-of-date, change, unanswerable, partly answerable, and "trap" questions where a stale sentence survives in the newest version. Split into dev (54) and test (22) by hash, so the split cannot be tuned.
4. **Version-aware retrieval** ([`rag/`](rag/README.md)). Pages chunked into ~150-word passages tagged with version, page and status. A router decides which version(s) a question is about; BM25 keyword search runs only inside those; the model gets a short "version card" (when the version was published, whether it is current) and any status notice of that version, pinned. It must cite passage IDs, and it may only cite passages it was given.
5. **Live demo** (`app.py`). The same pipeline with one change: the date comes from a slider instead of the question text.

## How the answers were graded

An LLM judge (`qwen/qwen3.8-27b`, a different model family from the one answering) compares each answer with the gold answer and quotes, and returns one label: correct, wrong version, incorrect, declined, correct refusal, or hallucinated; it also flags correct answers that add invented details. Temperature 0, structured output, every call cached.

To check the judge, all 76 closed-book answers were graded a second time independently. After one rubric fix (the first rubric read "stale" as "older only" and had no rule for invented extras), the judge agreed on **96% of answers (Cohen's κ = 0.94)**. The remaining disagreements and the old grades are kept in `eval/` for transparency.

## Repository map

| Path | What it is |
|---|---|
| `app.py` | Live demo (Streamlit): question box, date slider, cited answer |
| `data/manifest.csv` | The six versions: dates, URLs, SHA-256 hashes, notes |
| `data/clean/`, `data/sections/` | Cleaned text of each version, and the same text split into named sections |
| `data/diff/` | The change log: `report.md` (start here), `shortlist.md` (30 most important changes), `changes.jsonl`, `events.jsonl` |
| `scripts/diff_versions.py` | Builds everything in `data/clean`, `data/sections`, `data/diff` from the PDFs |
| `.claude/agents/version-differ.md` | The specification given to the AI agent that wrote and ran `diff_versions.py` |
| `eval/timelines.md` | The 19 facts × 6 versions table the questions are built from |
| `eval/questions.jsonl` | The 76 test questions with gold answers and quotes |
| `eval/build_eval.py`, `eval/extract_pages.py` | Build the test set and verify every quote against the raw PDF page |
| `eval/run_baseline.py` | Ask a model, grade with a judge, write reports (all providers, caching) |
| `eval/runs/` | Every answer, grade and report behind the results table |
| `rag/rag.py` | Chunking, BM25, routing, retrieval metrics, answering |
| `rag/asof.py` | Date-slider routing used by the demo |
| `rag/runs/retrieval_eval__all.md` | Retrieval metrics for the three configurations |

## Run it

Python 3.11+. Free API keys: [Groq](https://console.groq.com) (used for every result above).

```powershell
pip install -r requirements.txt
$env:GROQ_API_KEY = "..."

# the demo
streamlit run app.py

# reproduce the results (the PDFs are not in the repo: download them from the URLs in data/manifest.csv into data/raw/)
python -I scripts/diff_versions.py                 # change log, checks the SHA-256 of each PDF first
python -I eval/extract_pages.py data/raw eval/pages
python -I eval/build_eval.py eval/pages eval       # timelines + 76 questions, every quote verified
python -I rag/rag.py index                         # passages
python -I rag/rag.py retrieval-eval                # retrieval metrics, no API needed
python -I eval/run_baseline.py answer --provider groq --model openai/gpt-oss-120b           # closed-book
python -I rag/rag.py answer --config version_aware                                           # RAG
python -I eval/run_baseline.py judge  --run <run folder> --judge-provider groq --judge-model qwen/qwen3.8-27b
python -I eval/run_baseline.py report --run <run folder> --judge-model qwen/qwen3.8-27b
```

Free tiers allow roughly 1,000 requests a day per model; the scripts pace their calls and cache every response, so an interrupted run resumes where it stopped.

## Limitations

- **Small test set.** 76 questions, one run per configuration. Good for showing large effects (12% → 42% → 73%), not for ranking close variants.
- **One answering model**, one judge model. The judge was checked against a second grading, not yet against a blind human review.
- **Questions were written by the same project that built the system.** The hash-based dev/test split guards against tuning on the test set (retrieval: dev 75%, test 79%), but an outside question set would be a stronger test.
- **Keyword search only.** BM25 was enough for a single document family; embeddings were not tried.
- **Dates.** A version is treated as in force from its publication date until the next one; the documents state no separate effective dates.
- **Removed rules** are the main remaining failure (see Results).

## How AI was used

I used Claude (Anthropic) throughout, as a collaborator and as a tool inside the pipeline:
- **Design.** I discussed the problem framing, the evaluation design and each step's method with Claude before building it, and pushed back where it did not fit (for example, keeping the MVP to one document family).
- **Code.** Most code was written by Claude to my specifications and reviewed and run by me on my machine. `scripts/diff_versions.py` was written and run by a Claude Code sub-agent following the specification in `.claude/agents/version-differ.md`; I reviewed its output and sent it back with fixes (unstable IDs, a circular quote check, a misreported change).
- **Grading.** Claude produced the independent second grading used to validate the LLM judge (`eval/analysis/claude_grades.jsonl`).
- **What I did myself:** chose the problem and the documents, found and checked the six versions and their dates, ran every experiment, read the failures, and decided what to fix.

[EDIT THIS SECTION SO IT MATCHES EXACTLY WHAT YOU DID.]

## Source documents

The VCMI Claims Code of Practice is published by the Voluntary Carbon Markets Integrity Initiative at [vcmintegrity.org](https://vcmintegrity.org). This is an independent project, not affiliated with or endorsed by VCMI. The PDFs are not redistributed here; `data/manifest.csv` lists where to download each one and its SHA-256 hash, so you can check you have the same files.
