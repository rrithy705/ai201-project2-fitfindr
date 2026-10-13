# Scored run log — before-probe

- Produced by: `score_eval.py` wrapping `run_eval.py::main`
- When: 2026-10-13 19:23

| Criterion | Target | Try 1 | Try 2 | Try 3 | Try 4 | Try 5 | Verdict |
|---|---|---|---|---|---|---|---|

## Diagnostic probes (not criteria)

| Probe | Query | Try 1 | Try 2 | Try 3 | Try 4 | Try 5 | Verdict |
|---|---|---|---|---|---|---|---|
| probe: colour word vs item type | `black boots` | FAIL | FAIL | FAIL | FAIL | FAIL | 0/5 |
| probe: material word vs item type | `leather jacket under $45` | FAIL | FAIL | FAIL | FAIL | FAIL | 0/5 |
| probe: impossible item with a common colour | `black ballgown` | FAIL | FAIL | FAIL | FAIL | FAIL | 0/5 |

## Why each try passed or failed

**probe: colour word vs item type** — query `black boots`
- Try 1: FAIL — picked Biker Shorts — Black, Shiny ($14) — not boots
- Try 2: FAIL — picked Biker Shorts — Black, Shiny ($14) — not boots
- Try 3: FAIL — picked Biker Shorts — Black, Shiny ($14) — not boots
- Try 4: FAIL — picked Biker Shorts — Black, Shiny ($14) — not boots
- Try 5: FAIL — picked Biker Shorts — Black, Shiny ($14) — not boots

**probe: material word vs item type** — query `leather jacket under $45`
- Try 1: FAIL — picked Leather Belt — Brown, Braided ($12) — not jacket
- Try 2: FAIL — picked Leather Belt — Brown, Braided ($12) — not jacket
- Try 3: FAIL — picked Leather Belt — Brown, Braided ($12) — not jacket
- Try 4: FAIL — picked Leather Belt — Brown, Braided ($12) — not jacket
- Try 5: FAIL — picked Leather Belt — Brown, Braided ($12) — not jacket

**probe: impossible item with a common colour** — query `black ballgown`
- Try 1: FAIL — picked Biker Shorts — Black, Shiny ($14) — not ballgown
- Try 2: FAIL — picked Biker Shorts — Black, Shiny ($14) — not ballgown
- Try 3: FAIL — picked Biker Shorts — Black, Shiny ($14) — not ballgown
- Try 4: FAIL — picked Biker Shorts — Black, Shiny ($14) — not ballgown
- Try 5: FAIL — picked Biker Shorts — Black, Shiny ($14) — not ballgown
