from dataclasses import dataclass

from utils.currency import Currency


@dataclass(frozen=True)
class Request:
    request_id: str
    user_id: str
    request_date: str
    request_type: str
    requested_amount: float
    desired_completion_date: str
    allows_partial_payment: bool
    request_text: str


@dataclass(frozen=True)
class UserProfile:
    user_id: str
    home_currency: Currency
    current_available_balance: float
    minimum_balance_to_keep: float
    financial_priorities: str
    expense_categories_to_protect: str
    expense_categories_user_is_willing_to_reduce: str
    expense_categories_user_is_willing_to_stop: str
    payment_methods_user_will_consider: str
    max_installment_months: str


@dataclass(frozen=True)
class FinancialEvent:
    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: str
    amount: str
    currency: Currency
    event_date: str
    settlement_date: str
    status: str
    linked_event_id: str
    flexibility: str
    minimum_allowed_amount: str


@dataclass(frozen=True)
class ExchangeRate:
    rate_date: str
    from_currency: Currency
    to_currency: Currency
    rate: str


@dataclass(frozen=True)
class Message:
    message_id: str
    user_id: str
    request_id: str
    related_event_id: str
    sent_at: str
    source_type: str
    message_text: str


@dataclass(frozen=True)
class Image:
    image_id: str
    user_id: str
    request_id: str
    related_event_id: str


@dataclass(frozen=True)
class PaymentOption:
    payment_option_id: str
    request_id: str
    payment_method: str
    payment_amount: float
    number_of_payments: int
    first_payment_date: str
    payment_frequency_days: str
    financing_fee: float
    total_payable_amount: float
