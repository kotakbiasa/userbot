import asyncio
import datetime
import html
import re

import speedtest
from pyrogram import filters
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module
from selfbot.utils import fmtsec, fmtstr

pattern = re.compile(r"^speed(?:test)?$")


class Speedtest(Module):
    name = "Speedtest"
    cmds = "speed(test)?"
    desc = {
        "?": "Optional",
        "e.g.": "speedtest",
        "Info": "Runs an internet speed test and displays the results.",
    }

    @listener.handler(filters.regex(pattern) & ~listener.fltrep, priority=1)
    async def on_message_out(self, event: Message) -> None:
        """Runs an internet speed test."""
        await event.edit_text("<code>Running speedtest...</code>")
        now = datetime.datetime.now(datetime.UTC)

        try:
            # Run the synchronous speedtest function in a separate thread
            results = await asyncio.to_thread(self.run_speed_test)

            if not results:
                await event.edit_text("<code>Speedtest failed: No results returned.</code>")
                return

            # Format the results
            output = fmtstr(
                "Speedtest Results",
                {
                    "Provider": results.get('isp', 'N/A'),
                    "Server": f"{results.get('server_name', 'N/A')} ({results.get('server_country', 'N/A')})",
                    "Ping": f"{results.get('ping', 0):.2f} ms",
                    "Download": f"{results.get('download', 0) / 1_000_000:.2f} Mbps",
                    "Upload": f"{results.get('upload', 0) / 1_000_000:.2f} Mbps",
                },
                fmtsec(now),
            )
            await event.edit_text(output)

        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Speedtest failed: {error_msg}")
            await event.edit_text(
                f"<b>Speedtest failed:</b>\n<code>{html.escape(error_msg[:200])}</code>"
            )

    def run_speed_test(self) -> dict:
        """Synchronous function to run the speedtest."""
        try:
            st = speedtest.Speedtest(secure=True)
            
            # Get best server
            st.get_best_server()
            
            # Run download and upload tests
            st.download()
            st.upload()
            
            # Extract results with compatibility for different versions
            results = {
                'isp': st.results.client.get('isp', 'N/A'),
                'server_name': st.results.server.get('name', 'N/A'),
                'server_country': st.results.server.get('country', 'N/A'),
                'ping': st.results.ping,
                'download': st.results.download,
                'upload': st.results.upload,
            }
            
            return results
        except AttributeError:
            # Fallback untuk versi speedtest yang berbeda
            try:
                results = {
                    'isp': st.results['client'].get('isp', 'N/A'),
                    'server_name': st.results['server'].get('name', 'N/A'),
                    'server_country': st.results['server'].get('country', 'N/A'),
                    'ping': st.results['ping'],
                    'download': st.results['download'],
                    'upload': st.results['upload'],
                }
                return results
            except Exception as e:
                self.logger.error(f"Failed to extract speedtest results: {e}")
                raise Exception(f"Failed to extract speedtest results: {str(e)}")
        except Exception as e:
            raise Exception(f"Speedtest execution failed: {str(e)}")