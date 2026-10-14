# rag/

The retrieval-augmented answering system, in three configurations that differ in one thing each, so the effect of each change can be measured.

| Config | Searches | Purpose |
|---|---|---|
| `naive` | All versions together | What a standard RAG demo does |
| `latest_only` | Only the newest version | The obvious quick fix (fails on any question about the past) |
| `version_aware` | The version(s) the question is about | This project |

## Indexing (`python -I rag/rag.py index`)

- Text comes straight from the PDF pages. Lines repeated on at least a quarter of a version's pages (footers, page numbers) are dropped, except long repeated notices: the v3.2 banner saying VCMI no longer issues claims is kept once as a special *notice* passage.
- Each page is cut into passages of about 150 words, overlapping by one sentence, never across pages, so every passage has one page to cite. IDs look like `v3.1-p32-c0` (version, page, chunk).
- 680 passages in `index/chunks.jsonl`; `index/versions.json` holds each version's dates and a short "version card".

## Answering a question (`version_aware`)

1. **Route.** Decide which version(s) to search, with simple, inspectable rules:
   - names a version ("under version 2.1") → that version, or "not in the collection" if it does not exist;
   - asks how something changed ("which version…", "when did…") → every version, 2 passages each, oldest first;
   - names a date → the version published most recently before it;
   - otherwise → the current version.
2. **Search.** BM25 keyword search (written from scratch, k1 = 1.5, b = 0.75) inside the chosen version(s). Words that describe *when* ("in force on", "which version", dates) are removed from the search query because routing has already used them.
3. **Context.** The model gets the version card(s) (published when, superseded by what, current or not), the version's status notice pinned at the top, and the top 5 passages, each labelled with version, date, status and page.
4. **Answer.** The model must use only the passages, answer for the routed version, cite passage IDs, decline when the passages do not answer, and prefer a status notice over older body text when they conflict. Citations to passages it was not given are counted and reported (there were none).

## Retrieval results (no LLM involved)

From `runs/retrieval_eval__all.md`. "Hit" = a retrieved passage of the right version contains the gold quote.

| Config | Hit | Passages from the wrong version | Routing correct |
|---|---|---|---|
| naive | 25/67 (37%) | 77% | – |
| latest_only | 18/67 (27%) | 53% | – |
| version_aware | 51/67 (76%) | 0% | 49/49 |

## The demo's date routing (`asof.py`)

The live app replaces the text-based date rule with a slider. A plain question is answered from the version in force on the selected date; a "how did it change" question searches every version published up to that date; a version or date written in the question overrides the slider (the app says so). Retrieval, prompt and answer format are imported unchanged from `rag.py`.

## Commands

```powershell
python -I rag/rag.py index
python -I rag/rag.py retrieval-eval
python -I rag/rag.py show q010 --config version_aware        # what one question retrieves
python -I rag/rag.py answer --config version_aware --provider groq --model openai/gpt-oss-120b
```

Answers are written to `eval/runs/rag__<config>__…` and graded with `eval/run_baseline.py judge --run …`.
