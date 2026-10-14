# data/

Everything about the source documents: which versions exist, their text, and what changed between them.

## manifest.csv

One row per version of the VCMI Claims Code of Practice.

| Column | Meaning |
|---|---|
| `doc_id`, `version` | `vcmi-ccp-v3.1`, `3.1` |
| `publication_date` | Taken from the Document History table inside the newer PDFs, not from the website (the website gave three wrong dates) |
| `effective_from` | Same as publication: the documents state no separate effective date. A version is treated as in force until the next one is published |
| `source_page` | Where the PDF was downloaded |
| `local_filename`, `sha256`, `pages` | The file expected in `data/raw/` and its hash, so anyone can check they have the identical file |
| `version_stamp_in_pdf` | What the PDF itself says about its version (v1.0 says nothing; it is identified only by later Document History tables) |

| Version | Published | Note |
|---|---|---|
| 1.0 | 28 Jun 2023 | First version |
| 2.0 | 28 Nov 2023 | Near rewrite; claims open |
| 2.1 | 30 Aug 2024 | Clarifications |
| 3.0 | 30 Apr 2025 | Article 6.4 credits accepted; SBTi-only rules removed |
| 3.1 | 15 Aug 2025 | Credit deadline moved from 1 Jan 2026 to 1 Jan 2027 |
| 3.2 | 23 Sep 2026 | VCMI stops issuing claims; current version |

## raw/ (not in the repository)

The six PDFs. Download them from `source_page` and save them under `local_filename`. `scripts/diff_versions.py` checks every SHA-256 before doing anything and stops if a file differs.

## clean/ and sections/

Produced by `scripts/diff_versions.py`.

- `clean/<doc_id>.json`: the text of each version as blocks with page numbers, after removing page numbers, running footers and repeated banners. The v3.2 banner ("VCMI is not issuing Carbon Integrity Claims") is kept once as a status notice, because it is the most important change in that version.
- `sections/<doc_id>.jsonl`: the same text split into the document's own sections (each Step, each Foundational Criterion, each Box, glossary terms…), each with a version-independent ID such as `fc2/near-term-targets` or `step3/purchase-requirements`, so the same section can be compared across versions.

## The change log

`diff/` compares each pair of consecutive versions.

| File | What it holds |
|---|---|
| `report.md` | **Start here.** Counts per version pair, every substantive and status change in one line, the cross-check against VCMI's Document History, what cleaning removed, and the verification results |
| `shortlist.md` | The 30 most important changes, ranked (numbers and dates first, then eligibility, then rule wording), each with exact old and new quotes |
| `changes.jsonl` | One record per changed sentence (1,117): section, old text, new text, pages, type, `uncertain` flag |
| `events.jsonl` | The same records grouped into real-world changes (759): a moved deadline touches 8 sentences but is one event |

How it was built: sentences are aligned inside matching sections with `difflib` (and `rapidfuzz` to pair reworded sentences), then classified as **substantive** (a rule, number, date, threshold or scope changed), **status** (whether the scheme operates) or **editorial** (wording only). When unsure, a change is marked substantive and `uncertain: true`, so nothing important is lost; this is why the substantive count is an upper bound.

How it was checked:
1. **Known answer.** The 1 January 2026 → 2027 deadline change (v3.0 → v3.1) must be found. It is: 7 records, 1 event.
2. **Quotes against the raw PDF.** Every quoted sentence was searched in the unprocessed page text: 1,510 found verbatim, 6 not (a page footer interrupts the sentence in the PDF). Those 6 are never used as quotes elsewhere.
3. **Against VCMI's own Document History.** Every change VCMI lists for v2.0–v3.2 is matched to records here. Many more sentence-level changes exist than VCMI lists, because its history summarises each version in a few lines.
4. **Reproducible.** IDs are hashes of the content (`c-` + 10 hex characters), so rerunning the script gives identical files.

The script was written by an AI agent (Claude Code) following the written specification in `.claude/agents/version-differ.md`; its output was reviewed and corrected over several rounds before use.
