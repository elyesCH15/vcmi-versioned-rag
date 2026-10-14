# Retrieval evaluation (no LLM). Split: all. k=5 per single-version query.

Hit = a retrieved passage of the gold version contains the gold quote (strict), or is the gold page (page).
Change questions need both sides of the change; other questions need any one gold span. Removed-rule questions are excluded (their evidence is in an older version by design).
Wrong-version share = retrieved passages from a version other than the one the question targets.

| Config | Questions with gold | Hit, strict | Hit, page | Wrong-version share | Routing correct |
|---|---|---|---|---|---|
| naive | 67 | 25/67 (37%) | 28/67 (42%) | 189/245 (77%) | 0/49 |
| latest_only | 67 | 18/67 (27%) | 19/67 (28%) | 130/245 (53%) | 23/49 |
| version_aware | 67 | 51/67 (76%) | 56/67 (84%) | 0/268 (0%) | 49/49 |

## Strict hit by question type

| Type | n | naive | latest_only | version_aware |
|---|---|---|---|---|
| as_of_date | 9 | 4 | 0 | 7 |
| change_version | 19 | 5 | 0 | 9 |
| current | 19 | 7 | 16 | 18 |
| explicit_version | 17 | 8 | 0 | 14 |
| partial | 2 | 1 | 2 | 2 |
| refusal_false_premise | 1 | 0 | 0 | 1 |

version_aware misses (11): q003, q006, q008, q009, q015, q016, q017, q023, q037, q050, q056
