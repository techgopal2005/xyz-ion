import os
import asyncio
import yt_dlp
import traceback
from telethon import TelegramClient, events

# ================== CONFIG ==================
api_id = int(os.getenv("API_ID", 0))       # Your Telegram API ID
api_hash = os.getenv("API_HASH")           # Your Telegram API Hash
BOT_TOKEN = os.getenv("BOT_TOKEN")        # Your bot token
PREMIUM_USER_ID = int(os.getenv("PREMIUM_USER_ID", 0))  # Telegram user ID

DOWNLOAD_PATH = "/tmp"  # Railway ephemeral storage
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "")  # Leave blank to use system ffmpeg
# ============================================

os.makedirs(DOWNLOAD_PATH, exist_ok=True)

# ================== INIT TELETHON BOT ==================
client = TelegramClient("bot_session", api_id, api_hash).start(bot_token=BOT_TOKEN)
PENDING = {}

# ================== PROGRESS BAR FUNCTION ==================
async def progress_bar(current, total, message, action):
    if not total or total == 0:
        return
    percent = round(current * 100 / total, 2)
    filled = int(percent // 5)
    bar = "█" * filled + "░" * (20 - filled)
    try:
        await message.edit(f"{action}\n[{bar}] {percent}%")
    except:
        pass

# ================== /start COMMAND ==================
@client.on(events.NewMessage(pattern="/start"))
async def start_handler(event):
    if event.sender_id == PREMIUM_USER_ID:
        await event.reply("✅ YOU ARE A PREMIUM USER")
    else:
        await event.reply(
            "❌ YOU ARE NOT A PREMIUM SUBSCRIBER\n"
            "CONTACT [PROFESSOR](https://t.me/Do_land_trump)",
            link_preview=False
        )

# ================== /drm COMMAND ==================
@client.on(events.NewMessage(pattern=r'^/drm'))
async def drm_handler(event):
    if event.sender_id != PREMIUM_USER_ID:
        await event.reply(
            "❌ YOU ARE NOT A PREMIUM SUBSCRIBER\n"
            "CONTACT [PROFESSOR](https://t.me/Do_land_trump)",
            link_preview=False
        )
        return

    parts = event.raw_text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await event.reply("Usage:\n/drm <video_link>")
        return

    url = parts[1]
    PENDING[event.sender_id] = url
    await event.reply("Send quality:\n720 or 1080")

# ================== QUALITY HANDLER ==================
@client.on(events.NewMessage)
async def quality_handler(event):
    try:
        if event.sender_id != PREMIUM_USER_ID:
            return
        if event.sender_id not in PENDING:
            return
        if event.raw_text.strip() not in ["720", "1080"]:
            return

        quality = event.raw_text.strip()
        url = PENDING[event.sender_id]

        msg = await event.reply("⏳ Starting Download...")

        format_string = f"bestvideo[height<={quality}]+bestaudio/best"

        ydl_opts = {
            "format": format_string,
            "outtmpl": os.path.join(DOWNLOAD_PATH, "%(title)s.%(ext)s"),
            "ffmpeg_location": FFMPEG_PATH if FFMPEG_PATH else None,
            "merge_output_format": "mp4",
            "quiet": True,
            "progress_hooks": []
        }

        # DOWNLOAD PROGRESS HOOK
        def download_hook(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                downloaded = d.get('downloaded_bytes', 0)
                asyncio.create_task(progress_bar(downloaded, total, msg, "📥 Downloading..."))

        ydl_opts["progress_hooks"].append(download_hook)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            if not file_path.endswith(".mp4"):
                file_path = os.path.splitext(file_path)[0] + ".mp4"

        await msg.edit("✅ Download Complete!\n📤 Uploading...")

        await client.send_file(
            event.chat_id,
            file_path,
            progress_callback=lambda c, t: asyncio.create_task(progress_bar(c, t, msg, "📤 Uploading..."))
        )

        await msg.edit("✅ Upload Complete!")
        del PENDING[event.sender_id]

    except Exception:
        print(traceback.format_exc())
        await event.reply("❌ Error occurred.")

# ================== START BOT ==================
print("🤖 Premium DRM Bot Started...")
client.run_until_disconnected()
