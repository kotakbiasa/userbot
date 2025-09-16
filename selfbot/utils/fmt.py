import datetime
import sys
import traceback


def fmtsec(now: datetime.datetime) -> str:
    delta = datetime.datetime.now() - now
    return f"{delta.total_seconds()} s"


def fmtstr(head: str, data: any = None, foot: str = None) -> str:
    body = ""
    if isinstance(data, dict):
        padd = max((len(k) for k in data.keys()), default=0)
        body = "\n".join(
            f"  <code>{k.ljust(padd)}</code> : <code>{v}</code>"
            for k, v in data.items()
        )
    elif isinstance(data, list):
        body = "\n".join(
            f"  <code>{n}</code>. <code>{item}</code>"
            for n, item in enumerate(data, start=1)
        )
    elif data:
        body = f"  {data}"

    text = [f"<b>{head}</b>"]
    if body:
        text.append(body)

    if foot:
        text.append(f"<b>{foot}</b>")

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
