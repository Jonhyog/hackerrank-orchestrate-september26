def calendar_date(value: str) -> str | None:
    if len(value) < 10:
        return None
    return value[:10]
