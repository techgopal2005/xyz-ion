import os
import asyncio
import yt_dlp
import time
import requests
import re

from telethon import TelegramClient, events, types

# ================= CONFIG =================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

DOWNLOAD_PATH = "/tmp"
THUMB_URL = "https://static.pw.live/5eb393ee95fab7468a79d189/ADMIN/6e008265-fef8-4357-a290-07e1da1ff964.png"

client = TelegramClient("bot", api_id, api_hash).start(bot_token=bot_token)


# ================= HELPERS =================
def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|&]', "", name)


def format_duration(seconds):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}" if h > 0 else f"{m:02}:{s:02}"


def download_thumbnail():
    thumb_path = os.path.join(DOWNLOAD_PATH, "thumb.jpg")
    r = requests.get(THUMB_URL)
    with open(thumb_path, "wb") as f:
        f.write(r.content)
    return thumb_path


# ================= DOWNLOAD WITH PROGRESS =================
async def download_video(url, quality, status_msg):

    safe_title = "video"
    file_template = os.path.join(DOWNLOAD_PATH, "%(title)s.%(ext)s")

    last_edit = 0

    def progress_hook(d):
        nonlocal last_edit
        if d['status'] == 'downloading':
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 1
            downloaded = d.get("downloaded_bytes", 0)
            percent = int(downloaded * 100 / total)

            if percent - last_edit >= 5:
                asyncio.get_event_loop().create_task(
                    status_msg.edit(f"⬇ Downloading... {percent}%")
                )
                last_edit = percent

        elif d['status'] == 'finished':
            asyncio.get_event_loop().create_task(
                status_msg.edit("⬇ Download complete, processing...")
            )

    # Preferred format order
    format_list = [
        "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "bestvideo+bestaudio/best"
    ]

    ydl_base = {
        "outtmpl": file_template,
        "merge_output_format": "mp4",
        "prefer_ffmpeg": True,
        "noplaylist": True,
        "quiet": True,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 45,  # 🔥 increased
        "progress_hooks": [progress_hook],
        "http_headers": {"User-Agent": "Mozilla/5.0"},
    }

    for fmt in format_list:
        try:
            opts = ydl_base.copy()
            opts["format"] = fmt

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)

                file_path = ydl.prepare_filename(info)
                if not file_path.endswith(".mp4"):
                    file_path = file_path.rsplit(".", 1)[0] + ".mp4"

                duration = info.get("duration", 0)
                width = info.get("width", 1280)
                height = info.get("height", 720)

                return file_path, duration, width, height

        except Exception:
            continue

    raise Exception("Failed in all quality attempts (720/480/best)")


# ================= BOT =================
user_links = {}


@client.on(events.NewMessage(pattern="/drm"))
async def drm_handler(event):
    try:
        url = event.text.split(" ", 1)[1]
        user_links[event.sender_id] = url
        await event.reply("🎬 Send quality: 720 or 1080\n(Default = 720)")
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

    status_msg = await event.reply("⬇ Starting Download...")

    try:
        # DOWNLOAD
        file_path, duration, width, height = await download_video(
            url, quality, status_msg
        )

        formatted_duration = format_duration(duration)
        thumbnail = download_thumbnail()

        await status_msg.edit("📤 Uploading...")

        # UPLOAD PROGRESS
        async def upload_progress(current, total):
            percent = int(current * 100 / total)
            await status_msg.edit(f"📤 Uploading... {percent}%")

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
            progress_callback=upload_progress
        )

        await status_msg.edit("✅ Upload Complete!")

        # Cleanup
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(thumbnail):
            os.remove(thumbnail)

        del user_links[event.sender_id]

    except Exception as e:
        await status_msg.edit(f"❌ Error:\n{str(e)}")


print("🚀 Bot Running...")
client.run_until_disconnected()
