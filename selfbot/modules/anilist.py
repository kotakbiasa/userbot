import asyncio
import html
import re
from datetime import datetime

from pyrogram import filters
from pyrogram.types import (
    CallbackQuery,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
    ReplyParameters,
)

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, ikm

# --- Konstanta dan Query GraphQL ---
ANILIST_API_URL = "https://graphql.anilist.co"

SEARCH_QUERY = """
query ($search: String, $type: MediaType) {
  Page(page: 1, perPage: 8) {
    media(search: $search, type: $type, sort: SEARCH_MATCH) {
      id
      title { romaji english }
      format
      startDate { year }
    }
  }
}
"""

DETAILS_QUERY = """
query ($id: Int) {
  Media(id: $id) {
    id
    title { romaji english native }
    description(asHtml: false)
    startDate { year month day }
    endDate { year month day }
    status
    season
    type
    format
    episodes
    duration
    chapters
    volumes
    averageScore
    genres
    studios(isMain: true) { nodes { name } }
    coverImage { extraLarge }
    bannerImage
    siteUrl
  }
}
"""


class Anilist(Module):
    """Module to search for anime and manga on AniList."""

    name = "Anilist"
    cmds = "anilist {query}"
    desc = {
        "Info": "Searches for anime or manga on AniList.",
        "query": "The title to search for.",
        "e.g.": "anilist Attack on Titan",
    }

    msg_pattern = re.compile(r"^anilist\s+(.+)$", re.DOTALL)
    cb_pattern = re.compile(r"^anilist/(anime|manga)/(\d+)$")

    def _clean_html(self, text: str) -> str:
        """Removes HTML tags and formats the description."""
        if not text:
            return "No description available."
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = re.sub(r"<.*?>", "", text)
        return html.escape(text)

    async def _fetch_anilist(self, query: str, variables: dict) -> dict:
        """Helper function to query the AniList API."""
        payload = {"query": query, "variables": variables}
        response = await self.client.http.post(ANILIST_API_URL, json=payload, timeout=20)
        response.raise_for_status()
        return response.json()

    @listener.handler(filters.regex(msg_pattern), priority=1)
    async def on_message_out(self, event: Message) -> None:
        """Handles the .anilist command by triggering an inline query."""
        await event.edit_text("<code>...</code>")
        try:
            results = await event._client.get_inline_bot_results(
                self.client.bot.me.username, f"anilist {event.matches[0].group(1)}"
            )
            if not results.results:
                await event.edit_text("<code>No results found.</code>")
                return

            await event.reply_inline_bot_result(
                results.query_id,
                results.results[0].id,
                reply_parameters=ReplyParameters(
                    message_id=event.reply_to_message_id or event.id
                ),
            )
            await event.delete()
        except Exception as e:
            await event.edit_text(f"<b>Error:</b>\n<code>{html.escape(str(e))}</code>")

    @listener.handler(filters.regex(msg_pattern), priority=2)
    async def on_inline_query(self, event: InlineQuery) -> None:
        """Handles the inline query to search for media."""
        query = event.matches[0].group(1).strip()
        
        # Search for both Anime and Manga
        try:
            anime_results, manga_results = await asyncio.gather(
                self._fetch_anilist(SEARCH_QUERY, {"search": query, "type": "ANIME"}),
                self._fetch_anilist(SEARCH_QUERY, {"search": query, "type": "MANGA"}),
            )
        except Exception:
            await event.answer([], cache_time=0)
            return

        keyboard = []
        if anime_media := anime_results.get("data", {}).get("Page", {}).get("media"):
            keyboard.append([("─ ANIME ─", "anilist/noop")])
            for item in anime_media:
                title = item["title"]["romaji"] or item["title"]["english"] or "N/A"
                year = item.get("startDate", {}).get("year") or ""
                keyboard.append([(f"{title} ({year})", f"anilist/anime/{item['id']}")])

        if manga_media := manga_results.get("data", {}).get("Page", {}).get("media"):
            keyboard.append([("─ MANGA ─", "anilist/noop")])
            for item in manga_media:
                title = item["title"]["romaji"] or item["title"]["english"] or "N/A"
                year = item.get("startDate", {}).get("year") or ""
                keyboard.append([(f"{title} ({year})", f"anilist/manga/{item['id']}")])

        if not keyboard:
            await event.answer([], cache_time=0)
            return

        await event.answer(
            [
                InlineQueryResultArticle(
                    title=f"Results for '{query}'",
                    description="Select a title from the list below.",
                    input_message_content=InputTextMessageContent(
                        f"<b>AniList Search:</b> <code>{html.escape(query)}</code>"
                    ),
                    reply_markup=ikm(keyboard),
                )
            ],
            cache_time=0,
        )

    @listener.handler(filters.regex(cb_pattern), priority=4)
    async def on_inline_callback(self, event: CallbackQuery) -> None:
        """Handles button clicks to show media details."""
        match = self.cb_pattern.match(event.data)
        if not match:
            return

        media_type, media_id = match.groups()
        
        try:
            await event.answer("Fetching details...")
            now = datetime.now()
            
            data = await self._fetch_anilist(DETAILS_QUERY, {"id": int(media_id)})
            media = data.get("data", {}).get("Media")

            if not media:
                await event.answer("Failed to fetch details.", show_alert=True)
                return

            # Build caption
            title = media["title"]["romaji"] or media["title"]["english"] or "N/A"
            description = self._clean_html(media.get("description", ""))
            if len(description) > 300:
                description = description[:300] + "..."

            details = {
                "Type": media.get("format", "N/A").replace("_", " ").title(),
                "Status": media.get("status", "N/A").replace("_", " ").title(),
                "Score": f"{media.get('averageScore', 0) / 10.0} / 10",
            }
            if media.get("episodes"):
                details["Episodes"] = media["episodes"]
            if media.get("chapters"):
                details["Chapters"] = media["chapters"]

            details_str = "\n".join(f"<b>{k}:</b> {v}" for k, v in details.items())

            caption = (
                f"<b><a href='{media['siteUrl']}'>{html.escape(title)}</a></b>\n\n"
                f"{details_str}\n\n"
                f"<b>Genres:</b> {', '.join(media.get('genres', []))}\n\n"
                f"<blockquote>{description}</blockquote>\n\n"
                f"<b><blockquote>{fmtsec(now)}</blockquote></b>"
            )

            # Prepare keyboard and media
            keyboard = ikm(
                [
                    ("Description", f"anilist/desc/{media_id}"),
                    ("Close", "0"),
                ]
            )
            
            photo_url = media.get("bannerImage") or media.get("coverImage", {}).get("extraLarge")

            if photo_url:
                await event.edit_message_text(
                    f"<a href='{photo_url}'>&#8205;</a>{caption}",
                    reply_markup=keyboard,
                    disable_web_page_preview=False,
                )
            else:
                await event.edit_message_text(caption, reply_markup=keyboard, disable_web_page_preview=True)

        except Exception as e:
            await event.answer(f"Error: {html.escape(str(e))}", show_alert=True)

    @listener.handler(filters.regex(r"^anilist/desc/(\d+)$"), priority=5)
    async def on_desc_callback(self, event: CallbackQuery) -> None:
        """Handles the 'Description' button click."""
        match = re.match(r"^anilist/desc/(\d+)$", event.data)
        if not match:
            return
            
        media_id = match.group(1)
        try:
            data = await self._fetch_anilist(DETAILS_QUERY, {"id": int(media_id)})
            media = data.get("data", {}).get("Media")
            if not media:
                await event.answer("Could not fetch description.", show_alert=True)
                return
            
            description = self._clean_html(media.get("description", ""))
            title = media["title"]["romaji"] or media["title"]["english"]
            
            await event.answer(
                f"Description for {title}:\n\n{description[:4000]}", show_alert=True
            )
        except Exception as e:
            await event.answer(f"Error: {html.escape(str(e))}", show_alert=True)