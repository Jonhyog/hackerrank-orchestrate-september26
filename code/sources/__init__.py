import csv
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from sources.records import (
    FinancialEvent,
    Image,
    Message,
    PaymentOption,
    Request,
    UserProfile,
)

T = TypeVar("T")

__all__ = [
    "FinancialEvent",
    "Image",
    "Message",
    "PaymentOption",
    "Request",
    "UserProfile",
    "World",
    "load_world",
]


@dataclass(frozen=True)
class World:
    requests: tuple[Request, ...]
    profiles: tuple[UserProfile, ...] = ()
    events: tuple[FinancialEvent, ...] = ()
    messages: tuple[Message, ...] = ()
    images: tuple[Image, ...] = ()
    payment_options: tuple[PaymentOption, ...] = ()


def load_world(dataset_dir: Path) -> World:
    return World(
        requests=_load_rows(dataset_dir / "requests.csv", _request_from_row),
        profiles=_load_rows(dataset_dir / "financial_profiles.csv", _profile_from_row),
        events=_load_rows(dataset_dir / "financial_events.csv", _event_from_row),
        messages=_load_rows(dataset_dir / "messages.csv", _message_from_row),
        images=_load_rows(dataset_dir / "images.csv", _image_from_row),
        payment_options=_load_rows(
            dataset_dir / "request_payment_options.csv",
            _option_from_row,
        ),
    )


def _load_rows(path: Path, factory: Callable[[dict[str, str]], T]) -> tuple[T, ...]:
    with path.open(newline="", encoding="utf-8") as handle:
        return tuple(factory(row) for row in csv.DictReader(handle))


def _request_from_row(row: dict[str, str]) -> Request:
    return Request(
        request_id=row["request_id"],
        user_id=row["user_id"],
        request_date=row["request_date"],
        request_type=row["request_type"],
        requested_amount=float(row["requested_amount"]),
        desired_completion_date=row["desired_completion_date"],
        allows_partial_payment=row["allows_partial_payment"].strip().lower() == "true",
        request_text=row["request_text"],
    )


def _profile_from_row(row: dict[str, str]) -> UserProfile:
    return UserProfile(
        user_id=row["user_id"],
        home_currency=row["home_currency"],
        current_available_balance=float(row["current_available_balance"]),
        minimum_balance_to_keep=float(row["minimum_balance_to_keep"]),
        financial_priorities=row["financial_priorities"],
        expense_categories_to_protect=row["expense_categories_to_protect"],
        expense_categories_user_is_willing_to_reduce=row[
            "expense_categories_user_is_willing_to_reduce"
        ],
        expense_categories_user_is_willing_to_stop=row[
            "expense_categories_user_is_willing_to_stop"
        ],
        payment_methods_user_will_consider=row["payment_methods_user_will_consider"],
        max_installment_months=row["max_installment_months"],
    )


def _event_from_row(row: dict[str, str]) -> FinancialEvent:
    return FinancialEvent(
        event_id=row["event_id"],
        user_id=row["user_id"],
        event_type=row["event_type"],
        description=row["description"],
        category=row["category"],
        direction=row["direction"],
        amount=row["amount"],
        currency=row["currency"],
        event_date=row["event_date"],
        settlement_date=row["settlement_date"],
        status=row["status"],
        linked_event_id=row["linked_event_id"],
        flexibility=row["flexibility"],
        minimum_allowed_amount=row["minimum_allowed_amount"],
    )


def _message_from_row(row: dict[str, str]) -> Message:
    return Message(
        message_id=row["message_id"],
        user_id=row["user_id"],
        request_id=row["request_id"],
        related_event_id=row["related_event_id"],
        sent_at=row["sent_at"],
        source_type=row["source_type"],
        message_text=row["message_text"],
    )


def _image_from_row(row: dict[str, str]) -> Image:
    return Image(
        image_id=row["image_id"],
        user_id=row["user_id"],
        request_id=row["request_id"],
        related_event_id=row["related_event_id"],
    )


def _option_from_row(row: dict[str, str]) -> PaymentOption:
    return PaymentOption(
        payment_option_id=row["payment_option_id"],
        request_id=row["request_id"],
        payment_method=row["payment_method"],
        payment_amount=float(row["payment_amount"]),
        number_of_payments=int(row["number_of_payments"]),
        first_payment_date=row["first_payment_date"],
        payment_frequency_days=row["payment_frequency_days"],
        financing_fee=float(row["financing_fee"]),
        total_payable_amount=float(row["total_payable_amount"]),
    )
