# Tasks for delegated agents (Grok 4.7 high fast)

Scoped 25 September 2026. The user decides when each wave begins. **Wave 1 done, 25 September 2026.** G1, G2, G3 and G7 were reviewed and accepted by the main agent. Full suite: 352 tests pass, and `--compare` against the baseline prints `REPRODUCED`. G2's finding is recorded in backlog item 2.10: a threshold change alone cannot fix `weak_match`. **Wave 2 approved.** G4 was reverted and is kept on record. G5 was adopted. G6 started on 25 September 2026.

The main agent owns the plan ([PLAN.md](PLAN.md)), the data contracts, every ranking and threshold decision, review of each delegated change, and the final checks. Delegated agents implement against the specification below. When the specification is wrong or unclear, they stop and report; they do not work around it.

## Rules for every task

Read these before starting: `AGENTS.md`, this file, `docs/phase-4/TARGETS.md`, and the source files your task names.

- **This directory is not a git repository.** Before editing any existing file, copy it to `/tmp/lawindex-backup/<task-id>/`, keeping the relative path. Say in your report that you did.
- **Edit only the files your task lists.** Never edit:
  - `data/phase3/review-plans/`, `data/review/`, `data/benchmark/queries.v1.jsonl`, `data/benchmark/judgments.v1.jsonl`, anything in `data/benchmark/judging/`, or `data/benchmark/runs/baseline-lexical-v1.json`;
  - the importer, `web/`, `PHASES.md`, `docs/HANDOFF.md`, `docs/phase-4/`, or existing tests.
  If an existing test fails because of your change, stop and report it. Do not change the test.
- **No network access**, no package installs, no importer runs, no `--fresh`, no server left running. Use the Python standard library only.
- **Text becomes searchable only through the importer.** Your code must never add text to search.
- **The test split is held out.** Never print, read or reason about test-split queries one by one. Aggregates over the test split are allowed where the task says so.
- **Write benchmark runs to `/tmp`**, never into `data/benchmark/runs/`. Always pass `--out /tmp/<name>.json`.
- **Match the surrounding code:** small functions, a docstring only where the reason is not obvious, and no comments that narrate the change. Tests use `unittest` in `tests/`, with small in-memory fixtures. Load the real `Snapshot()` at most once per test class.
- **Checks you run:**
  - your own new tests;
  - `python3 -m unittest tests.test_retrieval tests.test_search tests.test_coverage_signals tests.test_evaluation -q` as a regression check;
  - for Wave 2 tasks, also `python3 scripts/run_benchmark.py --compare data/benchmark/runs/baseline-lexical-v1.json --out /tmp/<task-id>-run.json`.

  Do not run the full suite. The main agent runs it.
- **Finish with a short report:** files created or changed, backups made, commands run with their exact results and counts, any problem with the specification, and anything left undone. Do not say work is done without the command output behind it.

## Waves

| Wave | Tasks | Why this order |
| --- | --- | --- |
| 1 | G1, G2, G3 in parallel | New files only, disjoint. No change to search behaviour. |
| 1b | G7, after one of G1–G3 finishes | Keeps parallel work at three. |
| 2 | G4, then G5, then G6, one at a time | All three edit `lawindex/search.py`. Each starts only after the main agent has reviewed and accepted, or reverted, the one before. |
| Blocked | Embedding pipeline | Needs the user's decisions on the embedding model and on downloading model weights. The main agent designs it. |

---

## G1: adoption report

**Files:** create `lawindex/adoption.py` and `tests/test_adoption.py`. Edit `scripts/run_benchmark.py` to add one flag, `--adoption`, which is valid only together with `--baseline` and `--candidate`.

`lawindex/adoption.py` is pure: it takes the two loaded run dicts and returns a report. It checks every condition of the adoption rule in `docs/phase-4/TARGETS.md` section 2, and every floor in section 1. Hold the floor numbers in one module-level constant that cites TARGETS.md. Read everything from the run files' `aggregate` and `queries`:

| Check | How to compute it |
| --- | --- |
| Test nDCG@10 gain ≥ 0.03 | `aggregate["split:test"]["ndcg_at_10"]["mean"]`, candidate minus baseline |
| Paired 95% interval excludes zero, test split | `paired_ndcg_comparison` from `lawindex/evaluation.py`, split `test`. Excluding zero means both ends above 0. |
| Test nDCG@10 ≥ 0.63, MRR ≥ 0.69, MRR at document level ≥ 0.88 | candidate `split:test` means of `ndcg_at_10`, `mrr` and `mrr_doc` |
| 13 of 13 document-level queries rank the right Act first | candidate rows with `level == "document"`: count `success_at_1_doc == 1.0`, and require the count to equal the number of such rows, which is 13 |
| False notice rate ≤ 0.10 | candidate `aggregate["overall"]["false_notice_rate"]["mean"]` |
| Notice recall ≥ 0.68 | candidate `aggregate["overall"]["notice_recall"]["mean"]` |
| No category with ≥ 8 scored queries loses more than 0.05 | for each `category:*` group where the **baseline** `ndcg_at_10.n` ≥ 8: candidate mean minus baseline mean ≥ −0.05 |
| judged@10 ≥ 0.9 on both splits | candidate `split:dev` and `split:test` `judged_at_10` means |

The report lists each check with its value, threshold and pass or fail, and ends with one line: `ALL CONDITIONS MET` or `NOT MET: <failed checks>`. The exit code is 0 either way; this is a report, not a gate. A missing value is a failure that says the value is missing. Print aggregates only, never per-query test rows.

**Tests:** build small synthetic run dicts by hand, one for each check passing and failing, including a category below 8 queries that is ignored and a missing value. One end-to-end test runs `--baseline X --candidate X --adoption` on the real baseline file. Expect gain 0, which fails the 0.03 check, while every floor passes and judged@10 is 1.0.

## G2: weak-match diagnostic

**Files:** create `scripts/analyze_notices.py` and `tests/test_analyze_notices.py`. Do not edit `lawindex/search.py`.

The `weak_match` notice (`coverage_notices` in `lawindex/search.py`) fires when the best of the top results contains less than half (`WEAK_MATCH_SHARE`) of the query's content words. It gives 7 false notices on in-corpus queries. The main agent will pick any new rule; this task only measures.

- For every benchmark query, run `snapshot.search(query, limit=20, filters=...)` as `run_benchmark.py` does. Compute the best share using the same inputs and helpers the notice uses: `parse_query`, `QUESTION_WORDS`, `_stem`, `TOKEN` and `ALIASES`, imported from `lawindex.search`. Assert that a share below 0.5 matches whether `weak_match` is present, for every query. If it does not match, stop and report.
- **Dev split only:** print one line per query with id, scope, category, number of content words, best share, and whether `weak_match` fired. Then print a sweep over thresholds 0.2, 0.3, 0.4, 0.5 and 0.6. For each threshold, and separately for minimum content-word counts of 3, 4 and 5, report how many in-corpus queries would be flagged (false notices) and how many out-of-corpus or partial queries would be flagged.
- **Test split:** print only the same sweep, as counts. No per-query lines.
- `--json PATH` writes the same data. Test-split rows appear there only as counts.

**Tests:** check the share computation on a hand-built records dict against hand-checked shares. Check that the sweep counts are right on synthetic rows. Check that no test-split query id appears in the printed output, using one real run.

## G3: reciprocal rank fusion

**Files:** create `lawindex/fusion.py` and `tests/test_fusion.py`. It is not wired into search. The main agent does that in Phase 5.

```python
def reciprocal_rank_fusion(rankings: dict[str, list[str]], k: int = 60, limit: int | None = None) -> list[dict]:
```

- `rankings` maps a method name (for example `"lexical"`, `"vector"`) to provision keys in rank order, best first.
- The score of a key is the sum over methods of `1 / (k + rank)`, with rank counted from 1. A key missing from a method adds nothing for that method.
- A key repeated within one method's list counts once, at its best rank.
- Order by score descending, then by best single rank ascending, then by key ascending. The result is fully deterministic.
- Each result is `{"key", "score", "ranks": {method: rank}}`, with `score` rounded to 9 decimals.
- Reject `k < 1`, an empty `rankings` dict, and a non-list ranking with `ValueError`. An empty list for one method is allowed.

**Tests:** hand-computed scores for two methods with overlap, `k=60` and `k=1`; tie-breaking at each level; duplicate handling; `limit`; the errors; and a single method, which must return that method's order unchanged.

## G7: packets for unjudged pairs

**Files:** create `scripts/unjudged_packets.py` and `tests/test_unjudged_packets.py`. Outputs go under `data/benchmark/judging-v2/` only when the main agent runs the script; tests use temporary directories. Never write to `data/benchmark/judging/`.

A new retrieval method surfaces provisions nobody judged. `judged@10` then falls, and TARGETS.md requires those pairs to be judged before a comparison counts.

- `python3 scripts/unjudged_packets.py --run RUN.json [--run RUN2.json ...] --judge A|B [--batch-size 8] [--out DIR]` collects, from every run, each query's `unjudged_in_top_10` pairs. It de-duplicates them against each other and against `data/benchmark/judgments.v1.jsonl`.
- It writes packets and `expected.json` files in exactly the format of `scripts/judging_packets.py`: the same header, candidate rendering, truncation and per-judge shuffle. Reuse that script's functions by importing them; do not copy them.
- It covers dev **and** test queries: judges see query text, which is allowed, but the script prints only counts per split, never per-query test lines.
- The output must be accepted by `scripts/merge_judgments.py check`. If `check` cannot be pointed at a new directory without editing it, stop and report; do not edit `merge_judgments.py`.

**Tests:** synthetic run files with overlapping unjudged pairs, pairs already judged, and both splits. Check de-duplication, batch contents, shuffle determinism, and that packets from a temporary directory pass `merge_judgments.py check`.

---

## G4: acronym aliases (backlog 2.7 and 2.8)

**Starts only when the main agent says so.** This changes ranking.

**Files:** edit `ALIASES` in `lawindex/search.py`. Add tests to a new file, `tests/test_acronym_aliases.py`.

Today only RTI, EPA and POSH have aliases. "RERA section 18" returns nothing, and "DPDP Act 2023 …" is reported as an unindexed Act. Add exactly these aliases:

| Act slug | Aliases |
| --- | --- |
| `dpdp-2023` | `DPDP`, `DPDP Act` |
| `real-estate-2016` | `RERA` |
| `education-2009` | `RTE`, `RTE Act` |
| `information-technology-2000` | `IT Act` |
| `consumer-protection-2019` | `CPA` |
| `fcra-2010` | `FCRA` |

Never add a bare `IT` alias. Alias matching is case-insensitive on whole words, so `it` would match almost every query. If you think another alias is needed, list it in your report and do not add it.

Aliases do two things. They select an Act when the query names it. They are also indexed in the title field of every section of that Act, so they change BM25 scores for other queries as well. That second effect is why this task is measured.

**Tests:**
- "RERA section 18" returns `real-estate-2016:18` first.
- "DPDP Act 2023 obligations of data fiduciary" has no `act_not_indexed` notice and selects `dpdp-2023`.
- A query containing the ordinary word "it" selects no Act.

**Measure:** write a run with `--out /tmp/g4-run.json`, then run `--baseline data/benchmark/runs/baseline-lexical-v1.json --candidate /tmp/g4-run.json`, adding `--adoption` if G1 has landed. Report dev and test aggregates, the paired intervals, and the dev-split worst-10 list. `--compare` against the baseline will now print differences. That is expected; report how many there are. Do not decide adoption.

### G4 result, 25 September 2026

The change is exactly the six alias entries. Its three tests pass. The run is `/tmp/g4-run.json`, and the backup of the previous `search.py` is in `/tmp/lawindex-backup/G4/`.

| Measure | Baseline | With G4 |
| --- | --- | --- |
| Test nDCG@10 | 0.651 | 0.673 (+0.022; 95% interval −0.0001 to +0.054) |
| Dev nDCG@10 | 0.644 | 0.650 (+0.005; interval −0.012 to +0.030) |
| Test MRR | 0.710 | 0.738 |
| False notice rate | 0.067 | 0.050 |
| Acronym category | 0.523 | 0.587 (+0.064) |
| Citation category | 0.746 | 0.820 (+0.075) |

Every floor holds, and no category loses more than 0.0003. The adoption rule is **not met**: the test gain is below 0.03, and its interval touches zero. Adoption is the user's decision.

## G5: known central Act titles (backlog 2.2 and 2.11)

**Starts after G4 is settled.** This changes notices.

**Files:** create `data/reference/central_act_titles.v1.json` and `tests/test_known_titles.py`. Edit `coverage_notices` and title loading in `lawindex/search.py`.

- The file lists central Acts and Codes that are **not** among the 20 indexed Acts. Each entry is `{"title", "short_names": [...], "year"}`, and the file has a top-level `"provenance"`. It is a list of names only, never text, so it does not admit anything or add an Act.

  Because there is no network access, the list comes from model knowledge. Set provenance to say so and to say it is unverified. Keep it to well-known Acts people are likely to search for, at most 60 entries. Include:
  - the Bharatiya Nyaya Sanhita, Nagarik Suraksha Sanhita and Sakshya Adhiniyam, 2023, each with short names (`BNS`, `BNSS`, `BSA`);
  - the Indian Penal Code and Code of Criminal Procedure (`IPC`, `CrPC`);
  - the Income-tax Act, 1961, the Central Goods and Services Tax Act, 2017 (`GST`, `CGST Act`), the Companies Act, 2013, and the Hindu Marriage Act, 1955;
  - the National Green Tribunal Act, 2010.
- A query that names a listed Act by title (with or without "The" and the year) or by a short name, as a whole word and case-insensitively, gets an `act_not_indexed` notice naming that Act. **Results are still shown.** A notice never hides results. The existing behaviour for an unmatched cited title with a year is unchanged.
- If the query also names an indexed Act, there is no notice for the indexed one.
- Short names shorter than 3 characters are not allowed.

**Tests:** the title and short-name forms; case; whole-word matching ("BNSS" does not also fire "BNS"); an indexed Act gets no notice; results still returned; a validator that rejects duplicate titles, short names under 3 characters, and titles that collide with the 20 indexed Acts.

**Measure** as in G4. Report notice recall and false notice rate, overall and per split, against the baseline (0.684 and 0.067). This is a notice-only change, so it is judged by the notice-only rule in TARGETS.md: every ranking unchanged, every floor held, and a false notice rate that does not rise.

Check the rankings: load `/tmp/g5-run.json` and the baseline, and confirm every query's `ranking` is identical. Report the count of queries whose `ranking` differs (expected 0), and list which fields differ elsewhere. Do not list test-split ids. Do not decide adoption.

**Result, 25 September 2026.** The main agent reviewed the change. It corrected one title in the list ("Hindu Adoptions and Maintenance Act") and re-measured. The list has 56 entries.

| Measure | Baseline | With G5 |
| --- | --- | --- |
| Queries whose ranking or scores differ | — | 0 of 162 |
| Queries whose notices differ | — | 3 |
| False notice rate | 0.067 | 0.067 |
| Notice recall, overall | 0.684 | 0.789 |
| Notice recall, dev / test | 0.750 / 0.571 | 0.833 / 0.714 |

Every floor holds, and the full suite passes (381 tests). This meets the notice-only rule. **The user adopted G5 on 25 September 2026 and approved G6.**

Two limits:
- The list comes from model knowledge and is unverified.
- The file is loaded with the snapshot, so a malformed list makes search unavailable instead of silently skipping these notices.

## G6: held-back section notice (backlog 2.12)

**Starts after G5 is settled.** This changes notices only, never results.

**Files:** edit `lawindex/search.py`. Create `tests/test_held_back_notice.py`.

- When a query selects exactly one indexed Act (by title, alias or the `act` filter), names a section, and that section key exists in `data/phase3/candidates/<slug>.json` but is not in `snapshot.records`, add a notice with code `section_not_indexed` and a message along the lines of: "Section N of <Act> exists in the source but is not searchable yet. Open the source PDF to read it."
- Read the candidate files once, when the snapshot loads. Read keys only; never the candidate text. If a candidate file is missing or malformed, add no notice for that Act. Do not fail search.
- `lawindex/evaluation.py` counts only `*_not_indexed` codes and `weak_match` as false notices, so this notice is measured by the existing false-notice rate. That is intended.

**Tests:**
- A held-back key, for example `contract-1872:73`, gives the notice. Confirm first that it is held back.
- An admitted section gives no notice.
- A section number that is not in the source gives no notice.
- A missing candidate file gives no notice and no error.

**Measure** as in G5.

---

## What the main agent keeps

- **Decisions and reviews:** reviewing every delegated change, running the full suite and the benchmark, and recommending adoption or revert to the user under TARGETS.md.
- **The `weak_match` rule:** choosing a new threshold, word count or rule from G2's dev-split data. Then measuring it and recommending it.
- **Phase 5 structure:** the retrieval-mode contract (lexical, vector and hybrid, under the same query, filters and trace), wiring G3 into search, vector-index validity (the model and version bound to the index, and refusal to mix them), and the embedding pipeline once the user has chosen a model.
- **Judging:** judging and adjudicating the v2 pairs that G7 packages, under the judging guide.
- **Coverage (backlog 1.6):** the 111 held-back sections whose body agrees but whose footnote wording differs. They could be admitted with a recorded footnote conflict. That goes through the importer and new review records, so it stays with the main agent and needs the user's go-ahead.
