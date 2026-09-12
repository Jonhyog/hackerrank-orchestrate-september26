from dataclasses import dataclass, replace
from decimal import Decimal

from sources import ExchangeRate, FinancialEvent
from utils.currency import Currency

_CASH_DIRECTIONS = frozenset({"debit", "credit"})


@dataclass(frozen=True)
class RateBook:
    rates: tuple[ExchangeRate, ...]

    def convert_cash_events(
        self,
        events: tuple[FinancialEvent, ...],
        home_currency: Currency,
    ) -> tuple[FinancialEvent, ...]:
        return tuple(self._convert_cash_event(event, home_currency) for event in events)

    def _convert_cash_event(
        self,
        event: FinancialEvent,
        home_currency: Currency,
    ) -> FinancialEvent:
        if (
            event.direction not in _CASH_DIRECTIONS
            or not event.amount
            or event.currency == home_currency
        ):
            return event
        rate = self._settlement_rate(
            event.currency, home_currency, event.settlement_date
        )
        if rate is None:
            return event
        return replace(
            event,
            amount=_converted_amount(event.amount, rate),
            currency=home_currency,
        )

    def _settlement_rate(
        self,
        source: Currency,
        target: Currency,
        settlement_date: str,
    ) -> Decimal | None:
        for rate in self.rates:
            if (
                rate.from_currency == source
                and rate.to_currency == target
                and rate.rate_date == settlement_date
            ):
                return Decimal(rate.rate)
        return None


def _converted_amount(amount: str, rate: Decimal) -> str:
    value = Decimal(amount) * rate
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
