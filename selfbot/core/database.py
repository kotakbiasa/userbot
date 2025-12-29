import abc

from asyncpg import create_pool

queries = """
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
    id      BIGINT  NOT NULL,
    pts     INTEGER,
    qts     INTEGER,
    date    INTEGER,
    seq     INTEGER,
    PRIMARY KEY (name, id)
);
CREATE INDEX IF NOT EXISTS idx_peers_phone_number
    ON storage.peers (name, phone_number);
CREATE SCHEMA IF NOT EXISTS restart;
CREATE TABLE IF NOT EXISTS restart.msg (
    chat_id     BIGINT,
    message_id  INTEGER
);
CREATE SCHEMA IF NOT EXISTS afk;
CREATE TABLE IF NOT EXISTS afk.meta (
    reason  TEXT,
    since   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS afk.msgs (
    chat_id     BIGINT PRIMARY KEY,
    message_id  INTEGER
);
CREATE SCHEMA IF NOT EXISTS call;
CREATE TABLE IF NOT EXISTS call.chats (
    chat_id BIGINT  PRIMARY KEY,
    join_as BIGINT,
    mute    BOOLEAN DEFAULT FALSE
);
"""


class Database(abc.ABC):
    def __init__(self, **kwargs) -> None:
        self.db = None
        super().__init__(**kwargs)

    async def initdb(self) -> None:
        try:
            self.db = await create_pool(self.config["DATABASE_URL"])
        except Exception as e:
            self.logger.error(f"{e.__class__.__name__}: {e}")
        else:
            self.config.pop("DATABASE_URL", None)
            await self.db.execute(queries)
