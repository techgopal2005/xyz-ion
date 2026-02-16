import os
import asyncio
import yt_dlp
import traceback
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeVideo

# ================== ENV CONFIG ==================
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not API_ID or not API_HASH or not BOT_TOKEN:
    raise ValueError("Missing API_ID, API_HASH or BOT_TOKEN in Railway Variables")

API_ID = int(API_ID)

SESSION_NAME = "railway_bot"
DOWNLOAD_PATH = "/tmp"

os.makedirs(DOWNLOAD_PATH, exist_ok=True)

# Start bot
client = TelegramClient(SESSION_NAME, API_ID, API_HASH).start(bot_token=BOT_TOKEN)

PENDING = {}

print("🚀 Railway DRM Bot Started...")


# ================== UPLOAD PROGRESS ==================
async def upload_progress(current, total, message):
    if not total:
        return

    percent = round(current * 100 / total, 2)
    filled = int(percent // 5)
    bar = "█" * filled + "░" * (20 - filled)

    try:
        await message.edit(f"📤 Uploading...\n[{bar}] {percent}%")
    except:
        pass


# ================== /drm COMMAND ==================
@client.on(events.NewMessage(pattern=r'^/drm'))
async def drm_handler(event):
    parts = event.raw_text.strip().split(maxsplit=1)

    if len(parts) < 2:
        await event.reply("❌ Usage:\n/drm <video_link>")
        return

    PENDING[event.chat_id] = parts[1]
    await event.reply("🎬 Reply with quality:\nSend 720 or 1080")


# ================== QUALITY HANDLER ==================
@client.on(events.NewMessage)
async def quality_handler(event):
    try:
        if event.chat_id not in PENDING:
            return

        if event.raw_text.strip() not in ["720", "1080"]:
            return

        quality = event.raw_text.strip()
        url = PENDING[event.chat_id]

        msg = await event.reply("⏳ Downloading...")

        format_string = (
            f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]"
        )

        ydl_opts = {
            "format": format_string,
            "outtmpl": os.path.join(DOWNLOAD_PATH, "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "quiet": True,
            "noplaylist": True,
            "concurrent_fragment_downloads": 5,
            "ffmpeg_location": "ffmpeg"
        }

        # DOWNLOAD
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

        if not file_path.endswith(".mp4"):
            file_path = os.path.splitext(file_path)[0] + ".mp4"

        # Safe edit
        try:
            await msg.edit("✅ Download Complete!\n📤 Uploading...")
        except:
            pass

        # File size check
        file_size = os.path.getsize(file_path)
        print("File size MB:", file_size / (1024 * 1024))

        if file_size > 2 * 1024 * 1024 * 1024:
            await event.reply("❌ File too large (Over 2GB Telegram limit)")
            return

        # UPLOAD
        await client.send_file(
            event.chat_id,
            file_path,
            supports_streaming=True,
            attributes=[
                DocumentAttributeVideo(
                    duration=0,
                    w=0,
                    h=0,
                    supports_streaming=True
                )
            ],
            progress_callback=lambda c, t: asyncio.create_task(
                upload_progress(c, t, msg)
            )
        )

        try:
            await msg.edit("✅ Upload Complete!")
        except:
            pass

        # Delete file
        if os.path.exists(file_path):
            os.remove(file_path)

        del PENDING[event.chat_id]

    except Exception:
        print(traceback.format_exc())
        await event.reply("❌ Error occurred.")


# ================== RUN BOT ==================
client.run_until_disconnected()
