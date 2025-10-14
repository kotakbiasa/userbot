import datetime
import html
import sys
import traceback


def fmtsec(now: datetime.datetime, part: int = 3) -> str:
    delta = datetime.datetime.now() - now
    total = int(delta.total_seconds())
    micro = delta.microseconds

    parts = []

    w, r = divmod(total, 7 * 24 * 3600)
    if w:
        parts.append(f"{w} Week{'s' if w != 1 else ''}")

    d, r = divmod(r, 24 * 3600)
    if d:
        parts.append(f"{d} Day{'s' if d != 1 else ''}")

    h, r = divmod(r, 3600)
    if h:
        parts.append(f"{h} Hour{'s' if h != 1 else ''}")

    m, r = divmod(r, 60)
    if m:
        parts.append(f"{m} Minute{'s' if m != 1 else ''}")

    s = r
    if s:
        parts.append(f"{s} Second{'s' if s != 1 else ''}")

    ms, µs = divmod(micro, 1000)
    if ms:
        parts.append(f"{ms} ms")

    if µs:
        parts.append(f"{µs} µs")

    return ", ".join(parts[:part]) if parts else "0 µs"


def fmtstr(
    head: str, data: any = None, foot: str = None, msgs: str = None, ext: str = None
) -> str:
    body = ""
    if isinstance(data, dict):
        padd = max((len(str(k)) for k in data.keys()), default=0)
        body = "\n".join(
            f"  <code>{html.escape(str(k)).ljust(padd)}</code> : <code>{html.escape(str(v))}</code>"
            for k, v in data.items()
        )
    elif isinstance(data, list):
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
        text.append(f"<b>{html.escape(str(foot))}</b>")

    if ext:
        text.append(f"<b><blockquote>{ext}</blockquote></b>")

    return "\n\n".join(text)


def fmtexc() -> str:
    exc = traceback.TracebackException(*sys.exc_info())
    fmt = exc.exc_type.__name__
    if exc._str:
        fmt += f":\n  {exc._str}"

    ftb = traceback.format_list(
        [frame for frame in exc.stack if "/site-packages/" in frame.filename]
    )
    if ftb:
        fmt += f"\n\nTraceback:\n{''.join(ftb)}"

    return fmt
