import asyncio
import datetime
import html
import re
import shutil
import time
from pathlib import Path

from pyrogram import filters
from pyrogram.enums import MessageMediaType
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from selfbot import listener
from selfbot.module import Module

pattern = re.compile(r"^fps60$")


class FPSConverter(Module):
    name = "FPS Converter"
    cmds = "<Reply to Video> fps60"
    desc = {
        "Info": "Converts the replied video to 60 FPS using FFmpeg motion interpolation.",
        "e.g.": "<Reply to Video> fps60",
    }

    def _parse_ffmpeg_time(self, time_str: str) -> float:
        """Konversi format waktu FFmpeg (HH:MM:SS.ms) ke detik."""
        try:
            parts = time_str.split(':')
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        except (ValueError, IndexError):
            return 0.0

    def _create_progress_bar(self, percentage: int) -> str:
        return "▰" * (max(0, min(100, percentage)) // 10) + "▱" * (10 - (max(0, min(100, percentage)) // 10))

    @listener.handler(filters.regex(pattern) & listener.fltrep, 1)
    async def on_convert_fps(self, event: Message) -> None:
        """Handles the video to 60 FPS conversion command."""
        replied_message = event.reply_to_message
        # more robust check: ensure replied message has a video object
        if not replied_message or not getattr(replied_message, "video", None):
            await event.edit_text("<code>Please reply to a video message.</code>")
            return

        video = replied_message.video
        if video and video.duration > 60:
            await event.edit_text("<code>Video duration exceeds the 1-minute limit.</code>")
            return

        await event.edit_text("<code>Processing...</code>")
        now = datetime.datetime.now(datetime.UTC)

        # Create a temporary directory for this conversion
        temp_dir = Path("downloads") / f"fps_converter_{event.id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        input_path = None
        output_path = None

        # Regex untuk menangkap informasi waktu dari output FFmpeg (mendukung desimal variable)
        time_pattern = re.compile(r"time=(\d{2}:\d{2}:\d{2}(?:\.\d+)?)")

        try:
            # 1. Download the video
            await event.edit_text("<code>Downloading video...</code>")
            input_path = await replied_message.download(in_memory=False, file_name=str(temp_dir / "input.mp4"))

            if not input_path or not Path(input_path).exists():
                raise Exception("Video download failed.")

            # 2. Convert the video using FFmpeg
            output_path = str(temp_dir / "output_60fps.mp4")

            # FFmpeg command for motion interpolation
            command = (
                f'ffmpeg -i "{input_path}" '
                f'-vf "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1" '
                f'-c:v libx264 -preset fast -crf 23 '
                f'-c:a copy "{output_path}" -y -progress pipe:1'
            )

            self.logger.info(f"Executing FFmpeg command: {command}")

            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            last_update_time = 0
            stderr_accum = ""
            # Read progress from stdout (because we used -progress pipe:1)
            while True:
                # Try to read a line from stdout; if none, check if process ended
                line_bytes = await process.stdout.readline()
                if line_bytes:
                    line = line_bytes.decode('utf-8', errors='ignore').strip()
                else:
                    # no stdout line; check stderr for errors and process status
                    err = await process.stderr.readline()
                    if err:
                        stderr_accum += err.decode('utf-8', errors='ignore')
                    if process.returncode is not None:
                        break
                    # if process still running but no stdout available yet, small sleep
                    await asyncio.sleep(0.1)
                    # continue to next iteration
                    if not line_bytes and not err:
                        continue
                    else:
                        # if we did read something from stderr, continue to parse
                        if not line_bytes:
                            line = ""

                # accumulate stderr too for diagnostics
                if line.startswith("frame=") or line.startswith("time=") or line.startswith("progress=") or line:
                    # parse possible time=... lines from stdout progress or ffmpeg-ish output
                    m = time_pattern.search(line)
                    if m:
                        current_time = self._parse_ffmpeg_time(m.group(1))
                        duration = getattr(video, "duration", 0) or 0.0
                        if duration > 0:
                            percentage = int((current_time / duration) * 100)
                            percentage = max(0, min(100, percentage))
                        else:
                            percentage = 0

                        # Update progress setiap 5 detik untuk menghindari FloodWait
                        if time.time() - last_update_time > 5:
                            progress_bar = self._create_progress_bar(percentage)
                            try:
                                await event.edit_text(
                                    f"<code>Converting to 60 FPS...\n"
                                    f"[{progress_bar}] {percentage}%</code>"
                                )
                                last_update_time = time.time()
                            except FloodWait as e:
                                await asyncio.sleep(e.value)
                            except Exception:
                                # ignore if message deleted or other error
                                pass

                # If process finished, break loop
                if process.returncode is not None:
                    break

            # wait until process really finishes
            await process.wait()

            if process.returncode != 0:
                raise Exception(f"FFmpeg conversion failed.\n\nDetails:\n{stderr_accum[-1000:]}")

            if not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
                raise Exception("Conversion failed: Output file is missing or empty.")

            # 3. Upload the converted video
            await event.edit_text("<code>Uploading converted video...</code>")

            caption = f"<b>Converted to 60 FPS</b>\n\n<b><blockquote>{fmtsec(now)}</blockquote></b>"

            await event.reply_video(
                video=output_path,
                caption=caption,
                supports_streaming=True
            )

            await event.delete()

        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"FPS conversion failed: {error_msg}")
            await event.edit_text(f"<b>An error occurred:</b>\n<code>{html.escape(error_msg)}</code>")
        finally:
            # Clean up the temporary directory
            if temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    self.logger.warning(f"Failed to cleanup temporary directory {temp_dir}: {e}")