import asyncio
import json
import os
import re
import sys

import git
from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module

pattern = re.compile(r"^r$")


class Restart(Module):
    name = "Restart"

    cmds = "r"
    desc = "Update and Restart System"

    file = "/tmp/r.json"

    async def on_starting(self) -> None:
        if not os.path.exists(self.file):
            return

        try:
            with open(self.file) as f:
                data = json.load(f)
                chat_id = data["chat_id"]
                message_id = data["message_id"]
        except Exception:
            return
        else:
            try:
                await self.client.edit_message_text(
                    chat_id, message_id, "<code>Selfbot Restarted</code>"
                )
            except Exception:
                pass
            finally:
                os.remove(self.file)

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await event.edit("<code>Resetting...</code>")

        def ensure(repo, remote):
            origin = next((r for r in repo.remotes if r.name == "origin"), None)
            if origin is None:
                origin = repo.create_remote("origin", remote)
            else:
                try:
                    if getattr(origin, "url", None) != remote:
                        origin.set_url(remote)
                except Exception:
                    origin.set_url(remote)

            origin.fetch(prune=True)

        def check():
            repo = git.Repo(".") if os.path.isdir(".git") else git.Repo.init(".")
            remote_url = self.client.config.get(
                "remote", "https://github.com/DeltaUniverse/selfbot"
            ).removesuffix(".git")
            branch = self.client.config.get("branch", "staging")

            ensure(repo, remote_url)
            repo.git.reset("--hard", f"origin/{branch}")

            old = repo.head.commit.hexsha
            new = repo.commit(f"origin/{branch}").hexsha

            if old == new:
                return False

            deps = {"requirements.txt", "pyproject.toml", "poetry.lock"}
            for diff in repo.commit(old).diff(new):
                if (diff.a_path or "").lower() in deps or (
                    diff.b_path or ""
                ).lower() in deps:
                    return True

            return False

        changed = await asyncio.to_thread(check)

        if changed:
            await event.edit("<code>Update Deps...</code>")

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

        await event.edit("<code>Restarting...</code>")
        with open(self.file, "w") as f:
            json.dump({"chat_id": event.chat.id, "message_id": event.id}, f)

        os.execv(sys.executable, (sys.executable, "-m", "selfbot"))
