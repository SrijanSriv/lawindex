# Development search results

Observed 20 September 2026 using `python3 scripts/evaluate_search.py --out data/import/search-dev-results.json`.

**All six expected provisions ranked first.** This is a development smoke run over four provisions, not an independent benchmark or a claim about legal research quality. Queries already informed the project requirements; there is no held-out evaluation here.

| Query | Expected provision | Actual ranked keys | Expected rank |
| --- | --- | --- | --- |
| DEV-001: RTI Act section 6 | `rti-2005:6` | `rti-2005:6` | 1 |
| DEV-002: Do I need to explain why I want information in an RTI request? | `rti-2005:6` | `rti-2005:6`, `rti-2005:8` | 1 |
| DEV-003: RTI application sent to the wrong public authority | `rti-2005:6` | `rti-2005:6`, `rti-2005:8` | 1 |
| DEV-004: RTI section 8 personal information exemption | `rti-2005:8` | `rti-2005:8` | 1 |
| DEV-005: central government power to protect and improve the environment | `environment-1986:3` | `environment-1986:3`, `environment-1986:5A` | 1 |
| DEV-006: appeal against a direction issued under environmental law to the National Green Tribunal | `environment-1986:5A` | `environment-1986:5A`, `environment-1986:3`, `rti-2005:8` | 1 |

Method: SQLite FTS5 BM25 with documented field weights, English stemming, OR matching, and explicit Act/provision filters. No question-specific answers or generated text.

Known limitation visible here: DEV-006 also returns other provisions that match generic terms. The first expected hit does not make every returned result relevant. Unavailable explicit section references return no substitute.

The run emits actual scores, normalized terms, filters, rankings, and timings. The local JSON report is generated output under ignored `data/import/`; rerun the command to reproduce it. Timing values vary by run and are not a latency benchmark.

Backend verification: all existing 25 importer checks and 15 `unittest` API/search tests passed from an isolated project copy. These include HTTP requests and invalidation tests; no browser/UI verification has occurred because the interface is pending.
