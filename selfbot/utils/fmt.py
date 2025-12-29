import datetime
import html
import sys
import traceback


def fmtbar(
    current: int,
    total: int,
    bars: int = 8,
    empty: str = chr(9633),
    fill: str = chr(9635),
) -> str:
    fillbar = round(current / total * bars)
    percent = f"{(current / total * 100):.2f}".rstrip("0").rstrip(".")
    return f"[ {fill * fillbar + empty * (bars - fillbar)} ] {percent}%"


def fmtbyte(byte: int, si: bool = False) -> str:
    if si:
        units = (
            ("TB", 1000**4),
            ("GB", 1000**3),
            ("MB", 1000**2),
            ("KB", 1000),
            ("B", 1),
        )
    else:
        units = (
            ("TiB", 1024**4),
            ("GiB", 1024**3),
            ("MiB", 1024**2),
            ("KiB", 1024),
            ("B", 1),
        )

    for unit, factor in units:
        if byte >= factor:
            value = f"{(byte / factor):.2f}".rstrip("0").rstrip(".")
            return f"{value} {unit}"

    return "-"


def fmtexc() -> str:
    exc = traceback.TracebackException(*sys.exc_info())
    fmt = exc.exc_type.__name__
    if exc._str:
        fmt += f":\n  {exc._str}"

    ftb = traceback.format_list(f for f in exc.stack if "/site-packages/" in f.filename)
    if ftb:
        fmt += f"\n\nTraceback:\n{''.join(ftb)}"

    return fmt


def fmtmsg(head: str, data: object = None, foot: str = "", msgs: str = "") -> str:
    body = ""
    if isinstance(data, dict):
        padd = max((len(str(k)) for k in data.keys()), default=0)
        body = "\n".join(
            f"  <code>{html.escape(str(k)).ljust(padd)}</code> : <code>{html.escape(str(v))}</code>"
            for k, v in data.items()
        )
    elif isinstance(data, (list, set, tuple)):
        body = "\n".join(
            f"  <code>{n}</code>. <code>{html.escape(str(item))}</code>"
            for n, item in enumerate(data, start=1)
        )
    elif data:
        body = f"  <code>{html.escape(str(data))}</code>"

    text = [f"<b>{head}</b>"]
    if body:
        text.append(body)

    if msgs:
        text.append(f"<blockquote expandable>{html.escape(str(msgs))}</blockquote>")

    if foot:
        text.append(f"<b><blockquote>{html.escape(str(foot))}</blockquote></b>")

    return "\n\n".join(text)


def fmtsec(sec: object, part: int = 3, human: bool = False) -> str:
    if isinstance(sec, datetime.timedelta):
        delta = sec
    elif isinstance(sec, datetime.datetime):
        delta = datetime.datetime.now(datetime.UTC) - sec.astimezone(datetime.UTC)
    elif isinstance(sec, (float, int)):
        delta = datetime.timedelta(seconds=sec)
    else:
        raise TypeError

    total = int(delta.total_seconds())
    micro = delta.microseconds
    units = (
        ("Week", 60**2 * 24 * 7),
        ("Day", 60**2 * 24),
        ("Hour", 60**2),
        ("Minute", 60),
        ("Second", 1),
    )
    parts = []
    for unit, second in units:
        value, total = divmod(total, second)
        if value:
            parts.append(f"{value} {unit}{'' if value == 1 else 's'}")

        if len(parts) >= part:
            break

    if len(parts) < part and not human:
        ms, us = divmod(micro, 1000)
        if ms:
            parts.append(f"{ms} ms")

        if us and len(parts) < part:
            parts.append(f"{us} µs")

    return ", ".join(parts) if parts else "-"
