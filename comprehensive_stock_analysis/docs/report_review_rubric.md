# Equity note review rubric

Applied to a generated report **as a reader receives it** — the PDF and the HTML,
not the JSON behind them. Every check here exists because a human reviewer caught
something the automated checks did not.

Score each item **pass / fail / n-a**, with the evidence that decided it (a page
number and a quoted figure). A check with no evidence cited is not a pass.

Two rules for whoever runs this:

- **Do the arithmetic.** Most failures found so far were visible with a
  calculator: a margin that did not equal income over revenue, a per-share value
  that did not follow from its own stated inputs, a bull case below its bear
  case. Recompute every ratio the note prints from the other numbers the note
  prints.
- **Read the whole document before judging any part of it.** Several failures
  were contradictions *between* sections — page 5 printing a valuation while
  page 7 said none existed — invisible to anyone checking one section at a time.

---

## A. Identity — the document must agree with itself

| # | Check | Fails when |
|---|---|---|
| A1 | One price, one as-of | The same close appears as two values, or a price is paired with a date that is not its session |
| A2 | One market capitalisation | Cover and comparables table disagree, as rendered |
| A3 | One share count | Per-share figures imply different denominators |
| A4 | Sections do not contradict each other | The appendix denies something the body prints |
| A5 | Figures repeated across sections match | A margin in the financials table differs from the same margin in the forecast basis |

## B. Valuation — the target must be an output, not an assertion

| # | Check | Fails when |
|---|---|---|
| B1 | A valuation model exists and is named | "No model was produced" while a target is published |
| B2 | The target equals the model's output, or names the one assumption changed and what it becomes | The target silently differs from the model |
| B3 | The target is not the Street's number | Within 1% of consensus mean or median with no stated variant |
| B4 | Every valuation input is derived or sourced | An exit multiple or discount rate appears with no build |
| B5 | The arithmetic closes | Recomputing from the stated inputs does not reproduce the printed value |
| B6 | Scenarios are ordered bear < base < bull | Any inversion |
| B7 | The valuation uses the forecast it printed | Forecast cash flows are decorative — they enter no calculation |
| B8 | The target is plausible against the traded price | Orders of magnitude away: a unit, share-class or sign error |

## C. Rating — the call must be checkable

| # | Check | Fails when |
|---|---|---|
| C1 | The rating agrees with the return the target implies | Buy with negative implied return; Hold with a large one |
| C2 | The rating band is defined against a stated number | "Exceeds the market" with no market return given — unfalsifiable |
| C3 | The horizon is stated, and the return annualised over it clears the band | An 18-month horizon flattering a 12-month threshold |
| C4 | Risk level and confidence are defined and used | Scales printed in the appendix and never referenced |
| C5 | Stop-loss is a thesis invalidation, not a moving average | Derived only from technicals on a fundamental call |

## D. Source integrity — figures must match the filings

| # | Check | Fails when |
|---|---|---|
| D1 | Statement figures match the filed accounts | Any line differs from the 10-K |
| D2 | No year repeats another year's value | Two periods identical to the decimal — a data-pull signature |
| D3 | Ratio basis is labelled where bases differ | A TTM multiple beside fiscal-year statements with nothing saying so |
| D4 | Derived ratios reconcile with the printed inputs | Operating margin ≠ operating income ÷ revenue |
| D5 | Growth rates match the figures given | Stated growth differs from what the two revenue lines imply |

## E. Comparables — the set must be defensible

| # | Check | Fails when |
|---|---|---|
| E1 | Peers share the subject's business model | Convenience stores or leather goods against a hyperscaler |
| E2 | Peers are within a defensible size range | Micro-caps against mega-caps |
| E3 | Competitors named in the text appear in the table | The risk section names them; the comps set omits them |
| E4 | No second share class of the subject | Same issuer appearing as its own peer |
| E5 | Multiples are plausible | An outlier implying broken source data |

## F. Substance — the note must be actionable

| # | Check | Fails when |
|---|---|---|
| F1 | An explicit multi-year forecast exists | Drivers described, never measured |
| F2 | Segment economics are quantified | Segments named with no revenue or margin |
| F3 | Triggers are numeric | "Weakened materially" |
| F4 | Risks carry numbers or attach to a model line | Boilerplate paragraphs |
| F5 | A variant versus consensus is stated with both figures | No claim about what the note models that the Street does not |

## G. Artifact — it must read as a document, not output

| # | Check | Fails when |
|---|---|---|
| G1 | No generator artifacts | "Produced by automated analysis", generation timestamps, run bookkeeping |
| G2 | No instruction text | Captions telling the analyst what to do |
| G3 | No pipeline narration | "I cannot cite", "the data package", "in this run" |
| G4 | Figures are rounded for reading | `326.8373` on a dollar price |
| G5 | No duplicated content | The same chart or argument twice |
| G6 | No inline citation markers | `[1]`, footnote digits trailing sentences |
| G7 | Attribution present | Named author, firm, conflicts, certification |
| G8 | Consistent spelling and typography | Mixed conventions, stray soft hyphens |
| G9 | The file opens and extracts cleanly | Text unreadable to a normal extractor |

---

## Verdict

- **Send** — no fails in A–D, at most cosmetic fails elsewhere.
- **Internal draft** — A–D clean, substance or artifact gaps remain.
- **Do not send** — any fail in A, B, C or D.

Report the count of fails by section, the three most damaging with evidence, and
whether any failure is a *regression* against the previous version — a patch that
fixes two checks and breaks four is only visible from the scoreboard.
