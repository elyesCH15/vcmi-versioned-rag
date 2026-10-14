"""Build fact timelines and gold questions for the VCMI Claims Code versioning eval.

Every quote is checked against the raw text of the page it cites (PyMuPDF page.get_text()).
Matching normalises only: curly quotes and ligatures, hyphens (line-break hyphens are
indistinguishable from real ones in extracted text), whitespace and case.

Usage (from the project root): python -I eval/build_eval.py eval/pages eval
  pages_dir holds v1.json ... v3.2.json (list of raw page texts, one string per page).
"""
import json, re, sys
from datetime import date, timedelta

VERSIONS = ["v1", "v2", "v2.1", "v3.0", "v3.1", "v3.2"]
DOC_ID = {"v1": "vcmi-ccp-v1", "v2": "vcmi-ccp-v2", "v2.1": "vcmi-ccp-v2.1",
          "v3.0": "vcmi-ccp-v3.0", "v3.1": "vcmi-ccp-v3.1", "v3.2": "vcmi-ccp-v3.2"}
VNUM = {"v1": "1.0", "v2": "2.0", "v2.1": "2.1", "v3.0": "3.0", "v3.1": "3.1", "v3.2": "3.2"}
PUB = {"v1": date(2023, 6, 28), "v2": date(2023, 11, 28), "v2.1": date(2024, 8, 30),
       "v3.0": date(2025, 4, 30), "v3.1": date(2025, 8, 15), "v3.2": date(2026, 9, 23)}
CURRENT = "v3.2"
# Date inside each version's validity window, used for as-of-date questions.
AS_OF = {"v1": date(2023, 9, 15), "v2": date(2024, 3, 1), "v2.1": date(2025, 1, 15),
         "v3.0": date(2025, 6, 1), "v3.1": date(2026, 3, 1), "v3.2": date(2026, 10, 1)}

def span(v, page, quote):
    return {"version": v, "doc_id": DOC_ID[v], "page": page, "quote": quote}

def absent(pattern):
    return {"absent": True, "search": pattern}

# ---------------------------------------------------------------- timelines
# Each version maps to {"value": ..., "spans": [...]} or {"value": None, ...absent}.
T = []
TOPIC = {}

def tl(tid, fact, question_stem, values, notes="", traps=None):
    T.append({"timeline_id": tid, "fact": fact, "stem": question_stem,
              "values": values, "notes": notes, "traps": traps or []})

TOPIC["T01"] = "the Silver claim threshold"
tl("T01", "Silver claim threshold (share of remaining emissions covered by retired credits)",
   "what is the threshold for the Silver claim",
   {"v1": {"value": ">= 20% and < 60%", "spans": [span("v1", 18, "VCMI Silver (≥ 20% and < 60%)")]},
    **{v: {"value": ">= 10% and < 50%", "spans": [span(v, p, "Carbon Integrity Silver (≥ 10% and < 50%)")]}
       for v, p in [("v2", 18), ("v2.1", 19), ("v3.0", 19), ("v3.1", 19), ("v3.2", 19)]}})

TOPIC["T02"] = "the Gold claim threshold"
tl("T02", "Gold claim threshold", "what is the threshold for the Gold claim",
   {"v1": {"value": ">= 60% and < 100%", "spans": [span("v1", 18, "VCMI Gold (≥ 60% and < 100%)")]},
    **{v: {"value": ">= 50% and < 100%", "spans": [span(v, p, "Carbon Integrity Gold (≥ 50% and < 100%)")]}
       for v, p in [("v2", 18), ("v2.1", 19), ("v3.0", 19), ("v3.1", 19), ("v3.2", 19)]}})

TOPIC["T03"] = "the names of the claim tiers"
tl("T03", "Name of the claim tiers", "what are the claim tiers called",
   {"v1": {"value": "VCMI Silver / Gold / Platinum", "spans": [span("v1", 18, "VCMI Silver (≥ 20% and < 60%)")]},
    **{v: {"value": "Carbon Integrity Silver / Gold / Platinum",
           "spans": [span(v, p, "Carbon Integrity Silver (≥ 10% and < 50%)")]}
       for v, p in [("v2", 18), ("v2.1", 19), ("v3.0", 19), ("v3.1", 19), ("v3.2", 19)]}})

TOPIC["T04"] = "the deadline for moving to CCP-labelled credits"
tl("T04", "Deadline after which only CCP-labelled (or Article 6.4) credits count",
   "what is the deadline after which only CCP-labelled (or Article 6.4) credits may be used",
   {"v1": {"value": "No date: CORSIA label credits until the ICVCM Assessment Framework is implemented",
           "spans": [span("v1", 30, "These shall be CORSIA label credits, and once the ICVCM Assessment Framework is implemented, companies shall transition to purchase and retire CCP label credits.")]},
    "v2": {"value": "1 January 2026", "spans": [span("v2", 30, "Companies shall transition to purchase and retire CCP-Approved credits by January 1, 2026")]},
    "v2.1": {"value": "1 January 2026", "spans": [span("v2.1", 31, "Companies shall transition to purchase and retire CCP-Approved credits by January 1, 2026")]},
    "v3.0": {"value": "1 January 2026, or earlier if CCP-labelled or Article 6.4 credits become widely available",
             "spans": [span("v3.0", 32, "These options can only be used until 1 January 2026, or until CCP-labelled or Article 6.4 credits become widely available in the market, whichever is the earlier.")]},
    **{v: {"value": "1 January 2027",
           "spans": [span(v, 32, "These options can only be used until 1 January 2027 after which all credits purchased and retired to make a VCMI Claim shall be CCP-labelled credits or Article 6.4 credits")]}
       for v in ["v3.1", "v3.2"]}},
   notes="v3.1 also dropped the 'whichever is the earlier' clause. Strong closed-book test: models trained before Aug 2025 will say 2026.")

TOPIC["T05"] = "which carbon credits may be used"
tl("T05", "Which credits may be used for a claim",
   "which carbon credits may be used to make a claim",
   {"v1": {"value": "CORSIA label credits, moving to CCP label credits once the ICVCM Assessment Framework is implemented",
           "spans": [span("v1", 30, "These shall be CORSIA label credits")]},
    "v2": {"value": "CCP-Approved; interim: CORSIA eligible credits or existing contractually committed credits backed by due diligence against the 10 CCPs",
           "spans": [span("v2", 30, "CORSIA eligible credits or existing contractually committed carbon credits supported by the company's due diligence process alignment to ICVCM's 10 CCPs, will be accepted as an interim measure")]},
    "v2.1": {"value": "CCP-Approved; interim: CORSIA eligible credits or high quality credits backed by due diligence against the 10 CCPs",
             "spans": [span("v2.1", 31, "CORSIA eligible credits or high quality credits supported by the company's due diligence process alignment to ICVCM's 10 CCPs, will be accepted as an interim measure")]},
    "v3.0": {"value": "CCP-labelled credits or Article 6.4 credits (interim options until 1 January 2026)",
             "spans": [span("v3.0", 31, "Companies shall retire ICVCM Core Carbon Principles-labelled credits or Article 6.4 credits issued under Article 6.4 methodologies approved by the Article 6.4 Supervisory Body when they become available.")]},
    **{v: {"value": "CCP-labelled or Article 6.4 credits; never credits from methodologies rejected or excluded in ICVCM assessments",
           "spans": [span(v, 31, "Companies shall retire ICVCM Core Carbon Principles-labelled credits or Article 6.4 credits issued under Article 6.4 methodologies approved by the Article 6.4 Supervisory Body when they become available."),
                     span(v, 32, "companies shall not use credits from methodologies which have already been rejected or excluded by programs as part of the ICVCM assessments")]}
       for v in ["v3.1", "v3.2"]}},
   notes="v2 to v2.1 swaps 'existing contractually committed carbon credits' for 'high quality credits': a subtle change worth one question.")

TOPIC["T06"] = "Article 6.4 credits"
tl("T06", "Article 6.4 credits accepted for claims", "can Article 6.4 credits be used to make a claim",
   {**{v: {"value": None, **absent(r"Article 6\.4 credits")} for v in ["v1", "v2", "v2.1"]},
    **{v: {"value": "Yes, Article 6.4 credits issued under methodologies approved by the Article 6.4 Supervisory Body",
           "spans": [span(v, 31, "Article 6.4 credits issued under Article 6.4 methodologies approved by the Article 6.4 Supervisory Body")]}
       for v in ["v3.0", "v3.1", "v3.2"]}})

TOPIC["T07"] = "whether VCMI issues claims"
tl("T07", "Whether VCMI is issuing claims", "can companies obtain a VCMI claim",
   {"v1": {"value": "Not yet: claims available from November 2023, once the MRA Framework is in place",
           "spans": [span("v1", 9, "From November, companies will be able to obtain VCMI Claims")]},
    **{v: {"value": "Yes, companies are able to make Carbon Integrity Claims",
           "spans": [span(v, p, "Companies are now able to make Carbon Integrity Claims")]}
       for v, p in [("v2", 10), ("v2.1", 11), ("v3.0", 11), ("v3.1", 11)]},
    "v3.2": {"value": "No: as of 23 September 2026 VCMI is no longer issuing Carbon Integrity Claims",
             "spans": [span("v3.2", 1, "As of 23 September 2026, VCMI is no longer issuing Carbon Integrity Claims"),
                       span("v3.2", 6, "Please note at this point in time VCMI is not issuing Carbon Integrity Claims.")]}},
   traps=[{"version": "v3.2", "page": 14, "quote": "Companies are now able to make a Carbon Integrity Claim",
           "why": "Stale sentence left in Box 1 of v3.2; contradicts the cover and banners."}])

TOPIC["T08"] = "the target boundary and emissions coverage criteria"
tl("T08", "Target boundary and emissions coverage criteria", "which criteria must companies follow for the target boundary and emissions coverage",
   {"v1": {"value": "SBTi criteria (95% of scopes 1-2, 67% of scope 3 if scope 3 > 40%)",
           "spans": [span("v1", 21, "Companies must follow SBTi criteria for setting the target boundary and emissions coverage")]},
    **{v: {"value": "The most up to date SBTi or equivalent criteria (95% / 67%)",
           "spans": [span(v, p, "Companies must follow the most up to date SBTi or equivalent criteria for setting the target boundary and emissions coverage")]}
       for v, p in [("v2", 21), ("v2.1", 22)]},
    **{v: {"value": "The criteria of the chosen science-aligned target-setting framework",
           "spans": [span(v, 22, "Companies shall follow the criteria outlined in the chosen science-aligned target setting framework for setting the target boundary and emissions coverage")]}
       for v in ["v3.0", "v3.1", "v3.2"]}})

TOPIC["T09"] = "the organisational level of targets"
tl("T09", "Organisational level at which targets are submitted", "at what organisational level may companies submit their targets",
   {**{v: {"value": None, **absent(r"subsidiar")} for v in ["v1", "v2"]},
    "v2.1": {"value": "Parent or group level only, not subsidiary level (SBTi boundary criteria)",
             "spans": [span("v2.1", 22, "companies should submit targets only at the parent or group-level, not the subsidiary level")]},
    **{v: {"value": "Parent or subsidiary level",
           "spans": [span(v, 22, "Companies can submit targets at the parent or subsidiary level.")]}
       for v in ["v3.0", "v3.1", "v3.2"]}})

TOPIC["T10"] = "the deadline for SBTi validation of targets"
tl("T10", "Deadline to submit unvalidated targets to SBTi", "within what period must companies submit unvalidated targets to SBTi for validation",
   {"v1": {"value": None, **absent(r"submit a target to SBTi for validation"),
           "absent_note": "v1 required validated targets outright (see T11). Do not confuse with v1's separate 24-month rule for long-term targets."},
    **{v: {"value": "Within 24 months",
           "spans": [span(v, p, "they must submit a target to SBTi for validation within 24 months")]}
       for v, p in [("v2", 21), ("v2.1", 22)]},
    **{v: {"value": None, **absent(r"submit a target to SBTi for validation")} for v in ["v3.0", "v3.1", "v3.2"]}},
   notes="Removed in v3.0 along with the SBTi-only requirement.",
   traps=[{"version": "v1", "page": 21, "quote": "within 24 months of obtaining a VCMI Claim",
           "why": "A different 24-month rule (long-term net-zero target), present v1-v2.1."}])

TOPIC["T11"] = "Foundational Criterion 2"
tl("T11", "Foundational Criterion 2: type of near-term targets", "what kind of near-term targets does Foundational Criterion 2 require",
   {"v1": {"value": "Validated science-based near-term targets",
           "spans": [span("v1", 20, "Set and publicly disclose validated science-based near-term emissions reduction targets")]},
    **{v: {"value": "Science-aligned near-term targets (no validation required)",
           "spans": [span(v, p, "set and publicly disclose science-aligned near-term emission reduction targets")]}
       for v, p in [("v2", 6), ("v2.1", 7), ("v3.0", 7), ("v3.1", 7), ("v3.2", 7)]}})

TOPIC["T12"] = "Foundational Criterion 3"
tl("T12", "Foundational Criterion 3", "what does Foundational Criterion 3 require companies to demonstrate",
   {"v1": {"value": "Being on track towards a near-term target and minimising cumulative emissions",
           "spans": [span("v1", 22, "towards meeting a near-term emissions reduction target and minimizing cumulative emissions over the target period")]},
    **{v: {"value": "Making progress on financial allocation, governance and strategy towards the near-term target",
           "spans": [span(v, p, "Demonstrate that the company is making progress on financial allocation, governance, and strategy towards meeting its near-term")]}
       for v, p in [("v2", 22), ("v2.1", 23), ("v3.0", 23), ("v3.1", 23), ("v3.2", 23)]}})

TOPIC["T13"] = "the net-zero-by-2050 commitment"
tl("T13", "Public net-zero-by-2050 commitment", "is a public commitment to reach net zero by 2050 required",
   {"v1": {"value": "Required", "spans": [span("v1", 21, "Make a public commitment to achieve net zero emissions no later than 2050")]},
    **{v: {"value": "Required", "spans": [span(v, p, "Make a public commitment to achieve net-zero emissions no later than 2050")]}
       for v, p in [("v2", 21), ("v2.1", 22)]},
    **{v: {"value": "Encouraged, not required (moved to Recommendations)",
           "spans": [span(v, 23, "Companies are encouraged to make a public commitment to achieve net-zero emissions no later than 2050")]}
       for v in ["v3.0", "v3.1", "v3.2"]}})

TOPIC["T14"] = "the SBTi commitment letter"
tl("T14", "SBTi commitment letter as evidence", "must companies provide an SBTi commitment letter as evidence",
   {"v1": {"value": None, **absent(r"SBTi commitment letter")},
    **{v: {"value": "Required", "spans": [span(v, p, "the company must provide evidence of the SBTi commitment letter")]}
       for v, p in [("v2", 21), ("v2.1", 22)]},
    **{v: {"value": None, **absent(r"SBTi commitment letter")} for v in ["v3.0", "v3.1", "v3.2"]}})

TOPIC["T15"] = "assurance of scope 1 and 2 emissions"
tl("T15", "Third-party assurance of scope 1 and 2 emissions", "is third-party assurance of scope 1 and 2 emissions required",
   {**{v: {"value": None, **absent(r"limited assurance of scope 1 and scope 2")} for v in ["v1", "v2", "v2.1"]},
    **{v: {"value": "Required: limited assurance for base year and most recent reporting year",
           "spans": [span(v, 21, "Obtain third-party, limited assurance of scope 1 and scope 2 emissions for base year and most recent reporting year.")]}
       for v in ["v3.0", "v3.1", "v3.2"]}})

TOPIC["T16"] = "the base year and the most recent reporting year"
tl("T16", "Most recent reporting year vs base year", "can the most recent reporting year be the same as the base year",
   {**{v: {"value": None, **absent(r"cannot be the same as the base year")} for v in ["v1", "v2", "v2.1", "v3.0"]},
    **{v: {"value": "It cannot be the same year",
           "spans": [span(v, 27, "Note that the most recent reporting year cannot be the same as the base year.")]}
       for v in ["v3.1", "v3.2"]}})

TOPIC["T17"] = "the Step 4 obligation wording"
tl("T17", "Step 4 obligation wording", "must claimants ('shall') or should they demonstrate compliance in Step 4",
   {**{v: {"value": None, **absent(r"claimants (shall|should) demonstrate")} for v in ["v1", "v2", "v2.1"]},
    **{v: {"value": "shall (mandatory)", "spans": [span(v, 9, "Claimants shall demonstrate that all Foundational Criteria and Carbon Integrity")]}
       for v in ["v3.0", "v3.1"]},
    "v3.2": {"value": "should (advisory, as claims are no longer issued)",
             "spans": [span("v3.2", 9, "claimants should demonstrate that all Foundational Criteria and Carbon Integrity")]}})

TOPIC["T18"] = "the signatories of the leadership letter"
tl("T18", "Signatories of the letter in the Claims Code", "who signed the letter from VCMI's leadership",
   {**{v: {"value": "Tariye Gbadegesin and Rachel Kyte, Steering Committee Co-Chairs",
           "spans": [span(v, p, "Tariye Gbadegesin and Rachel Kyte VCMI STEERING COMMITTEE CO-CHAIRS")]}
       for v, p in [("v1", 9), ("v2", 10), ("v2.1", 11), ("v3.0", 11), ("v3.1", 11)]},
    "v3.2": {"value": "Usha Rao-Monari, Steering Committee Chair",
             "spans": [span("v3.2", 11, "Usha Rao-Monari VCMI STEERING COMMITTEE CHAIR")]}},
   traps=[{"version": "v3.2", "page": 45, "quote": "The Steering Committee, co-chaired by Rachel Kyte and Tariye Gbadegesin",
           "why": "Acknowledgements in v3.2 still name the former co-chairs."}])

TOPIC["T19"] = "the disclosure for companies not doing policy advocacy"
tl("T19", "Disclosure by companies not doing policy advocacy", "what must companies that do no climate policy advocacy disclose",
   {"v1": {"value": None, **absent(r"publicly disclose that they do not engage")},
    **{v: {"value": "They shall publicly disclose that they do not engage in such activities",
           "spans": [span(v, p, "they shall publicly disclose that they do not engage in any activities")]}
       for v, p in [("v2", 24), ("v2.1", 25), ("v3.0", 26), ("v3.1", 26), ("v3.2", 26)]}})

# ---------------------------------------------------------------- refusals
REFUSALS = [
    ("R01", "nonexistent_version", "What does version 4.0 of the VCMI Claims Code of Practice say about the Gold claim threshold?",
     r"version 4|v\.? ?4\b", "No version 4.0 exists in the corpus; the latest is v3.2 (23 September 2026)."),
    ("R02", "not_covered", "What fee does VCMI charge companies to verify a Carbon Integrity Claim?",
     r"\bfees?\b", "No version mentions a fee."),
    ("R03", "not_covered", "What minimum permanence period, in years, must carbon credits have to be used for a VCMI Claim?",
     r"\d+ ?years? (of )?permanence|permanence of \d+", "No version sets a permanence period in years."),
    ("R04", "not_covered", "What minimum share of a company's retired credits must be carbon removals under the Claims Code?",
     r"removals? (share|percentage)|percentage of removals", "No version sets a removals share."),
    ("R05", "not_covered", "How does the Claims Code align with ISO 14068-1 carbon neutrality claims?",
     r"14068", "ISO 14068 is not mentioned in any version."),
    ("R06", "not_covered_recent", "How does the current Claims Code reflect the SBTi Corporate Net-Zero Standard V2.0?",
     r"Net.Zero Standard (V|version) ?2|CNZS", "Not mentioned in any version, including v3.2. Closed-book trap: the model may know SBTi V2.0 exists."),
    ("R07", "absent_in_version", "What does version 2.1 of the Claims Code say about using Article 6.4 credits?",
     r"Article 6\.4 credits", "Answer: v2.1 does not mention Article 6.4 credits; they were added in v3.0. Correct behaviour is to say so, not to describe v3.0 rules as v2.1's."),
    ("R08", "false_premise", "Under version 1.0, until what date could companies use interim credit options instead of CCP-labelled credits?",
     r"January 1,? 202[67]|1 January 202[67]", "v1 sets no date: CORSIA label credits apply until the ICVCM Assessment Framework is implemented (v1 p30). The 1 January 2026 date first appears in v2."),
]
PARTIAL = [
    ("P01", "What is the Gold claim threshold in the current Claims Code, and what fee does VCMI charge to verify a Gold claim?",
     "T02", "The threshold part is answerable (>= 50% and < 100%, v3.2 p19); the fee part is not covered (no version mentions a fee)."),
    ("P02", "In the current Claims Code, until when can interim credit options be used, and what is the minimum permanence period for those credits?",
     "T04", "Deadline answerable (1 January 2027, v3.2 p32); no permanence period is set in any version."),
]

# ---------------------------------------------------------------- helpers
def norm(s):
    s = (s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
          .replace("ﬁ", "fi").replace("ﬂ", "fl"))
    s = re.sub(r"[-‐‑–—]\s*", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()

def version_on(d):
    cur = None
    for v in VERSIONS:
        if PUB[v] <= d:
            cur = v
    return cur

def main(pages_dir, out_dir):
    pages = {v: json.load(open(f"{pages_dir}/{v}.json", encoding="utf-8")) for v in VERSIONS}
    npages = {v: [norm(t) for t in pages[v]] for v in VERSIONS}
    raw_all = {v: " ".join(pages[v]) for v in VERSIONS}
    problems = []

    def check_span(s, label):
        if norm(s["quote"]) not in npages[s["version"]][s["page"] - 1]:
            problems.append(f"{label}: quote not on {s['version']} p{s['page']}: {s['quote'][:70]}")

    for t in T:
        for v in VERSIONS:
            e = t["values"].get(v)
            if e is None:
                problems.append(f"{t['timeline_id']}: no entry for {v}")
                continue
            if e.get("absent"):
                if re.search(e["search"], raw_all[v], re.I):
                    problems.append(f"{t['timeline_id']}: claimed absent in {v} but /{e['search']}/ matches")
            else:
                for s in e["spans"]:
                    check_span(s, t["timeline_id"])
        for tr in t["traps"]:
            check_span({"version": tr["version"], "page": tr["page"], "quote": tr["quote"]}, t["timeline_id"] + " trap")
    for rid, _, _, pat, _ in REFUSALS:
        if rid in ("R07",):
            if re.search(pat, raw_all["v2.1"], re.I):
                problems.append(f"{rid}: pattern found in v2.1")
            continue
        if rid == "R08":
            if re.search(pat, raw_all["v1"], re.I):
                problems.append(f"{rid}: pattern found in v1")
            continue
        for v in VERSIONS:
            if re.search(pat, raw_all[v], re.I):
                problems.append(f"{rid}: pattern /{pat}/ found in {v}")

    # ------------------------------------------------------------ questions
    Q = []
    def add(qtype, question, t, target_v, as_of=None, extra=None):
        e = t["values"][target_v]
        q = {"id": None, "type": qtype, "timeline_id": t["timeline_id"], "question": question,
             "as_of_date": as_of.isoformat() if as_of else None, "target_version": VNUM[target_v],
             "answerable": True, "gold_value": e["value"] if e["value"] else
             f"Not addressed in version {VNUM[target_v]}",
             "gold_spans": e.get("spans", []),
             "absent_in_target": bool(e.get("absent")),
             "trap_spans": [tr for tr in t["traps"] if tr["version"] == target_v],
             "closed_book_risk": target_v == CURRENT and t["values"][CURRENT]["value"] != t["values"]["v3.0"].get("value")}
        if extra: q.update(extra)
        Q.append(q)

    # Rules removed in an earlier version: the current answer is "no longer required", backed by
    # the last version that stated it. Removal is confirmed by the diff (pure-removal events).
    REMOVED = {"T10": ("v2.1", "No longer required: removed in version 3.0 (it was 24 months in versions 2.0 and 2.1)"),
               "T14": ("v2.1", "No longer required: removed in version 3.0 (required in versions 2.0 and 2.1)")}
    for t in T:
        vals, stem = t["values"], t["stem"]
        tid = t["timeline_id"]
        # 1. current
        if tid in REMOVED:
            last_v, note = REMOVED[tid]
            add("current_removed", f"According to the current VCMI Claims Code of Practice, {stem}?", t, CURRENT,
                extra={"gold_value": note, "gold_spans": vals[last_v]["spans"], "absent_in_target": True})
        else:
            add("current", f"According to the current VCMI Claims Code of Practice, {stem}?", t, CURRENT)
        # Only versions that state a value become explicit/as-of targets: an absence found by
        # phrase search is not strong enough to be a gold answer.
        diff = [v for v in VERSIONS[:-1]
                if vals[v].get("value") and vals[v]["value"] != vals[CURRENT].get("value")]
        if diff:
            v = diff[-1]
            add("explicit_version", f"Under version {VNUM[v]} of the VCMI Claims Code of Practice, {stem}?", t, v)
            v2 = diff[0] if diff[0] != v else None
            if v2:
                d = AS_OF[v2]
                assert version_on(d) == v2
                add("as_of_date", f"Under the VCMI Claims Code of Practice in force on {d.day} {d.strftime('%B %Y')}, {stem}?",
                    t, v2, as_of=d)
        # last change (additions and removals are backed by pure-addition/removal events in the diff)
        changes = [VERSIONS[i] for i in range(1, len(VERSIONS))
                   if vals[VERSIONS[i]].get("value") != vals[VERSIONS[i - 1]].get("value")]
        if changes:
            last = changes[-1]
            prev = VERSIONS[VERSIONS.index(last) - 1]
            Q.append({"id": None, "type": "change_version", "timeline_id": tid,
                      "question": f"In which version of the VCMI Claims Code of Practice did the rule on {TOPIC[tid]} last change, and how?",
                      "as_of_date": None, "target_version": VNUM[last], "answerable": True,
                      "gold_value": f"Version {VNUM[last]} ({PUB[last].isoformat()}): from "
                                    f"'{vals[prev].get('value') or 'not addressed'}' to '{vals[last].get('value') or 'not addressed'}'",
                      "gold_spans": vals[prev].get("spans", []) + vals[last].get("spans", []),
                      "absent_in_target": False, "trap_spans": [], "closed_book_risk": last == CURRENT})

    # extra hand-written questions for subtle changes and traps
    t5 = next(t for t in T if t["timeline_id"] == "T05")
    add("explicit_version_subtle", "Under version 2.0 of the Claims Code, besides CORSIA eligible credits, which other credits were accepted as an interim measure?", t5, "v2",
        extra={"gold_value": "Existing contractually committed carbon credits supported by the company's due diligence process alignment to ICVCM's 10 CCPs"})
    add("explicit_version_subtle", "Under version 2.1 of the Claims Code, besides CORSIA eligible credits, which other credits were accepted as an interim measure?", t5, "v2.1",
        extra={"gold_value": "High quality credits supported by the company's due diligence process alignment to ICVCM's 10 CCPs (v2.0 said existing contractually committed credits)"})
    t7 = next(t for t in T if t["timeline_id"] == "T07")
    add("current_trap", "Can a company make a VCMI Carbon Integrity Claim today?", t7, CURRENT)
    t18 = next(t for t in T if t["timeline_id"] == "T18")
    add("current_trap", "Who chairs the VCMI Steering Committee according to the current Claims Code?", t18, CURRENT)

    for rid, rtype, question, pat, note in REFUSALS:
        Q.append({"id": None, "type": "refusal_" + rtype, "timeline_id": None, "question": question,
                  "as_of_date": None, "target_version": None, "answerable": rid in ("R07", "R08"),
                  "gold_value": note, "gold_spans": [span("v1", 30, "These shall be CORSIA label credits")] if rid == "R08" else [],
                  "absent_in_target": rid not in ("R08",), "trap_spans": [],
                  "absence_evidence": {"pattern": pat, "versions_searched": ["v2.1"] if rid == "R07" else (["v1"] if rid == "R08" else VERSIONS)},
                  "closed_book_risk": rid == "R06"})
    for pid, question, tid, note in PARTIAL:
        t = next(t for t in T if t["timeline_id"] == tid)
        Q.append({"id": None, "type": "partial", "timeline_id": tid, "question": question, "as_of_date": None,
                  "target_version": VNUM[CURRENT], "answerable": "partial", "gold_value": note,
                  "gold_spans": t["values"][CURRENT]["spans"], "absent_in_target": False, "trap_spans": [],
                  "closed_book_risk": False})

    import hashlib
    for i, q in enumerate(Q, 1):
        q["id"] = f"q{i:03d}"
        # Fixed split: ~30% test, decided by a hash of the question text so it never moves.
        h = int(hashlib.sha256(q["question"].encode()).hexdigest(), 16) % 10
        q["split"] = "test" if h < 3 else "dev"

    # ------------------------------------------------------------ outputs
    with open(f"{out_dir}/timelines.json", "w", encoding="utf-8") as f:
        json.dump(T, f, ensure_ascii=False, indent=1)
    with open(f"{out_dir}/questions.jsonl", "w", encoding="utf-8") as f:
        for q in Q:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    # human-readable timeline table
    lines = ["# Fact timelines: VCMI Claims Code of Practice v1.0 to v3.2", "",
             "Every cell is backed by an exact quote checked against the cited PDF page (see timelines.json). "
             "'—' means the version does not address the fact (absence confirmed by text search).", "",
             "| ID | Fact | " + " | ".join(f"{VNUM[v]} ({PUB[v].strftime('%b %Y')})" for v in VERSIONS) + " |",
             "|---|---|" + "---|" * len(VERSIONS)]
    for t in T:
        cells = []
        for v in VERSIONS:
            e = t["values"][v]
            cells.append("—" if not e.get("value") else f"{e['value']} (p{e['spans'][0]['page']})")
        lines.append(f"| {t['timeline_id']} | {t['fact']} | " + " | ".join(cells) + " |")
    lines += ["", "## Traps (stale or misleading text a retriever may surface)", ""]
    for t in T:
        for tr in t["traps"]:
            lines.append(f"- **{t['timeline_id']}**, {VNUM[tr['version']]} p{tr['page']}: \"{tr['quote']}\". {tr['why']}")
    lines += ["", "## Notes", ""] + [f"- **{t['timeline_id']}**: {t['notes']}" for t in T if t["notes"]]
    open(f"{out_dir}/timelines.md", "w", encoding="utf-8").write("\n".join(lines) + "\n")

    counts = {}
    for q in Q:
        counts[q["type"]] = counts.get(q["type"], 0) + 1
    print(f"timelines: {len(T)}  questions: {len(Q)}  test: {sum(q['split']=='test' for q in Q)}  dev: {sum(q['split']=='dev' for q in Q)}")
    for k, n in sorted(counts.items()):
        print(f"  {k}: {n}")
    n_spans = sum(len(e.get("spans", [])) for t in T for e in t["values"].values()) + sum(len(t["traps"]) for t in T)
    print(f"quotes checked: {n_spans}  problems: {len(problems)}")
    for p in problems:
        print("  PROBLEM:", p)
    return 1 if problems else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
