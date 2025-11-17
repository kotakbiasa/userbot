import asyncio
import datetime
import html
import re

from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec


class IMDb(Module):
    """Module to fetch movie and TV show information from IMDb."""

    name = "IMDb"
    cmds = "imdb {query}"
    desc = {
        "Info": "Fetches information about a movie or TV show.",
        "query": "The title of the movie or show to search for.",
        "e.g.": "imdb Interstellar",
    }

    # Pola regex untuk menangkap perintah .imdb dan query
    pattern = re.compile(r"^imdb\s+(.+)$", flags=re.DOTALL)

    @listener.handler(filters.regex(pattern), priority=1)
    async def on_message_out(self, event: Message) -> None:
        """Handles the .imdb command."""
        match = self.pattern.match(event.text)
        if not match:
            return

        query = match.group(1).strip()
        await event.edit_text(f"<code>Searching for '{html.escape(query)}'...</code>")
        now = datetime.datetime.now(datetime.UTC)

        try:
            # Langkah 1: Cari film untuk mendapatkan ID
            search_url = f"https://imdbapi.dev/api/v1/search?query={query}"
            search_response = await self.client.http.get(search_url, timeout=20)
            search_response.raise_for_status()
            search_results = search_response.json()

            if not search_results:
                await event.edit_text(f"<code>No results found for '{html.escape(query)}'.</code>")
                return

            movie_id = search_results[0].get("id")
            if not movie_id:
                raise ValueError("Could not find a valid movie ID in search results.")

            await event.edit_text("<code>Fetching details...</code>")

            # Langkah 2: Dapatkan detail lengkap menggunakan ID
            details_url = f"https://imdbapi.dev/api/v1/movie/{movie_id}"
            details_response = await self.client.http.get(details_url, timeout=20)
            details_response.raise_for_status()
            result = details_response.json()

            # Format caption
            caption = self._build_caption(result, fmtsec(now))

            # Kirim poster dengan caption
            # API ini kadang memberikan URL poster yang tidak valid, jadi kita coba dan fallback
            poster_url = result.get("poster")
            if poster_url and not poster_url.startswith("http"):
                poster_url = None

            if poster_url:
                await asyncio.gather(
                    event.delete(),
                    self.client.app.send_photo(
                        chat_id=event.chat.id,
                        photo=poster_url,
                        caption=caption,
                        reply_to_message_id=event.reply_to_message_id or event.id,
                    ),
                )
            else:
                # Jika tidak ada poster, kirim sebagai teks
                await event.edit_text(caption)

        except Exception as e:
            self.logger.error(f"IMDb module error: {e}")
            await event.edit_text(f"<b>Error:</b>\n<code>{html.escape(str(e))}</code>")

    def _build_caption(self, data: dict, rtt: str) -> str:
        """Membangun caption dari data yang diterima."""
        title = html.escape(data.get("title", "N/A"))
        year = data.get("year", "N/A")
        rating = data.get("rating", "N/A") or "N/A"
        plot = html.escape(data.get("plot", "N/A"))
        imdb_url = f"https://www.imdb.com/title/{data.get('id', '')}" if data.get("id") else "#"

        # Ekstrak beberapa aktor dari daftar 'cast'
        cast = data.get("cast", [])
        actors_list = [member.get("actor") for member in cast[:5] if member.get("actor")]
        actors = ", ".join(actors_list) if actors_list else "N/A"

        caption = (
            f"<b><a href='{imdb_url}'>{title}</a> ({year})</b>\n\n"
            f"<b>Rating:</b> ⭐️ {rating}\n"
            f"<b>Actors:</b> {actors}\n\n"
            f"<b>Plot:</b>\n<blockquote>{plot}</blockquote>\n\n"
            f"<b><blockquote>{rtt}</blockquote></b>"
        )
        return caption