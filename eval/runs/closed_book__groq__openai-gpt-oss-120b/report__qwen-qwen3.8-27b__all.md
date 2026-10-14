# Closed-book baseline: openai/gpt-oss-120b (groq)

Judge: qwen/qwen3.8-27b (groq). Split: all. Today's date given to the model: 10 October 2026.

| Group | n | Correct (95% CI) | of which with invented extras | Wrong version | Wrong / hallucinated | Declined |
|---|---|---|---|---|---|---|
| as_of_date | 9 | 11% (0%–33%) | 0 | 1 | 5 | 2 |
| change_version | 19 | 0% (0%–0%) | 0 | 0 | 0 | 19 |
| current | 21 | 24% (5%–43%) | 5 | 3 | 7 | 6 |
| explicit_version | 17 | 12% (0%–29%) | 1 | 0 | 7 | 8 |
| partial | 2 | 0% (0%–0%) | 0 | 0 | 0 | 2 |
| refusal | 8 | 50% (12%–88%) | 0 | 0 | 4 | 0 |
| ~ ALL | 76 | 16% (8%–25%) | 6 | 4 | 23 | 37 |
| ~ changed recently (closed_book_risk) | 12 | 8% (0%–25%) | 1 | 3 | 2 | 6 |

## Wrong-version answers (gave an older or newer version's value)

- q020 (current, target 3.2): answered with version 3.1's value. According to the current VCMI Claims Code of Practice, can companies obtain a VCMI claim?
- q043 (as_of_date, target 1.0): answered with version 3.0's value. Under the VCMI Claims Code of Practice in force on 15 September 2023, is a public commitment to reach net zero by 2050 required?
- q053 (current, target 3.2): answered with version 3.0's value. According to the current VCMI Claims Code of Practice, must claimants ('shall') or should they demonstrate compliance in Step 4?
- q065 (current_trap, target 3.2): answered with version 2.0's value. Can a company make a VCMI Carbon Integrity Claim today?

## Hallucinated answers to unanswerable questions

- q069: What minimum permanence period, in years, must carbon credits have to be used for a VCMI Claim? → "The VCMI Claims Code requires that carbon credits used for a claim have a minimum permanence of 100 years."
- q070: What minimum share of a company's retired credits must be carbon removals under the Claims Code? → "The Claims Code requires that at least 50 % of the credits a company retires to support a carbon‑removal claim must be f"
- q071: How does the Claims Code align with ISO 14068-1 carbon neutrality claims? → "The VCMI Claims Code of Practice is designed to be consistent with ISO 14068‑1, requiring that carbon‑neutrality claims "
- q072: How does the current Claims Code reflect the SBTi Corporate Net-Zero Standard V2.0? → "The current VCMI Claims Code requires that any net‑zero claim be backed by a corporate net‑zero target that is validated"

Tokens (answers): 24627 in, 27670 out.
