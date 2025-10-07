import asyncio
import datetime
import os
import re
import sys

import git
from pyrogram import filters
from pyrogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    Message,
    ReplyParameters,
)

from selfbot import __version__, listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr, ikm

pattern = re.compile(r"^r(?:\s-f)?$")


class System(Module):
    name = "System"

    cmds = "r (-f)?"
    desc = {
        "r": "Restart Selfbot",
        "-f": "Fetch Upstream",
        "?": "Optional",
        "e.g.": "r -f",
    }

    file = "r.txt"

    async def on_starting(self) -> None:
        self.remote = self.client.config.get(
            "remote", "https://github.com/DeltaUniverse/selfbot"
        ).removesuffix(".git")
        self.branch = self.client.config.get("branch", "staging")
        g_branch, g_short, g_subject, g_full = await asyncio.to_thread(self.gitsync)
        data = await asyncio.to_thread(self.getraw)
        if data:
            inline_id, ts, old_sha, new_sha = data
            kb = self.ikbsha(old_sha, new_sha, g_full)
            await self.client.bot.edit_inline_text(
                inline_id,
                fmtstr(
                    "Selfbot Restarted",
                    {
                        "Version": f"{__version__} - {g_branch or 'N/A'}\n",
                        "Modules": len(self.client.modules),
                        "Handlers": len(self.client.handlers),
                        "Listeners": f"{len(self.client.listeners)}",
                    },
                    fmtsec(datetime.datetime.fromtimestamp(float(ts))),
                    g_subject[:512] if g_subject else "N/A",
                ),
                reply_markup=kb,
            )

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        res = await event._client.get_inline_bot_results(
            self.client.bot.me.id, event.content
        )
        await asyncio.gather(
            event.reply_inline_bot_result(
                res.query_id,
                res.results[0].id,
                reply_parameters=ReplyParameters(
                    message_id=event.reply_to_message_id or event.id
                ),
            ),
            event.delete(True),
        )

    @listener.handler(filters.regex(pattern), 2)
    async def on_inline_query(self, event: InlineQuery) -> None:
        await event.answer(
            [
                InlineQueryResultCachedSticker(
                    sticker_file_id=self.client.config["sticker_file_id"],
                    reply_markup=ikm((">_", "user_id", event._client.me.id)),
                    input_message_content=InputTextMessageContent("<code>...</code>"),
                )
            ],
            cache_time=0,
        )

    @listener.handler(filters.regex(pattern), 3)
    async def on_inline_result(self, event: ChosenInlineResult) -> None:
        if getattr(self.client, "restart", False) or os.path.exists(self.file):
            return await event.edit_message_text(
                "<code>Restart is Called</code>", reply_markup=ikm(("Close", b"0"))
            )

        setattr(self.client, "restart", True)

        persisted_old = None
        persisted_new = None

        if event.query.endswith("-f"):
            await event.edit_message_text("<code>Checking Upstream...</code>")

            def fetch_detect():
                repo = git.Repo(".") if os.path.isdir(".git") else git.Repo.init(".")
                origin = next((r for r in repo.remotes if r.name == "origin"), None)
                if origin is None:
                    origin = repo.create_remote("origin", self.remote)
                else:
                    try:
                        if getattr(origin, "url", None) != self.remote:
                            origin.set_url(self.remote)
                    except Exception:
                        origin.set_url(self.remote)

                origin.fetch(prune=True)
                try:
                    old_sha = repo.head.commit.hexsha
                except Exception:
                    old_sha = None

                try:
                    new_sha = repo.commit(f"origin/{self.branch}").hexsha
                except Exception:
                    return False, old_sha, None

                deps_changed = False
                if old_sha:
                    dep = {"requirements.txt", "pyproject.toml", "poetry.lock"}
                    try:
                        for d in repo.commit(old_sha).diff(new_sha):
                            a = (d.a_path or "").lower()
                            b = (d.b_path or "").lower()
                            if a in dep or b in dep:
                                deps_changed = True
                                break
                    except Exception:
                        deps_changed = True

                return deps_changed, old_sha, new_sha

            deps_changed, old_sha, new_sha = await asyncio.to_thread(fetch_detect)

            if new_sha and old_sha and new_sha == old_sha:
                await event.edit_message_text("<code>No Updates Found</code>")
                persisted_new = new_sha
            else:
                await event.edit_message_text("<code>Apply Update...</code>")
                persisted_old, persisted_new = old_sha, new_sha

                def reset_apply():
                    repo = (
                        git.Repo(".") if os.path.isdir(".git") else git.Repo.init(".")
                    )
                    origin = next((r for r in repo.remotes if r.name == "origin"), None)
                    if origin is None:
                        origin = repo.create_remote("origin", self.remote)
                    else:
                        try:
                            if getattr(origin, "url", None) != self.remote:
                                origin.set_url(self.remote)
                        except Exception:
                            origin.set_url(self.remote)

                    origin.fetch(prune=True)
                    ref = f"origin/{self.branch}"
                    if self.branch in repo.heads:
                        head = repo.heads[self.branch]
                    else:
                        head = repo.create_head(self.branch, ref)

                    try:
                        head.set_tracking_branch(repo.remotes.origin.refs[self.branch])
                    except Exception:
                        pass

                    head.checkout(force=True)
                    repo.git.reset("--hard", ref)

                await asyncio.to_thread(reset_apply)

                if deps_changed:
                    await event.edit_message_text(
                        "<code>Dependencies Changed. Updating...</code>"
                    )

                    def pip_update():
                        try:
                            from pip._internal.cli.main import main as pip_main
                        except Exception:
                            return

                        try:
                            pip_main(
                                ["install", "--upgrade", "pip", "setuptools", "wheel"]
                            )
                        except Exception:
                            pass

                        if os.path.exists("requirements.txt"):
                            try:
                                pip_main(["install", "-r", "requirements.txt"])
                            except Exception:
                                pass
                        elif os.path.exists("pyproject.toml"):
                            try:
                                pip_main(["install", "."])
                            except Exception:
                                pass

                    await asyncio.to_thread(pip_update)
                else:
                    await event.edit_message_text("<code>Dependencies Unchanged</code>")

        lines = [f"{event.inline_message_id}", f"{datetime.datetime.now().timestamp()}"]
        if persisted_old:
            lines.append(persisted_old)

        if persisted_new:
            lines.append(persisted_new)

        await asyncio.gather(
            event.edit_message_text("<code>Restarting...</code>"),
            asyncio.to_thread(self.putraw, "\n".join(lines)),
        )
        try:
            self.client.__event__.set()
        finally:
            os.execv(sys.executable, (sys.executable, "-m", "selfbot"))

    def getraw(self) -> tuple[str, float, str | None, str | None] | None:
        if not os.path.exists(self.file):
            return None

        with open(self.file) as f:
            try:
                lines = [ln.strip() for ln in f.readlines()]
                inline_id = lines[0]
                ts = float(lines[1]) if len(lines) > 1 else 0.0
                old_sha = lines[2] if len(lines) > 2 and lines[2] else None
                new_sha = lines[3] if len(lines) > 3 and lines[3] else None
                return inline_id, ts, old_sha, new_sha
            finally:
                try:
                    os.remove(self.file)
                except Exception:
                    pass

    def putraw(self, text: str) -> None:
        with open(self.file, "w") as f:
            f.write(text)

    def gitsync(self) -> tuple[str, str, str, str]:
        try:
            repo = git.Repo(".")
        except Exception:
            return ("N/A", "N/A", "N/A", "")

        try:
            branch = repo.active_branch.name
        except Exception:
            branch = "detached"

        try:
            c = repo.head.commit
            return (
                branch,
                c.hexsha[:7],
                (c.message.splitlines()[0] or "").strip(),
                c.hexsha,
            )
        except Exception:
            return branch, "N/A", "N/A", ""

    def ikbsha(self, old_sha: str | None, new_sha: str | None, head_sha: str | None):
        if old_sha and new_sha and old_sha != new_sha:
            txt = f"{old_sha[:7]}..{new_sha[:7]}"
            url = f"{self.remote}/compare/{old_sha}...{new_sha}"
        else:
            hs = (new_sha or head_sha) or ""
            txt = hs[:7] if hs else "N/A"
            url = f"{self.remote}/commit/{hs}" if hs else self.remote

        return ikm([[(txt, "url", url)], [("Close", b"0")]])
