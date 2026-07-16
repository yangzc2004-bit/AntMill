# AntMill Memory-Paper Path Isolation

Status: established on 2026-07-15 after the shared
`antmill_aaai27_en.*` entry point was reused by a separate MoA manuscript.

The memory paper now uses only these isolated source entry points:

- `antmill_memory_aaai27_en.tex`
- `antmill_memory_aaai27_supp.tex`
- `antmill_memory.bib`
- `antmill_memory_reproducibility_checklist.tex`
- `../reproducibility_checklist_responses_memory.json`

Memory-paper scripts, audits, and final compilation must not read or write
`antmill_aaai27_en.*`, `antmill_aaai27_supp.*`, `antmill.bib`, or
`antmill_reproducibility_checklist.*`.

## Recovery Record

The main source was reconstructed from the active Goal session log, using the
last complete pre-overwrite source snapshot and replaying all 13 successful
patch events before `2026-07-15T05:12:17Z`. The recovered source was checked
against later logged line-range reads.

The isolated pre-integration build produced seven pages and 409,796 bytes,
matching the last verified pre-overwrite PDF byte count exactly. Automated
render checks passed and all seven rendered pages were visually inspected.

Baseline SHA-256 values:

- main TeX:
  `977e8de075816e36df58ebdef538c34173314a5ce006245e347297da3321ca70`
- main PDF:
  `20318d8a985eb011a41f6bc80c96ebe39312b43ff1b4af6af9e8a8fc8894d30d`
- supplement TeX:
  `8d0ecf2bdc3761d905ca94bc64aaec1d6063bdc2cf3e3a734d59243dbac37849`
- bibliography:
  `44d2913fc654b6aa82df68e411b91af2242910ec77b9d24957c4ba8af23936b7`
- checklist responses:
  `bf54e6d0590a6fbeda276d7b62479f0eb07403817c8b8f8822d15739473ebb28`

These are recovery-baseline hashes, not final-submission hashes. Final
evidence integration will intentionally change the manuscript and PDF.
