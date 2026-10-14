# VCMI Claims Code of Practice: shortlist of the 30 most important changes

Ranking rule. Only substantive and status events are eligible. Events are placed in tiers: (1) explicit changes to a number, date or threshold (a full date, percentage, or a numeric duration/limit in a rule); (2) eligibility and claim status (status events; which credits, frameworks, entities or claims qualify); (3) other changes to rule wording (shall/must/should, requirements added or removed). Within a tier, events are ordered by how clearly they change the rule: certain records before uncertain ones, then requirement wording (shall/must/required/only/cannot) in the changed text, then normative sections (Foundational Criteria and Steps 1-4) before descriptive ones, then number of records. Citation years, footnote and page references, cover/version labels and Document History rows are not number changes.

Events come from `events.jsonl` (records grouped by underlying change); quotes are copied verbatim from member records in `changes.jsonl` and were re-checked against the raw `page.get_text()` text of the cited page (whitespace, ligatures and line-break hyphens normalised only): 38 quotes, 38 found, 0 failures.

## 1. Claim thresholds lowered: Silver from >= 20% and < 60% to >= 10% and < 50% of remaining emissions, Gold from >= 60% to >= 50% (Platinum stays >= 100%).

- event_id: `e-33de7c186c` (tier 1: number, date or threshold; 11 record(s))
- versions: 1.0 -> 2.0
- pages: old p6, 7, 18, 26, 27; new p7, 18, 26, 28
- old (vcmi-ccp-v1 p26, `c-3306826024`): "Purchase and retire high-quality carbon credits of an amount equivalent to or greater than 20% and less than 60% of their remaining emissions in the most recent reporting year, with credits only used to ﬁnance additional climate mitigation beyond these targets."
- new (vcmi-ccp-v2 p26, `c-3306826024`): "Carbon Integrity Silver requires the purchase and retirement of high-quality carbon credits in an amount equal to or greater than 10%, and less than 50%, of a company’s remaining emissions once it has demonstrated progress towards its near-term emission reduction targets."

## 2. Interim-options deadline moved from 1 January 2026 to 1 January 2027; after it only CCP-labelled or Article 6.4 credits may be used for VCMI Claims.

- event_id: `e-01b5022db8` (tier 1: number, date or threshold; 8 record(s))
- versions: 3.0 -> 3.1
- pages: old p31, 32, 33; new p31, 32, 33
- old (vcmi-ccp-v3.0 p32, `c-f4c74b3041`): "After 1 January 2026 only CCP-labelled or Article 6.4 credits may be used for VCMI Claims."
- new (vcmi-ccp-v3.1 p32, `c-f4c74b3041`): "After 1 January 2027 only CCP-labelled or Article 6.4 credits may be used for VCMI Claims."

## 3. New deadline: companies shall transition to CCP-Approved credits by 1 January 2026.

- event_id: `e-a5860b855a` (tier 1: number, date or threshold; 1 record(s))
- versions: 1.0 -> 2.0
- pages: old p-; new p30
- old: none (no old text: the change is a pure addition)
- new (vcmi-ccp-v2 p30, `c-365be0cbb5`): "Companies shall transition to purchase and retire CCP-Approved credits by January 1, 202615."

## 4. Rule stated that after 1 January 2026 only CCP-labelled or Article 6.4 credits may be used for VCMI Claims.

- event_id: `e-f7b4a7e5cf` (tier 1: number, date or threshold; 1 record(s))
- versions: 2.1 -> 3.0
- pages: old p-; new p32
- old: none (no old text: the change is a pure addition)
- new (vcmi-ccp-v3.0 p32, `c-cae9447b48`): "After 1 January 2026 only CCP-labelled or Article 6.4 credits may be used for VCMI Claims."

## 5. Interim options limited to 1 January 2026 or until CCP-labelled/Article 6.4 credits are widely available, whichever is earlier.

- event_id: `e-12a3f2f4c6` (tier 1: number, date or threshold; 1 record(s))
- versions: 2.1 -> 3.0
- pages: old p-; new p32
- old: none (no old text: the change is a pure addition)
- new (vcmi-ccp-v3.0 p32, `c-aa32f551cd`): "These options can only be used until 1 January 2026, or until CCP-labelled or Article 6.4 credits become widely available in the market, whichever is the earlier."

## 6. Removed the SBTi boundary rule requiring 95% coverage of scope 1 and 2 emissions and 67% of scope 3.

- event_id: `e-eeb02be8c1` (tier 1: number, date or threshold; 1 record(s))
- versions: 2.1 -> 3.0
- pages: old p22; new p-
- old (vcmi-ccp-v2.1 p22, `c-e7e608d9a3`): "Companies must follow the most up to date SBTi or equivalent criteria for setting the target boundary and emissions coverage (this means 95% coverage of scopes 1 and 2 emissions, and 67% coverage of scope 3 emissions, if scope 3 emissions represent over 40% of the inventory from all scopes)."
- new: none (no new text: the change is a pure removal)

## 7. Removed the requirement that companies with unvalidated SBTi-style targets submit them to SBTi for validation within 24 months.

- event_id: `e-1a308c8ed7` (tier 1: number, date or threshold; 1 record(s))
- versions: 2.1 -> 3.0
- pages: old p22; new p-
- old (vcmi-ccp-v2.1 p22, `c-1b8d6374be`): "For companies with targets following the SBTi near-term target setting criteria, but which have not had these targets validated, they must submit a target to SBTi for validation within 24 months9."
- new: none (no new text: the change is a pure removal)

## 8. Removed the requirement for power companies to set a third target covering 100% of emissions from downstream use of fossil fuels.

- event_id: `e-49c10e0ed0` (tier 1: number, date or threshold; 1 record(s))
- versions: 2.1 -> 3.0
- pages: old p22; new p-
- old (vcmi-ccp-v2.1 p22, `c-b230d83f3e`): "For power companies, SBTi sector specific criteria must be followed, including setting a third target covering 100% of emissions from downstream use of fossil fuels."
- new: none (no new text: the change is a pure removal)

## 9. Added the requirement to submit unvalidated targets to SBTi for validation within 24 months.

- event_id: `e-d50efac9b5` (tier 1: number, date or threshold; 1 record(s))
- versions: 1.0 -> 2.0
- pages: old p-; new p21
- old: none (no old text: the change is a pure addition)
- new (vcmi-ccp-v2 p21, `c-11985e563c`): "For companies with targets following the SBTi near-term target setting criteria, but which have not had these targets validated, they must submit a target to SBTi for validation within 24 months8."

## 10. Added interim options for credit procurement (CORSIA-eligible credits, or due diligence aligned with the 10 CCPs) pending CCP-labelled credits.

- event_id: `e-4eb60f495b` (tier 1: number, date or threshold; 11 record(s))
- versions: 1.0 -> 2.0
- pages: old p-; new p29, 30
- old: none (no old text: the change is a pure addition)
- new (vcmi-ccp-v2 p30, `c-0f3c6894c5`): "For VCMI Claims made on or after January 1, 202615, to comply with this VCMI Claims Code requirement, companies must transition to purchasing and retiring CCP-Approved credits."

## 11. Claims retired: as of 23 September 2026 VCMI is no longer issuing Carbon Integrity Claims and the claims infrastructure is retired.

- event_id: `e-5b186e3742` (tier 2: eligibility or claim status; 16 record(s))
- versions: 3.1 -> 3.2
- pages: old p1, 11, 18; new p1, 3, 6, 9, 11, 19
- old (vcmi-ccp-v3.1 p18, `c-516216c5b1`): "By following these steps and adhering to the requirements, a company will be able to obtain one of the enterprise-wide claims described in this Claims Code: Carbon Integrity Silver, Carbon Integrity Gold, or Carbon Integrity Platinum."
- new (vcmi-ccp-v3.2 p6, `c-dacb6a047b`): "VCMI Claims Code v3.2, 23 September 2026: Please note at this point in time VCMI is not issuing Carbon Integrity Claims."

## 12. Claims became available: companies can now make Carbon Integrity Claims, as the MRA Framework is in place.

- event_id: `e-c75c7c03ed` (tier 2: eligibility or claim status; 4 record(s))
- versions: 1.0 -> 2.0
- pages: old p9, 12; new p10, 13
- old (vcmi-ccp-v1 p9, `c-7511f0bcfb`): "From November, companies will be able to obtain VCMI Claims, once information relating to the requirements included in the Claims Code have undergone an assurance process as outlined in the upcoming MRA framework."
- new (vcmi-ccp-v2 p10, `c-7511f0bcfb`): "Companies are now able to make Carbon Integrity Claims, and all information relating to the requirements included in the Claims Code can now undergo an assurance process as outlined in the newly-released MRA Framework."

## 13. Article 6.4 credits (Paris Agreement Crediting Mechanism) accepted alongside CCP-labelled credits.

- event_id: `e-0e9ec97117` (tier 2: eligibility or claim status; 1 record(s))
- versions: 2.1 -> 3.0
- pages: old p-; new p31
- old: none (no old text: the change is a pure addition)
- new (vcmi-ccp-v3.0 p31, `c-cb07065b34`): "Companies shall retire ICVCM Core Carbon Principles-labelled credits or Article 6.4 credits issued under Article 6.4 methodologies approved by the Article 6.4 Supervisory Body when they become available."

## 14. Credits from methodologies rejected or excluded in the ICVCM assessments may not be used.

- event_id: `e-f1ee53b8f9` (tier 2: eligibility or claim status; 1 record(s))
- versions: 3.0 -> 3.1
- pages: old p-; new p32
- old: none (no old text: the change is a pure addition)
- new (vcmi-ccp-v3.1 p32, `c-410c399e56`): "Please note however, companies shall not use credits from methodologies which have already been rejected or excluded by programs as part of the ICVCM assessments."

## 15. Target boundary and coverage now follow the chosen science-aligned target-setting framework, not SBTi only.

- event_id: `e-e29013664e` (tier 2: eligibility or claim status; 1 record(s))
- versions: 2.1 -> 3.0
- pages: old p-; new p22
- old: none (no old text: the change is a pure addition)
- new (vcmi-ccp-v3.0 p22, `c-ed392014e5`): "Companies shall follow the criteria outlined in the chosen science-aligned target setting framework for setting the target boundary and emissions coverage7."

## 16. Targets must follow the SBTi organisational-boundary criteria (parent or group level, not subsidiary level).

- event_id: `e-2767412072` (tier 2: eligibility or claim status; 1 record(s))
- versions: 2.0 -> 2.1
- pages: old p-; new p22
- old: none (no old text: the change is a pure addition)
- new (vcmi-ccp-v2.1 p22, `c-6359d5c26b`): "The near-term emission reduction targets companies disclose shall also follow the organizational boundary criteria set out by SBTi8, which states that companies should submit targets only at the parent or group-level, not the subsidiary level."

## 17. Target boundary criteria opened from SBTi only to 'the most up to date SBTi or equivalent criteria'.

- event_id: `e-0b7385c187` (tier 2: eligibility or claim status; 1 record(s))
- versions: 1.0 -> 2.0
- pages: old p21; new p21
- old (vcmi-ccp-v1 p21, `c-72342b0e19`): "Companies must follow SBTi criteria for setting the target boundary and emissions coverage (this means 95 percent coverage of scopes 1 and 2 emissions, and 67 percent coverage of scope 3 emissions if scope 3 emissions represent over 40 percent of the inventory from all scopes)."
- new (vcmi-ccp-v2 p21, `c-72342b0e19`): "Companies must follow the most up to date SBTi or equivalent criteria for setting the target boundary and emissions coverage (this means 95% coverage of scopes 1 and 2 emissions, and 67% coverage of scope 3 emissions, if scope 3 emissions represent over 40% of the inventory from all scopes)."

## 18. Removed the rule that credits applied to a claim shall be CORSIA label credits until the ICVCM framework is implemented.

- event_id: `e-57ebd8d8c8` (tier 2: eligibility or claim status; 1 record(s))
- versions: 1.0 -> 2.0
- pages: old p30; new p-
- old (vcmi-ccp-v1 p30, `c-dd1616b429`): "These shall be CORSIA label credits, and once the ICVCM Assessment Framework is implemented, companies shall transition to purchase and retire CCP label credits."
- new: none (no new text: the change is a pure removal)

## 19. Companies may report emissions under a national GHG accounting framework adapted from the GHG Protocol.

- event_id: `e-c913ab4f12` (tier 2: eligibility or claim status; 1 record(s))
- versions: 2.1 -> 3.0
- pages: old p-; new p21
- old: none (no old text: the change is a pure addition)
- new (vcmi-ccp-v3.0 p21, `c-da348115cd`): "Companies may also use their national GHG accounting framework if it has been adapted from the GHG Protocol Corporate Accounting and Reporting Standard."

## 20. Targets may be submitted at parent or subsidiary level.

- event_id: `e-b03380e93a` (tier 2: eligibility or claim status; 1 record(s))
- versions: 2.1 -> 3.0
- pages: old p-; new p22
- old: none (no old text: the change is a pure addition)
- new (vcmi-ccp-v3.0 p22, `c-cb78dfc877`): "Companies can submit targets at the parent or subsidiary level."

## 21. Removed the statement accepting CORSIA or due-diligence credits until the ICVCM Assessment Framework is implemented.

- event_id: `e-1f82a1b7f1` (tier 2: eligibility or claim status; 1 record(s))
- versions: 3.0 -> 3.1
- pages: old p33; new p-
- old (vcmi-ccp-v3.0 p33, `c-26652c45eb`): "While CCP labelled credits are not widely available in the market, CORSIA eligible credits or high quality credits supported by the company’s due diligence process alignment to ICVCM’s 10 CCPs, will be accepted as an interim measure until the ICVCM Assessment Framework has been implemented."
- new: none (no new text: the change is a pure removal)

## 22. New rule: the most recent reporting year cannot be the same as the base year.

- event_id: `e-c42fe0eaaf` (tier 3: rule wording; 1 record(s))
- versions: 3.0 -> 3.1
- pages: old p-; new p27
- old: none (no old text: the change is a pure addition)
- new (vcmi-ccp-v3.1 p27, `c-709ab1238d`): "Note that the most recent reporting year cannot be the same as the base year."

## 23. New rule: reductions must be reported on the same basis (absolute or intensity) as the near-term target.

- event_id: `e-8e519108c3` (tier 3: rule wording; 1 record(s))
- versions: 2.1 -> 3.0
- pages: old p-; new p27
- old: none (no old text: the change is a pure addition)
- new (vcmi-ccp-v3.0 p27, `c-f14de5c356`): "This reduction can be demonstrated either on an absolute or intensity basis but the selected approach(es) (absolute or intensity) shall be aligned with the approach(es) used for near-term science-aligned emissions reduction target(s)."

## 24. Removed the requirement to provide the SBTi commitment letter as evidence for a VCMI Claim.

- event_id: `e-b17382592f` (tier 3: rule wording; 1 record(s))
- versions: 2.1 -> 3.0
- pages: old p22; new p-
- old (vcmi-ccp-v2.1 p22, `c-bdb3481276`): "To obtain a VCMI Claim, the company must provide evidence of the SBTi commitment letter as part of the formal SBTi commitment process."
- new: none (no new text: the change is a pure removal)

## 25. New rule: companies not engaged in policy advocacy shall publicly disclose that they do not engage in it.

- event_id: `e-b8ccc9d54b` (tier 3: rule wording; 1 record(s))
- versions: 1.0 -> 2.0
- pages: old p-; new p24
- old: none (no old text: the change is a pure addition)
- new (vcmi-ccp-v2 p24, `c-5e9b4d51eb`): "In cases where companies are not taking part in public policy advocacy activities, they shall publicly disclose that they do not engage in any activities, either directly or indirectly, that might influence policies, laws, or regulations with potential climate impact."

## 26. Public net-zero commitment changed from a requirement to an encouragement.

- event_id: `e-c43d4dfc32` (tier 3: rule wording; 1 record(s))
- versions: 2.1 -> 3.0
- pages: old p22; new p23
- old (vcmi-ccp-v2.1 p22, `c-ee92d5cec5`): "Make a public commitment to achieve net-zero emissions no later than 2050, including scopes 1, 2 and 3 GHG emissions, as well as land-based GHG emissions where applicable;"
- new (vcmi-ccp-v3.0 p23, `c-ee92d5cec5`): "Companies are encouraged to make a public commitment to achieve net-zero emissions no later than 2050, including scope 1, scope 2 and scope 3 GHG emissions, as well as land-based GHG emissions where applicable."

## 27. Foundational Criterion 3 redefined from being on-track and minimising cumulative emissions to making progress on financial allocation, governance and strategy.

- event_id: `e-f86499a687` (tier 3: rule wording; 1 record(s))
- versions: 1.0 -> 2.0
- pages: old p22; new p22
- old (vcmi-ccp-v1 p22, `c-39d9583e39`): "Foundational Criterion 3: Demonstrate that the company is on-track towards meeting a near-term emissions reduction target and minimizing cumulative emissions over the target period"
- new (vcmi-ccp-v2 p22, `c-39d9583e39`): "Foundational Criterion 3: Demonstrate that the company is making progress on financial allocation, governance, and strategy towards meeting its near-term emission reduction target"

## 28. Foundational Criterion 2 changed from validated science-based targets to science-aligned targets.

- event_id: `e-d31c7c83e0` (tier 3: rule wording; 4 record(s))
- versions: 1.0 -> 2.0
- pages: old p6, 18, 19, 20; new p6, 18, 19, 20
- old (vcmi-ccp-v1 p6, `c-8f1f4c04de`): "Set and publicly disclose validated science-based near-term emissions reduction targets, and publicly commit to reaching net zero emissions no later than 2050;"
- new (vcmi-ccp-v2 p6, `c-8f1f4c04de`): "set and publicly disclose science-aligned near-term emission reduction targets, and publicly commit to reaching net-zero emissions no later than 2050;"

## 29. New requirement: third-party limited assurance of scope 1 and scope 2 emissions (base and most recent year).

- event_id: `e-3a477b3b0d` (tier 3: rule wording; 1 record(s))
- versions: 2.1 -> 3.0
- pages: old p-; new p21
- old: none (no old text: the change is a pure addition)
- new (vcmi-ccp-v3.0 p21, `c-8d8b12a385`): "Obtain third-party, limited assurance of scope 1 and scope 2 emissions for base year and most recent reporting year."

## 30. New step: submitted claim information undergoes independent third-party verification.

- event_id: `e-c3b22b02c3` (tier 3: rule wording; 1 record(s))
- versions: 2.1 -> 3.0
- pages: old p-; new p36
- old: none (no old text: the change is a pure addition)
- new (vcmi-ccp-v3.0 p36, `c-ca04f9f611`): "Once companies have submitted the required information and evidentiary documentation to the VCMI Claims Reporting Platform (refer to Section 4 of the MRA Framework for guidance), this information and documentation is then subjected to independent, third-party verification to ensure companies are compliant with VCMI’s requirements to make a claim."

## Records not used as quote sources

These records are single sentences in the cleaned text, but in the raw `page.get_text()` stream their text is interrupted by a running footer, footnote or sidebar heading (sentence runs across a column or page break), so they fail the contiguous raw-text check and are never used for quotes:

- `c-2d3e1dc83b` (old text, p6): "VCMI Silver is the most accessible tier, requiring the purchase and retirement of high-quality credits in an amount equa..."
- `c-10002732bf` (old text, p9): "This modular approach is intended to ensure that all outstanding issues identified during the consultation process are a..."
- `c-5b5bf1c0bd` (old text, p16): "An “on-ramp” will also be created for companies at the beginning of their decarbonization journey, and which may initial..."
- `c-67b2ad8a64` (new text, p19): "Companies shall also include scope 3 emissions for all existing emissions sources, according to the minimum boundary est..."
- `c-f40ec55a18` (old text, p19): "However, a single and consistent accounting approach (either market-based or location-based) must be used for setting an..."
- `c-a7f46e6838` (old text, p20): "Set and publicly disclose validated near-term emissions reduction targets by the year they are seeking to make a VCMI Cl..."
