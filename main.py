import os
import asyncio
import yt_dlp
import traceback
from telethon import TelegramClient, events

# ================== CONFIG ==================
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
PREMIUM_USER_ID = int(os.getenv("PREMIUM_USER_ID", 0))

DOWNLOAD_PATH = "/tmp"  # Railway ephemeral storage
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "")  # Leave empty to use system ffmpeg
# ============================================

os.makedirs(DOWNLOAD_PATH, exist_ok=True)

# ================== INIT BOT ==================
client = TelegramClient("bot_session", API_ID, API_HASH).start(bot_token=BOT_TOKEN)
PENDING = {}

# ================== PROGRESS BAR ==================
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
    if event.sender_id != PREMIUM_USER_ID:
        return
    if event.sender_id not in PENDING:
        return
    if event.raw_text.strip() not in ["720", "1080"]:
        return

    url = PENDING[event.sender_id]
    quality = event.raw_text.strip()

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

    try:
        # Download with yt-dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            if not file_path.endswith(".mp4"):
                file_path = os.path.splitext(file_path)[0] + ".mp4"

        await msg.edit("✅ Download Complete!\n📤 Uploading...")

        # UPLOAD WITH RETRY
        for attempt in range(3):
            try:
                await client.send_file(
                    event.chat_id,
                    file_path,
                    progress_callback=lambda c, t: asyncio.create_task(progress_bar(c, t, msg, "📤 Uploading...")),
                    part_size_kb=512,
                    allow_cache=False
                )
                break
            except Exception as e:
                print(f"Upload failed (attempt {attempt+1}), retrying...", e)
                await asyncio.sleep(2)
        else:
            await msg.edit("❌ Upload failed after 3 attempts.")
            del PENDING[event.sender_id]
            return

        await msg.edit("✅ Upload Complete!")
        del PENDING[event.sender_id]

    except Exception:
        print(traceback.format_exc())
        await msg.edit("❌ Error occurred during download/upload.")

# ================== START BOT ==================
print("🤖 Premium DRM Bot Started...")
client.run_until_disconnected()
