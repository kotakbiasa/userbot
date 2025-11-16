import asyncio
from typing import Optional

from pyrogram import Client
from pyrogram.types import Message


class Conversation:
    """
    A utility class to manage conversations with bots or users in Pyrogram.
    """

    def __init__(self, client: Client, chat_id: int | str, timeout: int = 15):
        self.client = client
        self.chat_id = chat_id
        self.timeout = timeout
        self.response_event = asyncio.Event()
        self.response: Optional[Message] = None

    async def _on_message(self, _, message: Message):
        """Handler to capture incoming messages."""
        if message.chat.id == self.chat_id:
            self.response = message
            self.response_event.set()

    async def __aenter__(self):
        self.handler = self.client.add_handler(
            self.client.MessageHandler(self._on_message, filters=self.client.filters.incoming)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.client.remove_handler(*self.handler)

    async def send_message(self, text: str) -> Message:
        """Sends a message to the conversation chat."""
        return await self.client.send_message(self.chat_id, text)

    async def get_response(self, timeout: Optional[int] = None) -> Message:
        """Waits for and returns the next response in the conversation."""
        await asyncio.wait_for(self.response_event.wait(), timeout or self.timeout)
        return self.response