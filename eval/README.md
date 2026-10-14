# eval/

The test set and the grading. The ground truth comes only from the documents: every gold answer is backed by an exact quote that was found on the cited page of the PDF.

## Files

| File | What it is |
|---|---|
| `timelines.md` | **Start here.** 19 facts × 6 versions: the value of each fact in each version, with its page. `—` means the version does not address it (confirmed by text search). Also lists the "traps": stale sentences that survive in newer versions |
| `timelines.json` | The same, with the exact quotes |
| `questions.jsonl` | The 76 questions: question, type, target version, gold answer, gold quotes (version + page + text), split |
| `extract_pages.py` | Saves the raw text of every PDF page to `pages/` (used to verify quotes independently of any cleaning) |
| `build_eval.py` | Builds timelines and questions from the facts defined in it, and fails if any quote is not on its cited page |
| `run_baseline.py` | Asks a model the questions (closed-book), grades answers with a judge model, writes reports; also used to grade the RAG runs |
| `analysis/claude_grades.jsonl` | An independent second grading of all 76 closed-book answers, used to check the judge |
| `runs/` | One folder per experiment (see below) |

## The questions

| Type | n | Example | What it tests |
|---|---|---|---|
| current | 21 | "According to the current Code, what is the threshold for the Silver claim?" | Uses the newest version; includes 2 rules that were removed and 2 trap questions |
| explicit_version | 17 | "Under version 2.1, …" | Uses the named version, not the newest |
| as_of_date | 9 | "Under the Code in force on 15 September 2023, …" | Works out which version applied on a date |
| change_version | 19 | "In which version did the rule on X last change, and how?" | Compares versions |
| refusal | 8 | "What minimum permanence period must credits have?" (the Code does not say) | Declines instead of inventing; includes a false-premise question |
| partial | 2 | Half answerable, half not | Answers the covered part and flags the rest |

Split: 54 dev / 22 test, assigned by a hash of the question ID, so it cannot be adjusted after seeing results. 12 questions are flagged `closed_book_risk`: facts that changed recently enough that a model's training data is likely out of date.

## How answers are graded

A judge model (`qwen/qwen3.8-27b` on Groq) receives the question, the gold answer and quotes, and the answer, and returns one label:

- answerable questions: `correct`, `wrong_version` (another version's value), `incorrect`, `refused`, plus an `unsupported_details` flag for correct answers that add invented specifics;
- unanswerable: `correct_refusal` or `hallucinated`;
- partial: `full`, `partial_only`, `hallucinated` or `refused`.

Temperature 0, JSON output, a different model family from the one answering (models tend to favour their own outputs), and every call cached in `runs/cache.sqlite` (not in the repo) so a rerun gives identical grades.

**Checking the judge.** The closed-book answers were also graded independently (`analysis/claude_grades.jsonl`). The first rubric agreed on 88% (κ = 0.83); the disagreements showed two rubric faults (it read "wrong version" as "older version" only, and had no rule for invented extras). After fixing them: 96% agreement, κ = 0.94. The grades from the first rubric are kept as `grades__qwen_OLD_instructions.jsonl` in the closed-book run.

## runs/

Folder name = `<setup>__<provider>__<model>`; each holds `answers.jsonl`, `grades__<judge>.jsonl` and `report__<judge>__all.md` (accuracy by question type with 95% bootstrap intervals, plus every wrong-version and hallucinated answer).

| Folder | Set-up | Answerable correct |
|---|---|---|
| `closed_book__groq__openai-gpt-oss-120b` | No documents | 8/66 |
| `rag__naive__groq__openai-gpt-oss-120b` | Search all versions together | 28/66 |
| `rag__version_aware__groq__openai-gpt-oss-120b` | Version routing, first run | 47/66 |
| `rag__version_aware__groq__openai-gpt-oss-120b__fix1` | After fixing one bug (the v3.2 status notice was not passed for change questions) | 48/66 |

## Commands

```powershell
python -I eval/extract_pages.py data/raw eval/pages
python -I eval/build_eval.py eval/pages eval
python -I eval/run_baseline.py answer --provider groq --model openai/gpt-oss-120b
python -I eval/run_baseline.py judge  --run closed_book__groq__openai-gpt-oss-120b --judge-provider groq --judge-model qwen/qwen3.8-27b
python -I eval/run_baseline.py report --run closed_book__groq__openai-gpt-oss-120b --judge-model qwen/qwen3.8-27b
python -I eval/run_baseline.py compare --run closed_book__groq__openai-gpt-oss-120b --judge-model qwen/qwen3.8-27b --other eval/analysis/claude_grades.jsonl   # agreement with the second grading
```

`--mock` runs the whole pipeline with a fake model, without an API key.
