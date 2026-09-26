# Judging guide

You are judging whether provisions of Indian central Acts help answer a search query. Your judgments become the benchmark that later ranking changes are measured against, so consistency and honesty matter more than speed.

## What you see

Each packet lists queries. For each query: the text a user typed, an **intent** (what the user wants), any filters, and a set of candidate provisions in random order. Candidates were gathered from several different search methods. You are not told which method found which candidate or how it ranked. Do not try to guess.

## Judge against the intent, reading the text

Read each candidate's text, not only its heading. Headings mislead: "Consent." may be the answer to a consent question, but so may a long section with a dull heading. Judge what the provision says, as it is written. Do not use outside knowledge of the law to upgrade a provision that does not itself say the thing. Do not judge whether the law is current or correctly reproduced.

## Grades

| Grade | Name | Use when |
| --- | --- | --- |
| **3** | Answers | The provision states the rule, right, duty, procedure, time limit, penalty or definition the intent asks about. A user could stop reading here. More than one provision can be a 3 (for example, a right and the section that sets its time limit, when the intent asks for both). |
| **2** | Relevant | Needed to answer, but not the answer on its own: a qualification or exception to the answer, the companion procedure, the body that decides, the appeal from it, or the penalty for breaking the rule asked about. A user would want to read it. |
| **1** | Marginal | On the topic but no help in answering: it uses the words, cross-refers to the answer, is a rule-making power on the subject, or a definitions list that mentions the term in passing. |
| **0** | Not relevant | A different topic, or the right words in a different sense ("consent" of a government vs a person's consent to data processing). |

Rules of thumb:

- **Right Act matters.** A provision from the wrong Act on a similar topic is at most 1, unless the intent is a cross-Act question (broad discovery), where every Act counts equally.
- **Broad discovery queries** ("offences by companies", "appeal to High Court") are answered by every provision, in any Act, that is an instance of the thing asked. Grade each instance 3 if it is squarely the thing, 2 if partly.
- **Citation queries** ("RTI Act section 6"): the cited section is 3. Sections the cited one depends on to be understood are 2. Same-numbered sections of other Acts are 0.
- **Filtered queries**: the filter is part of the need. Judge only whether the provision serves the intent; everything shown already satisfies the filter.
- **Rule-making and "power to make rules" sections** are 1 unless the query is about rule-making.
- **Omitted or repealed sections** ("Omitted.", "Repealed.") are 0 unless the query asks about repeal.
- When torn between two grades, pick the lower and say why in the rationale.

## Manual exploration

The pool may miss the best provision. After judging a query's candidates, if you believe an admitted provision the pool missed would be a 2 or 3, look for it:

```
python3 scripts/show_provision.py --act SLUG                 # list an Act's admitted sections
python3 scripts/show_provision.py --grep 'PATTERN' [--act SLUG]
python3 scripts/show_provision.py KEY                        # read one in full
```

Add at most five per query, as `source: "manual"`. Only admitted provisions can be added (the tool shows only those). Spend a few minutes at most per query; this is a safety net, not a second search engine.

If the best answer is a section that is **not admitted** (you will see it missing from `--act` listings, for example a Contract Act section that exists in the Act but not in the list), or lives in material we don't index (a schedule, rules, a different Act), record it as an `unindexed_target` with a one-line reason. Do not grade it.

## Output

Write one JSON object per line to the output file you are given (`data/benchmark/judging/raw/<judge>/batch-NN.jsonl`):

```
{"kind": "judgment", "query_id": "B-012", "provision_key": "copyright-1957:55", "grade": 2, "rationale": "Civil remedies for infringement; relevant once infringement is established, but does not say what is fair dealing.", "source": "pool"}
{"kind": "judgment", "query_id": "B-012", "provision_key": "copyright-1957:63", "grade": 1, "rationale": "Criminal offence of infringement; does not address the exceptions asked about.", "source": "manual"}
{"kind": "unindexed_target", "query_id": "B-012", "target": "copyright-1957:52", "rationale": "Section 52 lists acts that are not infringement (fair dealing) but is not admitted."}
```

- Judge **every** pooled candidate exactly once, with `source: "pool"`.
- The rationale is one sentence saying what the provision does in relation to the intent. Do not quote long passages.
- Then run `python3 scripts/merge_judgments.py check --judge <X> --batch <NN>` and fix every problem it reports until it prints `OK`.

## Independence

Do not read other judges' output files, the `data/benchmark/pools/` file, or run the search system on the queries. Your judgment must come from the query, the intent and the text.
