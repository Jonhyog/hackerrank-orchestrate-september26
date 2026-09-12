from dataclasses import replace

from sources import FinancialEvent


def reserve_unknown_debits(
    events: tuple[FinancialEvent, ...],
) -> tuple[FinancialEvent, ...]:
    return tuple(_keep_unknown_debit(event) for event in events)


def _keep_unknown_debit(event: FinancialEvent) -> FinancialEvent:
    if event.direction != "debit" or event.amount.strip() != "":
        return event
    return replace(event, amount="")
