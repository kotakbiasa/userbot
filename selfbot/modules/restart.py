import asyncio
import os
import re
import sys

import git
from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module

pattern = re.compile(r"^r(?:estart)?$")


class Restart(Module):
    name = "Restart"
    cmds = "r(estart)?"
    desc = {"?": "Optional", "e.g": "restart"}

    @listener.handler(filters.regex(pattern) & ~listener.fltrep, 1)
    async def on_message_out(self, event: Message) -> None:
        await event.edit_text("<code>...</code>")

        def fetch(repo, remote) -> None:
            origin = next((r for r in repo.remotes if r.name == "origin"), None)
            if not origin:
                origin = repo.create_remote("origin", remote)
            else:
                try:
                    if getattr(origin, "url", None) != remote:
                        origin.set_url(remote)
                except Exception:
                    origin.set_url(remote)

            origin.fetch(prune=True)

        def check() -> bool:
            repo = git.Repo(".") if os.path.isdir(".git") else git.Repo.init(".")
            remote, branch = self.client.config.get(
                "remote", "https://github.com/kotakbiasa/userbot"
            ).removesuffix(".git"), self.client.config.get("branch", "staging")
            fetch(repo, remote)
            repo.git.reset("--hard", f"origin/{branch}")
            old, new = repo.head.commit.hexsha, repo.commit(f"origin/{branch}").hexsha
            if old == new:
                return False

            deps = {"requirements.txt", "pyproject.toml", "poetry.lock"}
            for diff in repo.commit(old).diff(new):
                if (diff.a_path or "").lower() in deps or (
                    diff.b_path or ""
                ).lower() in deps:
                    return True

            return False

        if await asyncio.to_thread(check):
            await event.edit_text("<code>Updating...</code>")

            def update():
                try:
                    from pip._internal.cli.main import main as pip

                    pip(["install", "--upgrade", "pip", "setuptools", "wheel"])
                    if os.path.exists("requirements.txt"):
                        pip(["install", "-r", "requirements.txt"])
                    elif os.path.exists("pyproject.toml"):
                        pip(["install", "."])
                except Exception:
                    pass

            await asyncio.to_thread(update)

        await asyncio.gather(
            event.edit_text("<code>Restarting...</code>"),
            self.client.db.execute(
                "INSERT INTO restart.msg (chat_id, message_id) VALUES ($1, $2);",
                event.chat.id,
                event.id,
            ),
        )
        os.execv(sys.executable, (sys.executable, "-m", "selfbot"))
