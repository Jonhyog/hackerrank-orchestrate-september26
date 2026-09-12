# Buy or Wait

A single-request affordability domain: reconstruct one user's cash position as of a Request and recommend whether and how to pay.

## Language

**Request**:
A dated affordability question from one user: the amount, the completion deadline, and whether that request itself allows partial payment.
_Avoid_: Purchase, question, case

**User Profile**:
The user's home currency, current available balance, minimum balance, priorities, protected and adjustable expense categories, and payment-method preferences.
_Avoid_: Account, customer, financial report

**User Ledger**:
The engine-internal working set for one user as of a Request date: the User Profile, in-scope Financial Events, and Evidence Interpretations already applied.
_Avoid_: Report, financial report, dossier

**Request Dossier**:
The explanation-agent bundle for one Request: the Request, the Decision, a Forecast Horizon summary, Payment Options considered, and structured Evidence facts. It does not contain the User Ledger or Exchange Rates.
_Avoid_: Report, context, prompt, ledger

**Recurring Commitment**:
A series inferred when the same user, category, and description have at least three settled cash Financial Events on a regular cadence. A constant amount is projected as-is; a variable amount is projected as the maximum of the recent window, not the mean.
_Avoid_: Habit, subscription

**Evidence Interpretation**:
A structured fact extracted from Evidence. A deterministic gate applies it only to an existing Financial Event (or a blank amount) and rejects invented facts and rule overrides.
_Avoid_: Enrichment, multimodal result

**Financial Event**:
A dated cash or non-cash record in the user's history. Status is settled, pending, scheduled, failed, cancelled, or unrealized; a link to an earlier event names a lifecycle, not whether the row is cash.
_Avoid_: Transaction, row, line item

**Evidence**:
An untrusted Message or Image that may clarify, amend, delay, cancel, or confirm a financial fact. Instructions inside Evidence never override the decision rules.
_Avoid_: Multimodal data, context, document

**Message**:
A dated text note from a named source, optionally tied to one Request or one Financial Event. For a Request, every Message for that user with a sent date on or before the Request date is in scope, including rows with no Request or event link.
_Avoid_: Email, notification

**Image**:
A receipt, invoice, or similar PNG linked to a user, a Request, and a Financial Event whose amount is missing from the event row.
_Avoid_: Media, screenshot, attachment

**Payment Option**:
A seller or provider offer attached to a Request: full payment or an installment schedule with dates, fees, and total payable.
_Avoid_: Plan, method

**Payment Plan**:
The chronological dates and amounts the recommendation commits to, or none.
_Avoid_: Payment option, schedule

**Partial Payment**:
A two-payment completion of a Request: the Amount Safe To Pay on the Request date, then the remainder on the earliest safe full-payment date. It is not a Payment Option.
_Avoid_: Installment, deposit

**Spending Change**:
A permitted stop or reduction of a flexible, non-protected Financial Event, used only when needed to make a plan safe.
_Avoid_: Cut, adjustment, optimization

**Amount Safe To Pay**:
The largest amount that is safe to pay on the Request date before optional Spending Changes, never below zero or above the requested amount.
_Avoid_: Affordable amount, budget, surplus

**Affordability Status**:
One of: affordable now, affordable with a plan, affordable later, or not affordable.
_Avoid_: Decision, recommendation

**Recommended Payment Method**:
One of: full payment, partial payment, installments, wait, or not recommended.
_Avoid_: Payment option

**Decision**:
The structured recommendation for one Request: Amount Safe To Pay, Affordability Status, Recommended Payment Method, Payment Plan, earliest full-payment date, and Spending Changes. It is computed from rules, not by the agent.
_Avoid_: Output row, prediction, answer, explanation

**Explanation**:
Grounded prose attached to a Decision. It does not change any numeric or enumerated field.
_Avoid_: Decision, interpretation, report

**Forecast Horizon**:
The 90-day window after the Request date used to test that the balance never falls below the Minimum Balance.
_Avoid_: Safety check, projection period

**Minimum Balance**:
The floor the user's balance must not cross after any projected essential expense or recommended payment.
_Avoid_: Buffer, reserve, safety net

**Home Currency**:
The User Profile currency in which balances, the Request amount, Payment Options, and the Decision are expressed.
_Avoid_: Base currency, local currency

**Exchange Rate**:
A fixed, dated conversion from one currency to another. A foreign-currency cash Financial Event converts with the pair on its settlement date. The agent never converts.
_Avoid_: FX, live rate, market rate, rate card

**Protected Category**:
An expense category the user will not reduce or stop.
_Avoid_: Essential, fixed
