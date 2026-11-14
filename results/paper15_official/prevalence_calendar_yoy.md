# Calendar-definition disagreement on official TPC-DS SF=1 (full population)

This is a **population** statistic, not a task-selection statistic. Every complete
(year, month[, category]) triple with a complete prior-year window in 1999–2002 is counted.
The v0.1 fixture preferentially *selected* the sign-disagreement triples for the
diagnostic tasks; reporting only those would overstate how often a sign flips.

Gate: opposite signs and both |YoY| ≥ 1% (1 percentage point). Magnitude
disagreement: |calendar YoY − rolling-30 YoY| ≥ 2 percentage points, with |calendar YoY| ≥ 1 pp.

| Scope | n complete | Sign disagreement | Rate | Magnitude gap ≥ 2 pp | Rate | Sign rate among decision-relevant |
|---|---:|---:|---:|---:|---:|---:|
| All stores (month) | 48 | 1 | 2.08% | 3 | 6.25% | 2.50% |
| Category-month | 480 | 2 | 0.42% | 42 | 8.75% | 0.47% |
| All triples | 528 | 3 | 0.57% | 45 | 8.52% | 0.64% |

**Reading.** Sign flips are *real* and *rare* (3 of 528 complete triples, 0.57%).
All three already appear in the v0.1 diagnostic fixture; there is **no leftover sign-flip
triple** for a paper-15 held-out. Magnitude disagreement is more common (45 triples, 8.52%).
The scientific claim is therefore: when two legitimate window definitions disagree in
*sign*, a silent choice can reverse a management conclusion — and this happens on official
TPC-DS data — but a benchmark that reported only the flagship flips would be selection-biased.
The paper-15 official held-out is therefore drawn from leftover *same-sign* magnitude and
ordinary complete months (hash-selected, pre-registered), and the population rates above
are a first-class result.

### The three flagship sign flips (existence proof; both |YoY| ≥ 1 pp)

| Scope | Month | Category | Calendar-month YoY | Rolling-30 YoY | Gap |
|---|---|---|---:|---:|---:|
| all_stores | 2000-02 | all stores | +1.924% | -1.157% | 3.081 pp |
| category | 2000-02 | Sports | +2.675% | -2.016% | 4.691 pp |
| category | 2001-02 | Books | -2.068% | +1.206% | 3.274 pp |

February 2000 is a leap month (29 days vs 28 in 1999), which is one mechanistic reason
the two windows diverge at the all-stores grain.

