import time

from asyncpg import Pool
from pyrogram import raw, utils
from pyrogram.raw.base import InputPeer
from pyrogram.storage import Storage

schema = """
CREATE SCHEMA IF NOT EXISTS storage;
CREATE TABLE IF NOT EXISTS storage.sessions (
    name        TEXT    PRIMARY KEY,
    dc_id       INTEGER NOT NULL,
    api_id      INTEGER,
    test_mode   BOOLEAN,
    auth_key    BYTEA,
    date        BIGINT  NOT NULL,
    user_id     BIGINT,
    is_bot      BOOLEAN
);
CREATE TABLE IF NOT EXISTS storage.peers (
    name            TEXT    NOT NULL,
    id              BIGINT  NOT NULL,
    access_hash     BIGINT,
    type            TEXT    NOT NULL,
    phone_number    TEXT,
    PRIMARY KEY (name, id)
);
CREATE TABLE IF NOT EXISTS storage.usernames (
    name        TEXT    NOT NULL,
    id          BIGINT  NOT NULL,
    username    TEXT    NOT NULL,
    PRIMARY KEY (name, username),
    FOREIGN KEY (name, id)
        REFERENCES storage.peers (name, id)
        ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS storage.update_state (
    name    TEXT    NOT NULL,
    id      INTEGER NOT NULL,
    pts     BIGINT,
    qts     BIGINT,
    date    BIGINT,
    seq     BIGINT,
    PRIMARY KEY (name, id)
);
CREATE INDEX IF NOT EXISTS idx_peers_phone_number
    ON storage.peers (name, phone_number);
"""
Object = object()


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


class PostgreStorage(Storage):
    def __init__(self, name: str, pool: Pool) -> None:
        super().__init__(name)
        self.name = name
        self.pool = pool

    async def open(self) -> None:
        await self.pool.execute(schema)
        await self.pool.execute(
            """
            INSERT INTO storage.sessions (name, dc_id, date)
            VALUES ($1, $2, $3)
            ON CONFLICT (name) DO NOTHING;
            """,
            self.name,
            2,
            0,
        )

    async def save(self) -> None:
        await self.date(int(time.time()))

    async def close(self) -> None:
        pass

    async def delete(self) -> None:
        await self.pool.execute("DROP SCHEMA IF EXISTS storage CASCADE;")

    async def update_peers(self, peers: list | None = None) -> None:
        if not peers:
            return

        peer_records = []
        username_records = []
        for p_id, p_access_hash, p_type, p_usernames, p_phone_number in peers:
            peer_records.append(
                (self.name, p_id, p_access_hash, p_type, p_phone_number)
            )
            if p_usernames:
                for uname in p_usernames:
                    username_records.append((self.name, p_id, uname))

        await self.pool.executemany(
            """
            INSERT INTO storage.peers (
                name,
                id,
                access_hash,
                type,
                phone_number
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (name, id) DO UPDATE SET
                access_hash = EXCLUDED.access_hash,
                type = EXCLUDED.type,
                phone_number = EXCLUDED.phone_number;
            """,
            peer_records,
        )
        if username_records:
            await self.pool.executemany(
                """
                INSERT INTO storage.usernames (name, id, username)
                VALUES ($1, $2, $3)
                ON CONFLICT (name, username) DO UPDATE SET
                    id = EXCLUDED.id;
                """,
                username_records,
            )

    async def update_state(self, value: any = Object) -> list | None:
        if value is Object:
            rows = await self.pool.fetch(
                """
                SELECT
                    id,
                    pts,
                    qts,
                    date,
                    seq
                FROM storage.update_state
                WHERE name = $1;
                """,
                self.name,
            )
            return [tuple(r) for r in rows]

        if value is None:
            await self.pool.execute(
                "DELETE FROM storage.update_state WHERE name = $1;", self.name
            )
        else:
            await self.pool.execute(
                """
                INSERT INTO storage.update_state (
                    name,
                    id,
                    pts,
                    qts,
                    date,
                    seq
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (name, id) DO UPDATE SET
                    pts = EXCLUDED.pts,
                    qts = EXCLUDED.qts,
                    date = EXCLUDED.date,
                    seq = EXCLUDED.seq;
                """,
                self.name,
                *value,
            )

        return None

    async def get_peer_by_id(self, peer_id: int | str) -> InputPeer:
        try:
            peer_id_int = int(peer_id)
        except (ValueError, TypeError) as e:
            raise KeyError(f"Invalid peer ID: {peer_id}") from e

        res = await self.pool.fetchval(
            """
            SELECT (id, access_hash, type)
            FROM storage.peers
            WHERE name = $1
                AND id = $2;
            """,
            self.name,
            peer_id_int,
        )

        if not res:
            raise KeyError(f"Peer ID not found: {peer_id_int}")

        return get_input_peer(*res)

    async def get_peer_by_username(self, username: str) -> InputPeer:
        res = await self.pool.fetchval(
            """
            SELECT (p.id, p.access_hash, p.type)
            FROM storage.peers AS p
            JOIN storage.usernames AS u
                ON p.id = u.id
                AND p.name = u.name
            WHERE u.name = $1
                AND u.username = $2;
            """,
            self.name,
            username,
        )

        if not res:
            raise KeyError(f"Username not found: {username}")

        return get_input_peer(*res)

    async def get_peer_by_phone_number(self, phone_number: str) -> InputPeer:
        res = await self.pool.fetchval(
            """
            SELECT (id, access_hash, type)
            FROM storage.peers
            WHERE name = $1
                AND phone_number = $2;
            """,
            self.name,
            phone_number,
        )

        if not res:
            raise KeyError(f"Phone number not found: {phone_number}")

        return get_input_peer(*res)

    async def dc_id(self, value: any = Object) -> int | None:
        res = await self._value("dc_id", value)
        return res if value is Object else None

    async def api_id(self, value: any = Object) -> int | None:
        res = await self._value("api_id", value)
        return res if value is Object else None

    async def test_mode(self, value: any = Object) -> bool | None:
        res = await self._value("test_mode", value)
        return res if value is Object else None

    async def auth_key(self, value: any = Object) -> bytes | None:
        res = await self._value("auth_key", value)
        return res if value is Object else None

    async def date(self, value: any = Object) -> int | None:
        res = await self._value("date", value)
        return res if value is Object else None

    async def user_id(self, value: any = Object) -> int | None:
        res = await self._value("user_id", value)
        return res if value is Object else None

    async def is_bot(self, value: any = Object) -> bool | None:
        res = await self._value("is_bot", value)
        return res if value is Object else None

    async def _value(self, attr: str, value: any = Object) -> any:
        if value is Object:
            return await self.pool.fetchval(
                f"SELECT {attr} FROM storage.sessions WHERE name = $1;", self.name
            )

        if attr in ["is_bot", "test_mode"] and not isinstance(value, bool):
            value = bool(value)

        await self.pool.execute(
            f"UPDATE storage.sessions SET {attr} = $1 WHERE name = $2;",
            value,
            self.name,
        )
