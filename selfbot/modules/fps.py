import asyncio
import datetime
import html
import os
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
from selfbot.utils import fmtsec

pattern = re.compile(r"^fps\s*$")


class FPSConverter(Module):
    name = "FPS Converter"
    cmds = "<Reply to Video> fps"
    desc = {
        "Info": "Converts the replied video to 60 FPS using FFmpeg motion interpolation.",
        "e.g.": "<Reply to Video> fps",
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
        return "▰" * (percentage // 10) + "▱" * (10 - (percentage // 10))

    @listener.handler(filters.regex(pattern) & listener.fltrep, 1)
    async def on_convert_fps(self, event: Message) -> None:
        """Handles the video to 60 FPS conversion command."""
        replied_message = event.reply_to_message
        
        # Cek video dari berbagai sumber (video, animation, atau document)
        video = replied_message.video or replied_message.animation
        if not video and replied_message.document:
            mime = replied_message.document.mime_type or ""
            if mime.startswith("video/"):
                video = replied_message.document
        
        if not replied_message or not video:
            await event.edit_text("<code>Reply ke pesan video untuk mengkonversinya.</code>")
            return

        # Get duration, fallback to 0 if not available
        duration = getattr(video, 'duration', 0) or 0
        file_size = getattr(video, 'file_size', 0) or 0
        
        if duration > 120:
            await event.edit_text("<code>Durasi video melebihi batas 2 menit.</code>")
            return
        
        if file_size > 50 * 1024 * 1024:  # 50 MB
            await event.edit_text("<code>Ukuran file melebihi batas 50 MB.</code>")
            return

        await event.edit_text("<code>Processing...</code>")
        now = datetime.datetime.now(datetime.UTC)

        # Create a temporary directory for this conversion
        temp_dir = Path("downloads") / f"fps_converter_{event.id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        input_path = None
        output_path = None

        # Regex untuk menangkap informasi waktu dari output stderr FFmpeg
        time_pattern = re.compile(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})")

        try:
            # 1. Download the video
            await event.edit_text("<code>Downloading video...</code>")
            input_path = await replied_message.download(in_memory=False, file_name=str(temp_dir / "input.mp4"))
            
            if not input_path or not os.path.exists(input_path):
                raise Exception("Video download failed.")

            # 2. Convert the video using FFmpeg
            output_path = str(temp_dir / "output_60fps.mp4")

            # Optimized FFmpeg command for smooth 60 FPS conversion
            command = (
                f'ffmpeg -i "{input_path}" '
                f'-vf "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,scale=trunc(iw/2)*2:trunc(ih/2)*2" '
                f'-c:v libx264 -preset medium -crf 20 -profile:v high -level 4.1 '
                f'-movflags +faststart -pix_fmt yuv420p '
                f'-c:a aac -b:a 128k "{output_path}" -y'
            )

            self.logger.info(f"Executing FFmpeg command: {command}")

            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            last_update_time = 0
            stderr_output = ""
            
            while process.returncode is None:
                line_bytes = await process.stderr.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode('utf-8', errors='ignore').strip()
                stderr_output += line + "\n"
                
                match = time_pattern.search(line)
                if match:
                    current_time = self._parse_ffmpeg_time(match.group(1))
                    
                    # Safe percentage calculation
                    if duration > 0:
                        percentage = int((current_time / duration) * 100)
                    else:
                        # Estimate based on processed time
                        percentage = min(int(current_time * 10), 99)
                    
                    # Batasi persentase antara 0 dan 100
                    percentage = max(0, min(100, percentage))
                    
                    current_time_secs = time.time()
                    if current_time_secs - last_update_time > 5:
                        # Update progress setiap 5 detik untuk menghindari FloodWait
                        progress_bar = self._create_progress_bar(percentage)
                        try:
                            await event.edit_text(
                                f"<code>Converting to 60 FPS...\n"
                                f"[{progress_bar}] {percentage}%</code>"
                            )
                            last_update_time = current_time_secs
                        except FloodWait as e:
                            await asyncio.sleep(e.value)
                        except Exception:
                            pass # Abaikan error jika pesan sudah dihapus
            
            await process.wait()

            if process.returncode != 0:
                raise Exception(f"FFmpeg conversion failed.\n\nDetails:\n{stderr_output[-1000:]}")

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