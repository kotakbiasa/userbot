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

pattern = re.compile(r"^(?:r)$")


class Restart(Module):
    name = "Restart"
    cmds = "r"
    desc = "Restart Selfbot"
    file = "/tmp/r.json"

    async def on_started(self) -> None:
        if not os.path.exists(self.file):
            return

        def load() -> dict:
            with open(self.file) as f:
                return json.load(f)

        try:
            data = await asyncio.to_thread(load)
        except Exception:
            return
        else:
            try:
                await self.client.app.delete_messages(*data.values())
            except Exception:
                pass
            finally:
                os.remove(self.file)

    @listener.handler(filters.regex(pattern), 1)
    async def on_message_out(self, event: Message) -> None:
        await event.edit_text("<code>...</code>")

        def fetch(repo, remote) -> None:
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

        def check() -> bool:
            repo = git.Repo(".") if os.path.isdir(".git") else git.Repo.init(".")
            remote = self.client.config.get(
                "remote", "https://github.com/DeltaUniverse/selfbot"
            ).removesuffix(".git")
            branch = self.client.config.get("branch", "staging")
            fetch(repo, remote)
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

        await event.edit_text("<code>Restarting...</code>")

        def dump() -> None:
            with open(self.file, "w") as f:
                json.dump({"cid": event.chat.id, "mid": event.id}, f)

        await asyncio.to_thread(dump)
        os.execv(sys.executable, (sys.executable, "-m", "selfbot"))
