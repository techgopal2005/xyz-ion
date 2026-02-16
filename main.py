import os
import asyncio
import yt_dlp
import subprocess
import json
import time

from telethon import TelegramClient, events, types

# ================= CONFIG =================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

DOWNLOAD_PATH = "/tmp"

client = TelegramClient("bot", api_id, api_hash).start(bot_token=bot_token)

# ================= METADATA =================
def get_video_metadata(video_path):
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-show_streams",
            "-of", "json",
            video_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            return 0, 1280, 720

        info = json.loads(result.stdout)

        duration = int(float(info["format"]["duration"]))

        video_stream = next(
            (s for s in info["streams"] if s["codec_type"] == "video"),
            None
        )

        width = video_stream["width"]
        height = video_stream["height"]

        return duration, width, height

    except Exception as e:
        print("Metadata Error:", e)
        return 0, 1280, 720


def generate_thumbnail(video_path):
    thumb_path = video_path.replace(".mp4", ".jpg")

    try:
        subprocess.run([
            "ffmpeg",
            "-y",
            "-ss", "00:00:02",
            "-i", video_path,
            "-frames:v", "1",
            thumb_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if os.path.exists(thumb_path):
            return thumb_path
        return None

    except Exception as e:
        print("Thumbnail Error:", e)
        return None


# ================= DOWNLOAD =================
async def download_video(url, quality):

    if quality == "720":
        format_string = "bestvideo[height<=720]+bestaudio/best[height<=720]"
    else:
        format_string = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"

    ydl_opts = {
        "format": format_string,
        "outtmpl": os.path.join(DOWNLOAD_PATH, "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "prefer_ffmpeg": True,
        "noplaylist": True,
        "quiet": True,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 15,  # unchanged speed
        "postprocessors": [{
            "key": "FFmpegVideoRemuxer",
            "preferedformat": "mp4",
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info)

        if not file_path.endswith(".mp4"):
            file_path = file_path.rsplit(".", 1)[0] + ".mp4"

        return file_path


# ================= BOT =================
user_links = {}

@client.on(events.NewMessage(pattern="/drm"))
async def drm_handler(event):
    try:
        url = event.text.split(" ", 1)[1]
        user_links[event.sender_id] = url
        await event.reply("🎬 Send quality: 720 or 1080")
    except:
        await event.reply("❌ Use:\n/drm your_link_here")


@client.on(events.NewMessage)
async def quality_handler(event):
    if event.sender_id not in user_links:
        return

    if event.text not in ["720", "1080"]:
        return

    url = user_links[event.sender_id]
    quality = event.text

    status_msg = await event.reply("⬇ Downloading...")

    try:
        file_path = await download_video(url, quality)

        duration, width, height = get_video_metadata(file_path)
        thumbnail = generate_thumbnail(file_path)

        await status_msg.edit("📤 Uploading... 0%")

        async def progress(current, total):
            percent = int(current * 100 / total)
            now = time.time()

            if now - progress.last_update > 30:
                await status_msg.edit(f"📤 Uploading... {percent}%")
                progress.last_update = now

        progress.last_update = 0

        await client.send_file(
            event.chat_id,
            file_path,
            caption="✅ Upload Complete!",
            thumb=thumbnail,
            supports_streaming=True,
            attributes=[
                types.DocumentAttributeVideo(
                    duration=duration,
                    w=width,
                    h=height,
                    supports_streaming=True
                )
            ],
            progress_callback=progress
        )

        await status_msg.edit("✅ Upload Complete!")

        # cleanup
        if os.path.exists(file_path):
            os.remove(file_path)

        if thumbnail and os.path.exists(thumbnail):
            os.remove(thumbnail)

        del user_links[event.sender_id]

    except Exception as e:
        await status_msg.edit(f"❌ Error:\n{str(e)}")


print("🚀 Bot Running...")
client.run_until_disconnected()
