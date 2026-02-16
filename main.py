import os
import asyncio
import yt_dlp
import time
import math
import requests

from telethon import TelegramClient, events, types

# ================= CONFIG =================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

DOWNLOAD_PATH = "/tmp"
THUMB_URL = "https://static.pw.live/5eb393ee95fab7468a79d189/ADMIN/6e008265-fef8-4357-a290-07e1da1ff964.png"

client = TelegramClient("bot", api_id, api_hash).start(bot_token=bot_token)


# ================= HELPER =================
def format_duration(seconds):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60

    if h > 0:
        return f"{h:02}:{m:02}:{s:02}"
    return f"{m:02}:{s:02}"


def download_thumbnail():
    thumb_path = os.path.join(DOWNLOAD_PATH, "thumb.jpg")
    r = requests.get(THUMB_URL)
    with open(thumb_path, "wb") as f:
        f.write(r.content)
    return thumb_path


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
        "concurrent_fragment_downloads": 15,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        file_path = ydl.prepare_filename(info)
        if not file_path.endswith(".mp4"):
            file_path = file_path.rsplit(".", 1)[0] + ".mp4"

        duration = info.get("duration", 0)
        width = info.get("width", 1280)
        height = info.get("height", 720)

        return file_path, duration, width, height


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
        file_path, duration, width, height = await download_video(url, quality)

        formatted_duration = format_duration(duration)
        thumbnail = download_thumbnail()

        await status_msg.edit("📤 Uploading...")

        async def progress(current, total):
            percent = int(current * 100 / total)
            now = time.time()
            new_text = f"📤 Uploading... {percent}%"

            if now - progress.last_update > 30 and new_text != progress.last_text:
                try:
                    await status_msg.edit(new_text)
                    progress.last_update = now
                    progress.last_text = new_text
                except:
                    pass

        progress.last_update = 0
        progress.last_text = ""

        await client.send_file(
            event.chat_id,
            file_path,
            caption=f"✅ Upload Complete!\n\n⏱ Duration: {formatted_duration}",
            thumb=thumbnail,
            supports_streaming=True,
            attributes=[
                types.DocumentAttributeVideo(
                    duration=int(duration),
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
        if os.path.exists(thumbnail):
            os.remove(thumbnail)

        del user_links[event.sender_id]

    except Exception as e:
        await status_msg.edit(f"❌ Error:\n{str(e)}")


print("🚀 Bot Running...")
client.run_until_disconnected()
