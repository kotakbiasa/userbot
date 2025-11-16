import asyncio
import datetime
import html
import re

from pyrogram import filters
from pyrogram.types import (
    CallbackQuery,
    InlineQuery,
    InlineQueryResultPhoto,
    InputMediaPhoto,
    Message,
    ReplyParameters,
)

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, ikm


class AnimePic(Module):
    name = "AnimePic"

    # Daftar tag khusus untuk API nekos.best
    nekos_best_tags = ["husbando", "kitsune", "neko", "pat"]

    # Daftar tag khusus untuk API waifu.pics
    waifu_pics_tags = [
        "waifu",
        "neko",
        "shinobu",
        "megumin",
        "bully",
        "cry",
        "awoo",
        "lick",
        "smug",
        "blush",
        "smile",
        "wave",
        "highfive",
        "handhold",
        "nom",
        "bite",
        "slap",
        "happy",
        "wink",
        "poke",
        "cringe",
    ]

    # Daftar tag khusus untuk API nekosia.cat
    nekosia_tags = [
        "animal_ears",
        "blue-archive",
        "blue_eyes",
        "cat_ears",
        "catgirl",
        "cute",
        "fox_ears",
        "foxgirl",
        "girl",
        "pink_hair",
        "ribbon",
        "sailor_uniform",
        "skirt",
        "smile",
        "tail",
        "tail_with_ribbon",
        "thigh_high_socks",
        "thighs",
        "uniform",
        "vtuber",
        "white_hair",
        "white_thigh_high_socks",
        "young_girl",
        "kemonomimi",
    ]

    # Daftar tag khusus untuk API waifu.im
    waifu_im_tags = [
        "kamisato-ayaka",
        "marin-kitagawa",
        "mori-calliope",
        "raiden-shogun",
        "maid",
        "oppai",
        "selfies",
        "uniform",
        "waifu",
    ]

    # Daftar tag khusus untuk API t.mwm.moe
    mwm_moe_tags = [
        "ai",
        "aimp",
        "bd",
        "fj",
        "lai",
        "moe",
        "moemp",
        "mp",
        "pc",
        "tx",
        "xhl",
        "ys",
        "ysmp",
    ]

    # Daftar tag khusus untuk API pic.re
    picre_tags = ["picre"]

    # Daftar tag khusus untuk API nekos.moe
    nekos_moe_tags = ["moe"]

    # Daftar tag khusus untuk API nekobot.xyz
    nekobot_tags = ["coffee", "food", "holo", "kanna", "kemonomimi", "neko"]

    # Daftar tag khusus untuk API nekosapi.com
    nekosapi_tags = [
        "bikini",
        "black_hair",
        "blonde_hair",
        "blue_hair",
        "brown_hair",
        "catgirl",
        "dress",
        "flower",
        "girl",
        "horsegirl",
        "kemonomimi",
        "large_breasts",
        "medium_breasts",
        "mountain",
        "night",
        "pink_hair",
        "purple_hair",
        "rain",
        "red_hair",
        "school_uniform",
        "shorts",
        "skirt",
        "small_breasts",
        "sportswear",
        "tree",
        "usagimimi",
        "wet",
        "white_hair",
    ]

    # Daftar tag yang didukung
    tags = sorted(
        list(
            set(
                mwm_moe_tags
                + picre_tags
                + waifu_im_tags
                + nekos_moe_tags
                + nekobot_tags
                + nekosapi_tags
                + nekosia_tags
                + waifu_pics_tags
                + nekos_best_tags
                + [
                    "gecg",
                    "meow",
                    "gasm",
                    "goose",
                    "lewd",
                    "v3",
                    "wallpaper",
                    "lizard",
                    "woof",
                    "fox_girl",
                    "avatar",
                    "cuddle",
                    "hug",
                    "kiss",
                    "spank",
                    "feed",
                ]
            )
        )
    )

    # Membuat pola regex dari daftar tag
    msg_pattern = re.compile(rf"^({'|'.join(tags)})$", re.IGNORECASE)
    cb_pattern = re.compile(r"^animepic/next/(.+)$")

    # Deskripsi untuk modul bantuan
    cmds = f"{{{', '.join(tags)}}}"
    desc = {
        "Info": "Sends an anime picture based on a tag with interactive buttons.",
        "e.g.": "waifu",
    }

    @listener.handler(filters.regex(msg_pattern), priority=1)
    async def on_message_out(self, event: Message) -> None:
        await event.edit_text("<code>...</code>")

        try:
            # Panggil bot inline dari akun pengguna
            results = await event._client.get_inline_bot_results(
                self.client.bot.me.username, event.text
            )
            if not results.results:
                await event.edit_text("<code>The bot did not return any results.</code>")
                return

            # Kirim hasil pertama dari bot inline
            await event.reply_inline_bot_result(
                results.query_id,
                results.results[0].id,
                reply_parameters=ReplyParameters(  # Ensure it replies in the correct topic
                    message_id=event.reply_to_message_id or event.id
                ),
            )
            await event.delete()

        except Exception as e:
            await event.edit_text(f"<code>{html.escape(str(e))}</code>")

    @listener.handler(filters.regex(msg_pattern), priority=2)
    async def on_inline_query(self, event: InlineQuery) -> None:
        tag = event.matches[0].group(1).lower()

        try:
            now = datetime.datetime.now(datetime.UTC)
            result = await self.get_image_url(tag)
            rtt = fmtsec(now)
            if not result:
                # Jika tidak ada URL, jangan kirim hasil apa pun
                await event.answer([], cache_time=0)
                return

            await event.answer(
                [
                    InlineQueryResultPhoto(
                        photo_url=result[0],
                        caption=self.build_caption(rtt, *result[1:]),
                        reply_markup=self.build_keyboard(tag),
                    )
                ],
                cache_time=0,
            )
        except Exception:
            await event.answer([], cache_time=0)

    @listener.handler(filters.regex(cb_pattern), priority=4)
    async def on_inline_callback(self, event: CallbackQuery) -> None:
        (tag,) = event.matches[0].groups()

        try:
            await event.answer("Refreshing...")
            now = datetime.datetime.now(datetime.UTC)
            new_result = await self.get_image_url(tag)
            rtt = fmtsec(now)
            if not new_result:
                await event.answer("Failed to get a new image.", show_alert=True)
                return

            await event.edit_message_media(
                media=InputMediaPhoto(
                    new_result[0], caption=self.build_caption(rtt, *new_result[1:])
                ),
                reply_markup=self.build_keyboard(tag),
            )
        except Exception as e:
            await event.answer(f"Error: {html.escape(str(e))}", show_alert=True)

    async def get_image_url(self, tag: str) -> tuple | None:
        """Mendapatkan URL gambar non-GIF dari berbagai API."""
        apis_to_try = [
            (self.mwm_moe_tags, self._get_from_mwm_moe),
            (self.picre_tags, self._get_from_picre),
            (self.waifu_im_tags, self._get_from_waifu_im),
            (self.nekos_moe_tags, self._get_from_nekos_moe),
            (self.nekobot_tags, self._get_from_nekobot),
            (self.nekosapi_tags, self._get_from_nekosapi),
            (self.nekosia_tags, self._get_from_nekosia),
            (self.waifu_pics_tags, self._get_from_waifu_pics),
            (self.nekos_best_tags, self._get_from_nekos_best),
        ]

        for tags_list, api_func in apis_to_try:
            if tag in tags_list:
                try:
                    result = await api_func(tag)
                    if result:
                        return result
                except Exception:
                    continue  # Coba API berikutnya jika ada error

        # API Cadangan (nekos.life)
        try:
            for _ in range(3):  # Coba hingga 3 kali
                resp = await self.client.http.get(
                    f"https://nekos.life/api/v2/img/{tag}"
                )
                if resp.status_code == 200:
                    data = resp.json()
                    url = data.get("url")
                    if url and not url.endswith(".gif"):
                        return url, None, {}, None
                await asyncio.sleep(0.2)
        except Exception:
            return None

        return None

    # --- Metode Helper untuk setiap API ---

    async def _get_from_mwm_moe(self, tag: str):
        resp = await self.client.http.get(
            f"https://t.mwm.moe/{tag}", follow_redirects=True
        )
        if resp.status_code == 200:
            url = str(resp.url)
            if url and not url.endswith(".gif"):
                return url, None, {}, None
        return None

    async def _get_from_picre(self, tag: str):
        resp = await self.client.http.get("https://pic.re/images")
        if resp.status_code == 200:
            url = str(resp.url)
            source_url = resp.headers.get("image_source")
            if url and not url.endswith(".gif"):
                return url, None, None, source_url
        return None

    async def _get_from_waifu_im(self, tag: str):
        params = {"included_tags": [tag], "is_nsfw": "false"}
        resp = await self.client.http.get(
            "https://api.waifu.im/search", params=params
        )
        if resp.status_code == 200:
            data = resp.json()
            if images := data.get("images"):
                image_data = images[0]
                url = image_data.get("url")
                if url and not url.endswith(".gif"):
                    artist = image_data.get("artist") or {}
                    artist_links = {
                        k: v
                        for k, v in {
                            "Pixiv": artist.get("pixiv"),
                            "Twitter": artist.get("twitter"),
                        }.items()
                        if v
                    }
                    return (
                        url,
                        artist.get("name"),
                        artist_links,
                        image_data.get("source"),
                    )
        return None

    async def _get_from_nekos_moe(self, tag: str):
        params = {"nsfw": "false"}
        resp = await self.client.http.get(
            "https://nekos.moe/api/v1/random/image", params=params
        )
        if resp.status_code == 200:
            data = resp.json()
            if images := data.get("images"):
                image_data = images[0]
                if image_id := image_data.get("id"):
                    url = f"https://nekos.moe/image/{image_id}"
                    return (
                        url,
                        image_data.get("artist"),
                        {},
                        f"https://nekos.moe/post/{image_id}",
                    )
        return None

    async def _get_from_nekobot(self, tag: str):
        api_category = "hololewd" if tag == "holo" else tag
        resp = await self.client.http.get(
            f"https://nekobot.xyz/api/image?type={api_category}"
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                url = data.get("message")
                if url and not url.endswith(".gif"):
                    return url, None, {}, None
        return None

    async def _get_from_nekosapi(self, tag: str):
        params = {"rating": "safe,suggestive", "count": 1, "tags": tag}
        resp = await self.client.http.get(
            "https://api.nekosapi.com/v4/images/random", params=params
        )
        if resp.status_code == 200:
            if images := resp.json():
                image_data = images[0]
                url = image_data.get("url")
                if url and not url.endswith(".gif"):
                    return (
                        url,
                        image_data.get("artist_name"),
                        {},
                        image_data.get("source_url"),
                    )
        return None

    async def _get_from_nekosia(self, tag: str):
        resp = await self.client.http.get(f"https://api.nekosia.cat/api/v1/images/{tag}")
        if resp.status_code != 200:
            resp = await self.client.http.get(
                "https://api.nekosia.cat/api/v1/images/random", params={"tag": tag}
            )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                data = data[0]
            url = data.get("image", {}).get("original", {}).get("url")
            if url and not url.endswith(".gif"):
                artist = data.get("attribution", {}).get("artist", {})
                source = data.get("source", {})
                return (
                    url,
                    artist.get("username"),
                    {"profile": artist.get("profile")},
                    source.get("url"),
                )
        return None

    async def _get_from_waifu_pics(self, tag: str):
        resp = await self.client.http.get(f"https://api.waifu.pics/sfw/{tag}")
        if resp.status_code == 200:
            data = resp.json()
            url = data.get("url")
            if url and not url.endswith(".gif"):
                return url, None, {}, None
        return None

    async def _get_from_nekos_best(self, tag: str):
        resp = await self.client.http.get(f"https://nekos.best/api/v2/{tag}")
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("results", [{}])[0]
            url = result.get("url")
            if url and not url.endswith(".gif"):
                return (
                    url,
                    result.get("artist_name"),
                    {"profile": result.get("artist_href")},
                    result.get("source_url"),
                )
        return None

    def build_keyboard(self, tag: str) -> ikm:
        """Membangun inline keyboard."""
        return ikm([[("Refresh", f"animepic/next/{tag}"), ("Close", b"0")]])

    def build_caption(
        self,
        rtt: str,
        artist_name: str | None,
        artist_links: dict | None,
        source_url: str | None,
    ) -> str:
        """Membangun caption dengan informasi artis dan sumber."""
        caption_parts = []
        if artist_name:
            artist_str = f"Artist: {html.escape(artist_name)}"
            if artist_links:
                links = []
                for name, url in artist_links.items():
                    if url:
                        links.append(f'<a href="{url}">{name.capitalize()}</a>')
                if links:
                    artist_str += f" ({' | '.join(links)})"
            caption_parts.append(artist_str)
        if source_url:
            caption_parts.append(f'<a href="{source_url}">Source</a>')

        info_line = " | ".join(caption_parts)
        return (
            f"{info_line}\n<b><blockquote>{rtt}</blockquote></b>"
            if info_line
            else f"<b><blockquote>{rtt}</blockquote></b>"
        )