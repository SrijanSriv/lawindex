# Agent instructions for LawIndex

Start by reading [docs/HANDOFF.md](docs/HANDOFF.md). It covers current status, the pending user decision, the code map, verification commands and next steps. Then read [PHASES.md](PHASES.md).

Rules that always apply:

1. **Permission is limited to the 20 selected Acts, personal and non-commercial** (`data/phase3/access-authorization.json`). Do not add Acts, rules, regulations or notifications without new, recorded permission from the user. Do no network fetching of new sources, no public deployment and no commercial use.
2. **Text becomes searchable only through the importer and review records.** Never make search admit text directly.
3. **Never edit digest-bound files.**
   - Review plans: `data/phase3/review-plans/*.json`.
   - Review records: `data/review/*.review.json`.
   - The v1 benchmark queries, judgments and judging files, and `data/benchmark/runs/baseline-lexical-v1.json`.
   - To change the benchmark, make v2 files.
4. **Tune ranking on the dev split only.** Adopt a ranking change only under the rule in `docs/phase-4/TARGETS.md`.
5. **This directory is not a git repository.** Look before you overwrite or delete anything.
6. **Before saying work is done, run the relevant checks.**
   - `python3 -m unittest discover -s tests -q` for code changes (381 tests).
   - `python3 scripts/run_benchmark.py --compare data/benchmark/runs/baseline-lexical-v1.json --out /tmp/check.json` for anything that could affect search.
   - Report the results honestly.
7. **Leave decisions to the user.** Targets, scope, gate closure and permission are the user's to decide. Explain in plain language, and record decisions and new gaps in the docs, including `docs/EXPANSION_BACKLOG.md`.
8. **Keep background work to about three parallel jobs.** The user has hit usage limits before.
