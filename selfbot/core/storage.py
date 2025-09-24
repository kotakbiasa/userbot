import time
from typing import Any, Optional, TypeAlias, Union, cast, overload

import asyncpg
from pyrogram import raw, utils
from pyrogram.storage import Storage

InputPeer: TypeAlias = Union[
    raw.types.InputPeerUser, raw.types.InputPeerChat, raw.types.InputPeerChannel
]

Object = object()

SCHEMA = """
CREATE TABLE IF NOT EXISTS version (
    number  INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS sessions (
    session     TEXT    PRIMARY KEY,
    dc_id       INTEGER NOT NULL,
    api_id      INTEGER,
    test_mode   BOOLEAN,
    auth_key    BYTEA,
    date        BIGINT  NOT NULL,
    user_id     BIGINT,
    is_bot      BOOLEAN
);

CREATE TABLE IF NOT EXISTS peers (
    session         TEXT    NOT NULL,
    id              BIGINT  NOT NULL,
    access_hash     BIGINT,
    type            TEXT    NOT NULL,
    phone_number    TEXT,
    last_update_on  BIGINT  NOT NULL DEFAULT (EXTRACT(epoch FROM now())),
    PRIMARY KEY (session, id)
);

CREATE TABLE IF NOT EXISTS usernames (
    session     TEXT    NOT NULL,
    id          BIGINT  NOT NULL,
    username    TEXT    NOT NULL,
    PRIMARY KEY (session, username),
    FOREIGN KEY (session, id) REFERENCES peers (session, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS update_state (
    session TEXT    NOT NULL,
    id      INTEGER NOT NULL,
    pts     BIGINT,
    qts     BIGINT,
    date    BIGINT,
    seq     BIGINT,
    PRIMARY KEY (session, id)
);

CREATE INDEX IF NOT EXISTS idx_peers_session_id ON peers (session, id);
CREATE INDEX IF NOT EXISTS idx_peers_phone_number ON peers (session, phone_number);
CREATE INDEX IF NOT EXISTS idx_usernames_username ON usernames (session, username);
"""


def get_input_peer(peer_id: int, access_hash: int, peer_type: str) -> InputPeer:
    if peer_type in ("user", "bot"):
        return raw.types.InputPeerUser(user_id=peer_id, access_hash=access_hash)

    if peer_type == "group":
        return raw.types.InputPeerChat(chat_id=-peer_id)

    if peer_type in ("channel", "supergroup"):
        return raw.types.InputPeerChannel(
            channel_id=utils.get_channel_id(peer_id), access_hash=access_hash
        )

    raise ValueError(f"Invalid peer type: {peer_type}")


class PostgresStorage(Storage):
    VERSION: int = 5
    USERNAME_TTL: int = 8 * 60 * 60

    def __init__(self, session: str, pool: asyncpg.Pool) -> None:
        super().__init__(session)
        self.session: str = session
        self.pool: asyncpg.Pool = pool

    @staticmethod
    async def create_schema(pool: asyncpg.Pool) -> None:
        async with pool.acquire() as conn:
            await conn.execute(SCHEMA)
            await conn.execute(
                "INSERT INTO version (number) VALUES ($1) ON CONFLICT DO NOTHING",
                PostgresStorage.VERSION,
            )

    async def open(self) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sessions (session, dc_id, date)
                VALUES ($1, 2, 0)
                ON CONFLICT (session) DO NOTHING
                """,
                self.session,
            )

    async def save(self) -> None:
        await self.date(int(time.time()))

    async def close(self) -> None:
        pass

    async def delete(self) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM peers WHERE session = $1", self.session)
                await conn.execute(
                    "DELETE FROM update_state WHERE session = $1", self.session
                )
                await conn.execute(
                    "DELETE FROM sessions WHERE session = $1", self.session
                )

    async def update_peers(
        self, peers: list[tuple[int, int, str, list[str] | None, str | None]]
    ) -> None:
        if not peers:
            return

        peer_records = []
        username_records = []
        peer_ids_to_update = [p[0] for p in peers]

        for p_id, p_access_hash, p_type, p_usernames, p_phone_number in peers:
            peer_records.append(
                (self.session, p_id, p_access_hash, p_type, p_phone_number)
            )
            if p_usernames:
                for uname in p_usernames:
                    username_records.append((self.session, p_id, uname))

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(
                    """
                    INSERT INTO peers (session, id, access_hash, type, phone_number)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (session, id) DO UPDATE SET
                        access_hash = EXCLUDED.access_hash,
                        type = EXCLUDED.type,
                        phone_number = EXCLUDED.phone_number,
                        last_update_on = EXTRACT(epoch FROM now())
                    """,
                    peer_records,
                )
                await conn.execute(
                    "DELETE FROM usernames WHERE session = $1 AND id = ANY($2::bigint[])",
                    self.session,
                    peer_ids_to_update,
                )
                if username_records:
                    await conn.copy_records_to_table(
                        "usernames",
                        records=username_records,
                        columns=("session", "id", "username"),
                    )

    @overload
    async def update_state(self) -> list[tuple[int, int, int, int, int]]: ...
    @overload
    async def update_state(self, value: tuple[int, ...] | None) -> None: ...
    async def update_state(
        self, value: Any = Object
    ) -> list[tuple[int, int, int, int, int]] | None:
        async with self.pool.acquire() as conn:
            if value is Object:
                rows = await conn.fetch(
                    "SELECT id, pts, qts, date, seq FROM update_state WHERE session = $1",
                    self.session,
                )
                return [cast(tuple, tuple(r)) for r in rows]

            if value is None:
                await conn.execute(
                    "DELETE FROM update_state WHERE session = $1", self.session
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO update_state (session, id, pts, qts, date, seq)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (session, id) DO UPDATE SET
                        pts = EXCLUDED.pts, qts = EXCLUDED.qts,
                        date = EXCLUDED.date, seq = EXCLUDED.seq
                    """,
                    self.session,
                    *value,
                )

            return None

    async def get_peer_by_id(self, peer_id: int | str) -> InputPeer:
        try:
            peer_id_int = int(peer_id)
        except (ValueError, TypeError) as e:
            raise KeyError(f"Invalid peer ID: {peer_id}") from e

        async with self.pool.acquire() as conn:
            r = await conn.fetchrow(
                "SELECT id, access_hash, type FROM peers WHERE session = $1 AND id = $2",
                self.session,
                peer_id_int,
            )

        if r is None:
            raise KeyError(f"Peer ID not found: {peer_id_int}")

        return get_input_peer(r["id"], r["access_hash"], r["type"])

    async def get_peer_by_username(self, username: str) -> InputPeer:
        async with self.pool.acquire() as conn:
            r = await conn.fetchrow(
                """
                SELECT p.id, p.access_hash, p.type, p.last_update_on
                FROM peers AS p
                JOIN usernames AS u ON p.id = u.id AND p.session = u.session
                WHERE u.session = $1 AND u.username = $2
                """,
                self.session,
                username,
            )

        if r is None:
            raise KeyError(f"Username not found: {username}")

        if abs(time.time() - r["last_update_on"]) > self.USERNAME_TTL:
            raise KeyError(f"Username cache expired: {username}")

        return get_input_peer(r["id"], r["access_hash"], r["type"])

    async def get_peer_by_phone_number(self, phone_number: str) -> InputPeer:
        async with self.pool.acquire() as conn:
            r = await conn.fetchrow(
                "SELECT id, access_hash, type FROM peers WHERE session = $1 AND phone_number = $2",
                self.session,
                phone_number,
            )

        if r is None:
            raise KeyError(f"Phone number not found: {phone_number}")

        return get_input_peer(r["id"], r["access_hash"], r["type"])

    async def _get(self, attr: str) -> Any:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                f'SELECT "{attr}" FROM sessions WHERE session = $1', self.session
            )

    async def _set(self, attr: str, value: Any) -> None:
        if attr in ("is_bot", "test_mode") and isinstance(value, int):
            value = bool(value)

        async with self.pool.acquire() as conn:
            await conn.execute(
                f'UPDATE sessions SET "{attr}" = $1 WHERE session = $2',
                value,
                self.session,
            )

    async def _accessor(self, attr: str, value: Any = Object) -> Any:
        return (
            await self._get(attr) if value is Object else await self._set(attr, value)
        )

    @overload
    async def dc_id(self) -> int | None: ...
    @overload
    async def dc_id(self, value: int) -> None: ...
    async def dc_id(self, value: Any = Object) -> int | None:
        res = await self._accessor("dc_id", value)
        return cast(Optional[int], res) if value is Object else None

    @overload
    async def api_id(self) -> int | None: ...
    @overload
    async def api_id(self, value: int) -> None: ...
    async def api_id(self, value: Any = Object) -> int | None:
        res = await self._accessor("api_id", value)
        return cast(Optional[int], res) if value is Object else None

    @overload
    async def test_mode(self) -> bool | None: ...
    @overload
    async def test_mode(self, value: bool) -> None: ...
    async def test_mode(self, value: Any = Object) -> bool | None:
        res = await self._accessor("test_mode", value)
        return cast(Optional[bool], res) if value is Object else None

    @overload
    async def auth_key(self) -> bytes | None: ...
    @overload
    async def auth_key(self, value: bytes) -> None: ...
    async def auth_key(self, value: Any = Object) -> bytes | None:
        res = await self._accessor("auth_key", value)
        return cast(Optional[bytes], res) if value is Object else None

    @overload
    async def date(self) -> int: ...
    @overload
    async def date(self, value: int) -> None: ...
    async def date(self, value: Any = Object) -> int | None:
        res = await self._accessor("date", value)
        return cast(int, res) if value is Object else None

    @overload
    async def user_id(self) -> int | None: ...
    @overload
    async def user_id(self, value: int) -> None: ...
    async def user_id(self, value: Any = Object) -> int | None:
        res = await self._accessor("user_id", value)
        return cast(Optional[int], res) if value is Object else None

    @overload
    async def is_bot(self) -> bool | None: ...
    @overload
    async def is_bot(self, value: bool) -> None: ...
    async def is_bot(self, value: Any = Object) -> bool | None:
        res = await self._accessor("is_bot", value)
        return cast(Optional[bool], res) if value is Object else None

    @overload
    async def version(self) -> int: ...
    @overload
    async def version(self, value: int) -> None: ...
    async def version(self, value: Any = Object) -> int | None:
        async with self.pool.acquire() as conn:
            if value is Object:
                v = await conn.fetchval("SELECT number FROM version")
                return cast(int, v)

            await conn.execute("UPDATE version SET number = $1", value)
            return None

    async def update(self) -> None:
        v = await self.version()
        if v != self.VERSION:
            raise RuntimeError(
                f"Database version mismatch (found {v}, expected {self.VERSION})"
            )
