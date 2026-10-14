# rag__version_aware__groq__openai-gpt-oss-120b

Judge: qwen/qwen3.8-27b (groq). Split: all. Today's date given to the model: 10 October 2026.

| Group | n | Correct (95% CI) | of which with invented extras | Wrong version | Wrong / hallucinated | Declined |
|---|---|---|---|---|---|---|
| as_of_date | 9 | 56% (22%–89%) | 0 | 1 | 1 | 2 |
| change_version | 19 | 53% (32%–74%) | 3 | 6 | 3 | 0 |
| current | 21 | 86% (71%–100%) | 6 | 0 | 1 | 2 |
| explicit_version | 17 | 82% (65%–100%) | 5 | 0 | 3 | 0 |
| partial | 2 | 100% (100%–100%) | 0 | 0 | 0 | 0 |
| refusal | 8 | 88% (62%–100%) | 0 | 0 | 1 | 0 |
| ~ ALL | 76 | 74% (63%–83%) | 14 | 7 | 9 | 4 |
| ~ changed recently (closed_book_risk) | 12 | 75% (50%–100%) | 2 | 1 | 2 | 0 |

## Wrong-version answers (gave an older or newer version's value)

- q009 (change_version, target 2.0): answered with version 1.0's value. In which version of the VCMI Claims Code of Practice did the rule on the names of the claim tiers last change, and how?
- q017 (change_version, target 3.1): answered with version 3.0's value. In which version of the VCMI Claims Code of Practice did the rule on which carbon credits may be used last change, and how?
- q022 (as_of_date, target 1.0): answered with version 2.0's value. Under the VCMI Claims Code of Practice in force on 15 September 2023, can companies obtain a VCMI claim?
- q023 (change_version, target 3.2): answered with version 3.0's value. In which version of the VCMI Claims Code of Practice did the rule on whether VCMI issues claims last change, and how?
- q034 (change_version, target 3.0): answered with version 2.0's value. In which version of the VCMI Claims Code of Practice did the rule on the deadline for SBTi validation of targets last change, and how?
- q037 (change_version, target 2.0): answered with version 3.0's value. In which version of the VCMI Claims Code of Practice did the rule on Foundational Criterion 2 last change, and how?
- q048 (change_version, target 3.0): answered with version 2.0's value. In which version of the VCMI Claims Code of Practice did the rule on the SBTi commitment letter last change, and how?

## Hallucinated answers to unanswerable questions

- q073: What does version 2.1 of the Claims Code say about using Article 6.4 credits? → "Version 2.1 defines Article 6 as a section of the Paris Agreement that provides principles for voluntary cooperation thr"

Tokens (answers): 172961 in, 30475 out.
