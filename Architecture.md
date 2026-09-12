# Architecture

Staged DAG for Buy or Wait. Terms live in [`CONTEXT.md`](CONTEXT.md). Why this shape: [ADR 0001](docs/adr/0001-cursor-sdk-for-evidence-and-explanation.md), [ADR 0002](docs/adr/0002-staged-dag-ledger-and-dossier.md). Spec: [#1](https://github.com/Jonhyog/hackerrank-orchestrate-september26/issues/1).

The engine owns the Decision. Agents own Evidence Interpretation and Explanation. The Writer persists the splice.

## Objects

| Object | Owner | Contains |
|---|---|---|
| **World** | Sources | All `dataset/` tables plus the Exchange Rate book, loaded once |
| **User Ledger** | Engine | One user's User Profile, in-scope Financial Events, applied Evidence Interpretations |
| **Request Dossier** | Explanation sandbox | Request, Decision, Forecast Horizon summary, Payment Options considered, structured Evidence facts |
| **Decision** | Engine | Amount Safe To Pay, Affordability Status, Recommended Payment Method, Payment Plan, earliest full-payment date, Spending Changes |
| **Explanation** | Explanation agent | Prose only |

The User Ledger stays in the engine. The Request Dossier never contains the User Ledger or Exchange Rates.

## DAG

```text
CSV sources ─┬─► Exchange Rate book (process-wide, engine only)
             │
             └─► per-Request slice
                      │
                      ├─► Image agent?  ─┐
                      ├─► Message agent? ─┼─► apply gate ─► User Ledger
                      └─► profile/events ─┘         │
                                                    ▼
                              Recurring Commitments + Forecast Horizon
                                                    │
                                                    ▼
                                         plan rank → Decision
                                                    │
                                                    ▼
                                         Request Dossier
                                                    │
                                                    ▼
                                         Explanation agent
                                                    │
                                                    ▼
                         Writer (engine Decision + Explanation text)
```

Sources and the Writer are ends, not pipes. Image and Message stages are skipped when that Request has no such Evidence. Explanation always runs.

## Module map

Import root is `code/`. There is no challenge-named package. Each stage is a package (several files). Utils holds primitives only (dates, money, CSV, paths).

```text
code/
  main.py                 # CLI: run evaluation Requests; --output <path>
  config/                 # env: CURSOR_API_KEY, model, dataset/output/sandbox paths
  utils/
  sources/                # load World once
  exchange_rates/         # settlement-date pair book
  slice/                  # per-Request user slice (Q7 cash as-of + Message/Image scope)
  evidence/               # schemas, apply gate, unknown-debit reserve
  ledger/                 # Recurring Commitments, forecast, Amount Safe To Pay
  decision/               # eligibility, rank, Spending Changes
  dossier/                # Request Dossier
  agents/                 # SDK prompt, sandbox cwd, image / message / explain
  writer/                 # submission table
  evaluation/             # usage report for the final full run
```

`solve(world, request, ports) → output row` is the orchestrator. Injected ports replace Cursor SDK in tests.

## Slice and cash as-of

For one Request the slice is: that User Profile, that user's Financial Events, in-scope Messages, Image if any, that Request's Payment Options.

Messages in scope: every Message for that `user_id` with sent date on or before the Request date, including rows with no Request or event link.

User Ledger cash: history on or before the Request date, plus recorded scheduled and pending rows. Reserve pending debits. Ignore pending credits, cancelled, failed, and unrealized. Count confirmed salary on settlement date. Convert foreign-currency cash Financial Events with the Exchange Rate on the settlement date. The agent never converts.

## Evidence

Image sandbox: the PNG and the blank-amount Financial Event.

Message sandbox: in-scope Messages plus candidate Financial Events (id, dates, amounts, descriptions, status).

Apply gate: fill a blank amount, or cancel / delay / confirm / amend an **existing** Financial Event. Reject invented income, new events, and rule overrides. Then the spec conflict order.

Failure: retry once; if still unusable, leave the amount unknown; reserve an unknown debit (never treat a blank amount as zero).

## Recurrence and Decision

Recurring Commitment: same user + category + description, ≥3 settled cash Financial Events, regular cadence. Constant amount projects as-is. Variable amount projects the maximum of the recent window.

Amount Safe To Pay and earliest full-payment date are computed **before** optional Spending Changes. Forecast Horizon is 90 days. Balance stays at or above the Minimum Balance.

Eligibility, Partial Payment two-step rule, installment match, Spending Changes, and ranking follow [`problem_statement.md`](problem_statement.md).

## Agents (Cursor SDK)

Every agent call is `Agent.prompt`, local runtime, `cwd` = that stage's sandbox.

Image, Message, and Explanation never share an agent. Sandbox is never the repository root.

Writer takes Decision fields from the engine and `decision_explanation` from the Explanation agent. Extra numbers in agent output are discarded.

## CLI

Default write path is repository-root `output.csv` (the submission file).

`--output <path>` writes the same table elsewhere so a development run does not overwrite the submission file.

Secrets come from the environment via Config (`CURSOR_API_KEY` and related settings).

## Test seam

One seam: `solve`. Inputs: loaded World, one Request, injected Image / Message / Explanation ports. Output: one submission row.

Tests assert that row (and sandbox contents when isolation is the claim). Unit tests do not call the Cursor SDK.

## Ticket map

Frontier is the runnable stub. Parent spec is #1.

| Issue | Slice |
|---|---|
| [#2](https://github.com/Jonhyog/hackerrank-orchestrate-september26/issues/2) | Stub `solve` + `--output` |
| [#3](https://github.com/Jonhyog/hackerrank-orchestrate-september26/issues/3) | Slice isolation |
| [#4](https://github.com/Jonhyog/hackerrank-orchestrate-september26/issues/4) | Settlement-date Exchange Rate |
| [#5](https://github.com/Jonhyog/hackerrank-orchestrate-september26/issues/5) | Evidence apply gate (injected ports) |
| [#6](https://github.com/Jonhyog/hackerrank-orchestrate-september26/issues/6) | Amount Safe To Pay + earliest full-payment date |
| [#7](https://github.com/Jonhyog/hackerrank-orchestrate-september26/issues/7) | Full Decision ranking |
| [#8](https://github.com/Jonhyog/hackerrank-orchestrate-september26/issues/8) | SDK Evidence adapters |
| [#9](https://github.com/Jonhyog/hackerrank-orchestrate-september26/issues/9) | Explanation + Writer splice |
| [#10](https://github.com/Jonhyog/hackerrank-orchestrate-september26/issues/10) | Full evaluation run + usage report |
