from __future__ import annotations

from datetime import date, datetime


def get_current_datetime() -> dict[str, str]:
    current = datetime.now().astimezone()
    return {
        "datetime": current.isoformat(timespec="seconds"),
        "timezone": str(current.tzinfo),
    }


def get_current_date() -> dict[str, str]:
    return {"date": date.today().isoformat()}


def get_current_time() -> dict[str, str]:
    return {"time": datetime.now().astimezone().time().isoformat(timespec="seconds")}


def calculate_date_difference(start_date: str, end_date: str) -> dict[str, object]:
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValueError("Dates must use the ISO format YYYY-MM-DD.") from exc
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "days": (end - start).days,
    }
