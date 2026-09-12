import csv
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from sources import (
    FinancialEvent,
    Image,
    Message,
    PaymentOption,
    Request,
    UserProfile,
    World,
)
from utils.dates import calendar_date


@dataclass(frozen=True)
class RequestSlice:
    request_id: str
    profile: UserProfile | None
    events: tuple[FinancialEvent, ...]
    messages: tuple[Message, ...]
    image: Image | None
    payment_options: tuple[PaymentOption, ...]


def for_request(world: World, request: Request) -> RequestSlice:
    return RequestSlice(
        request_id=request.request_id,
        profile=next(
            (
                profile
                for profile in world.profiles
                if profile.user_id == request.user_id
            ),
            None,
        ),
        events=tuple(
            event for event in world.events if event.user_id == request.user_id
        ),
        messages=tuple(
            message
            for message in world.messages
            if _message_in_scope(message, request)
        ),
        image=next(
            (
                image
                for image in world.images
                if image.request_id == request.request_id
                and image.user_id == request.user_id
            ),
            None,
        ),
        payment_options=tuple(
            option
            for option in world.payment_options
            if option.request_id == request.request_id
        ),
    )


def write_sandbox(request: Request, request_slice: RequestSlice, root: Path) -> Path:
    dest = root / request.request_id
    dest.mkdir(parents=True, exist_ok=True)
    _write_records(
        dest / "financial_profiles.csv",
        UserProfile,
        (request_slice.profile,) if request_slice.profile is not None else (),
    )
    _write_records(dest / "financial_events.csv", FinancialEvent, request_slice.events)
    _write_records(dest / "messages.csv", Message, request_slice.messages)
    _write_records(
        dest / "images.csv",
        Image,
        (request_slice.image,) if request_slice.image is not None else (),
    )
    _write_records(
        dest / "request_payment_options.csv",
        PaymentOption,
        request_slice.payment_options,
    )
    return dest


def _message_in_scope(message: Message, request: Request) -> bool:
    if message.user_id != request.user_id:
        return False
    sent_date = calendar_date(message.sent_at)
    return sent_date is not None and sent_date <= request.request_date


def _write_records(
    path: Path,
    record_type: type[Any],
    rows: tuple[Any, ...],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[field.name for field in fields(record_type)],
        )
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
