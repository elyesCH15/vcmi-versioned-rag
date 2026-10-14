# rag__naive__groq__openai-gpt-oss-120b

Judge: qwen/qwen3.8-27b (groq). Split: all. Today's date given to the model: 10 October 2026.

| Group | n | Correct (95% CI) | of which with invented extras | Wrong version | Wrong / hallucinated | Declined |
|---|---|---|---|---|---|---|
| as_of_date | 9 | 44% (11%–78%) | 2 | 1 | 0 | 4 |
| change_version | 19 | 26% (11%–47%) | 3 | 7 | 0 | 7 |
| current | 21 | 43% (24%–67%) | 4 | 0 | 1 | 11 |
| explicit_version | 17 | 59% (35%–82%) | 2 | 0 | 2 | 5 |
| partial | 2 | 50% (0%–100%) | 0 | 0 | 0 | 1 |
| refusal | 8 | 100% (100%–100%) | 0 | 0 | 0 | 0 |
| ~ ALL | 76 | 49% (37%–59%) | 11 | 8 | 3 | 28 |
| ~ changed recently (closed_book_risk) | 12 | 33% (8%–58%) | 1 | 1 | 1 | 6 |

## Wrong-version answers (gave an older or newer version's value)

- q009 (change_version, target 2.0): answered with version 1.0's value. In which version of the VCMI Claims Code of Practice did the rule on the names of the claim tiers last change, and how?
- q017 (change_version, target 3.1): answered with version 1.0's value. In which version of the VCMI Claims Code of Practice did the rule on which carbon credits may be used last change, and how?
- q022 (as_of_date, target 1.0): answered with version 2.0's value. Under the VCMI Claims Code of Practice in force on 15 September 2023, can companies obtain a VCMI claim?
- q027 (change_version, target 3.0): answered with version 2.1's value. In which version of the VCMI Claims Code of Practice did the rule on the target boundary and emissions coverage criteria last change, and how?
- q034 (change_version, target 3.0): answered with version 2.1's value. In which version of the VCMI Claims Code of Practice did the rule on the deadline for SBTi validation of targets last change, and how?
- q037 (change_version, target 2.0): answered with version 3.0's value. In which version of the VCMI Claims Code of Practice did the rule on Foundational Criterion 2 last change, and how?
- q048 (change_version, target 3.0): answered with version 2.1's value. In which version of the VCMI Claims Code of Practice did the rule on the SBTi commitment letter last change, and how?
- q056 (change_version, target 3.2): answered with version 3.0's value. In which version of the VCMI Claims Code of Practice did the rule on the Step 4 obligation wording last change, and how?

## Hallucinated answers to unanswerable questions

- none

Tokens (answers): 117418 in, 25237 out.
