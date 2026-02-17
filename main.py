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

# ================= STATE =================
# Track user sessions
user_sessions = {}

# ================= HELPERS =================
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

async def download_video(url, preferred_quality):
    # Quality fallback list
    quality_order = ["1080", "720", "480"]
    start_idx = quality_order.index(preferred_quality)
    quality_order = quality_order[start_idx:]

    for q in quality_order:
        try:
            format_string = f"bestvideo[height<={q}]+bestaudio/best[height<={q}]"
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
        except Exception:
            continue
    raise Exception("All quality downloads failed")

# ================= /drm DOWNLOAD =================
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

        # Animated progress
        async def progress(current, total):
            percent = int(current * 100 / total)
            bar_length = 20
            filled = int(bar_length * percent / 100)
            bar = "█" * filled + "─" * (bar_length - filled)
            now = time.time()
            new_text = f"📤 Uploading: |{bar}| {percent}%"
            if now - progress.last_update > 1:
                try:
                    await status_msg.edit(new_text)
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
        os.remove(file_path)
        os.remove(thumbnail)
        del user_links[event.sender_id]
    except Exception as e:
        await status_msg.edit(f"❌ Error:\n{str(e)}")

# ================= /txt HANDLER =================
@client.on(events.NewMessage(pattern="/txt"))
async def txt_handler(event):
    key = (event.sender_id, getattr(event.message, "thread_id", None))
    if key in user_sessions and user_sessions[key].get("state") == "waiting_file":
        return  # Already waiting
    user_sessions[key] = {"state": "waiting_file", "links": [], "stop": False}
    await event.reply(
        "➠ 𝐒𝐞𝐧𝐝 𝐌𝐞 𝐘𝐨𝐮𝐫 𝐓𝐗𝐓 𝐅𝐢𝐥𝐞 𝐢𝐧 𝐀 𝐏𝐫𝐨𝐩𝐞𝐫 𝐖𝐚𝐲\n\n"
        "➠ TXT FORMAT : FILE NAME : URL/LINK\n"
        "➠ 𝐌𝐨𝐝𝐢𝐟𝐢𝐞𝐝 𝐁𝐲: @do_land_trump"
    )

@client.on(events.NewMessage)
async def file_handler(event):
    key = (event.sender_id, getattr(event.message, "thread_id", None))
    session = user_sessions.get(key)
    if not session or session.get("state") != "waiting_file":
        return

    if not event.file or not event.file.name.endswith(".txt"):
        await event.reply("❌ Please send a proper TXT file.")
        return

    # Download and parse TXT
    file_path = os.path.join(DOWNLOAD_PATH, event.file.name)
    await client.download_media(event.message, file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    links = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        idx = line.find(": http")
        if idx == -1:
            continue
        title = line[:idx].strip()
        url = line[idx+2:].strip()
        links.append((title, url))

    session["links"] = links
    session["state"] = "ready"

    video_count = sum(1 for _, url in links if url.endswith(".mpd"))
    pdf_count = sum(1 for _, url in links if url.endswith(".pdf"))

    await event.reply(
        f"Total links found: {len(links)}\n"
        f"┃\n"
        f"┠ Total Video Count: {video_count}\n"
        f"┠ Total PDF Count: {pdf_count}\n"
        f"┠ Send starting index to download (initial: 1)\n"
        f"┠ Send /stop to abort\n"
        f"┖ Bot By: @do_land_trump"
    )

# ================= /stop =================
@client.on(events.NewMessage(pattern="/stop"))
async def stop_handler(event):
    key = (event.sender_id, getattr(event.message, "thread_id", None))
    session = user_sessions.get(key)
    if session:
        session["stop"] = True
        await event.reply("🛑 Stopped ✅")

# ================= BOT RUN =================
print("🚀 Bot Running...")
client.run_until_disconnected()
