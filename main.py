import os
import asyncio
import yt_dlp
import traceback
from telethon import TelegramClient, events

# ================== ENV CONFIG ==================
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not API_ID or not API_HASH or not BOT_TOKEN:
    raise ValueError("Missing API_ID, API_HASH or BOT_TOKEN in Railway Variables")

API_ID = int(API_ID)

SESSION_NAME = "render_bot"
DOWNLOAD_PATH = "/tmp"   # Railway temporary storage
# ================================================

os.makedirs(DOWNLOAD_PATH, exist_ok=True)

# Start bot directly with token (NO user login)
client = TelegramClient(SESSION_NAME, API_ID, API_HASH).start(bot_token=BOT_TOKEN)

PENDING = {}


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

    url = parts[1]
    PENDING[event.chat_id] = url

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
            f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={quality}]+bestaudio/best"
        )

        ydl_opts = {
            "format": format_string,
            "outtmpl": os.path.join(DOWNLOAD_PATH, "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "quiet": True,
            "noplaylist": True,
            "concurrent_fragment_downloads": 4
        }

        # DOWNLOAD
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

            if not file_path.endswith(".mp4"):
                file_path = os.path.splitext(file_path)[0] + ".mp4"

        await msg.edit("✅ Download Complete!\n📤 Uploading...")

        await client.send_file(
            event.chat_id,
            file_path,
            progress_callback=lambda c, t: asyncio.create_task(
                upload_progress(c, t, msg)
            )
        )

        await msg.edit("✅ Upload Complete!")

        # Delete file after upload (important for Railway)
        if os.path.exists(file_path):
            os.remove(file_path)

        del PENDING[event.chat_id]

    except Exception:
        print(traceback.format_exc())
        await event.reply("❌ Error occurred.")


# ================== RUN BOT ==================
print("🚀 Railway DRM Bot Started...")
client.run_until_disconnected()

