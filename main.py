import os
import asyncio
import yt_dlp
import time
import requests

from telethon import TelegramClient, events, types

# ================= CONFIG =================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

DOWNLOAD_PATH = "/tmp"
THUMB_URL = "https://static.pw.live/5eb393ee95fab7468a79d189/ADMIN/6e008265-fef8-4357-a290-07e1da1ff964.png"

client = TelegramClient("bot", api_id, api_hash).start(bot_token=bot_token)

# ================= HELPERS =================
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

def download_pdf(url):
    local_filename = os.path.join(DOWNLOAD_PATH, url.split("/")[-1].split("?")[0])
    r = requests.get(url, stream=True)
    r.raise_for_status()
    with open(local_filename, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return local_filename

# ================= DOWNLOAD =================
async def download_video(url, quality):
    loop = asyncio.get_event_loop()

    def run():
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
            "concurrent_fragment_downloads": 10,
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

    return await loop.run_in_executor(None, run)

# ================= BOT =================
user_links = {}

@client.on(events.NewMessage(pattern="/drm"))
async def drm_handler(event):
    try:
        url = event.text.split(" ", 1)[1]
        user_links[event.sender_id] = url

        if ".pdf" in url.lower():
            await event.reply("📄 PDF detected. Downloading...")
            await handle_pdf(event, url)
        else:
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

        # Check Telegram size limit
        file_size = os.path.getsize(file_path)
        if file_size > 1900 * 1024 * 1024:
            await status_msg.edit("❌ File too large for Telegram (over 2GB).")
            os.remove(file_path)
            return

        formatted_duration = format_duration(duration)
        thumbnail = download_thumbnail()

        await status_msg.edit("📤 Uploading...")

        async def progress(current, total):
            percent = int(current * 100 / total)
            now = time.time()
            if now - progress.last_update > 10:
                try:
                    await status_msg.edit(f"📤 Uploading... {percent}%")
                    progress.last_update = now
                except:
                    pass

        progress.last_update = 0

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
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        await status_msg.edit(f"❌ Error:\n{str(e)}")

# ================= PDF HANDLER =================
async def handle_pdf(event, url):
    status_msg = await event.reply("⬇ Downloading PDF...")

    try:
        file_path = download_pdf(url)
        await status_msg.edit("📤 Uploading PDF...")

        await client.send_file(
            event.chat_id,
            file_path,
            caption="✅ PDF Upload Complete!"
        )

        await status_msg.edit("✅ PDF Upload Complete!")

        if os.path.exists(file_path):
            os.remove(file_path)

        del user_links[event.sender_id]

    except Exception as e:
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        await status_msg.edit(f"❌ Error:\n{str(e)}")

print("🚀 Bot Running...")
client.run_until_disconnected()
