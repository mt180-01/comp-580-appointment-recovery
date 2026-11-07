import re


def utc_seconds(value):
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value) is None
    ):
        raise ValueError("Timestamps must use YYYY-MM-DDTHH:MM:SSZ in UTC")
    year, month, day = int(value[:4]), int(value[5:7]), int(value[8:10])
    hour, minute, second = int(value[11:13]), int(value[14:16]), int(value[17:19])
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    months = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if not (
        1 <= year <= 9999
        and 1 <= month <= 12
        and 1 <= day <= months[month - 1]
        and 0 <= hour < 24
        and 0 <= minute < 60
        and 0 <= second < 60
    ):
        raise ValueError("Timestamp has an invalid calendar date or time")
    previous_year = year - 1
    days = 365 * previous_year + previous_year // 4 - previous_year // 100 + previous_year // 400
    days += sum(months[: month - 1]) + day - 1
    return ((days * 24 + hour) * 60 + minute) * 60 + second


def eligible(appointment, slot):
    return (
        slot["service"] == appointment["service"]
        and slot["location"] in appointment["allowed_locations"]
        and slot["start"] >= appointment["earliest_start"]
        and slot["end"] <= appointment["latest_end"]
        and utc_seconds(slot["end"]) - utc_seconds(slot["start"]) >= appointment["duration_minutes"] * 60
    )
