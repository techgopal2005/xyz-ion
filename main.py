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

# ================= GLOBAL STATE =================
user_sessions = {}  # key: (user_id, thread_id) -> session dict

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

async def download_video(url, quality):
    """Try download in quality order: 1080 → 720 → 480"""
    qualities = {"1080": [1080, 720, 480], "720": [720, 480], "480": [480]}
    attempts = qualities.get(quality, [720, 480])

    for q in attempts:
        try:
            format_string = f"bestvideo[height<={q}]+bestaudio/best[height<={q}]"
            ydl_opts = {
                "format": format_string,
                "outtmpl": os.path.join(DOWNLOAD_PATH, "%(title)s.%(ext)s"),
                "merge_output_format": "mp4",
                "prefer_ffmpeg": True,
                "noplaylist": True,
                "quiet": True,
                "retries": 5,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)
                if not file_path.endswith(".mp4"):
                    file_path = file_path.rsplit(".", 1)[0] + ".mp4"
                return file_path, info.get("duration", 0), info.get("width", 1280), info.get("height", 720)
        except Exception:
            continue
    # if all fail
    raise Exception("Download failed in all qualities")

def parse_txt_lines(lines):
    """Return list of tuples: (title, url)"""
    result = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        idx = line.find(": http")
        if idx == -1:
            continue
        title = line[:idx].strip()
        url = line[idx+2:].strip()
        result.append((title, url))
    return result

def compute_counts(links):
    video_count = sum(1 for _, url in links if url.endswith(".mpd"))
    pdf_count = sum(1 for _, url in links if url.endswith(".pdf"))
    return video_count, pdf_count

# ================= COMMANDS =================
@client.on(events.NewMessage(pattern="/drm"))
async def drm_handler(event):
    key = (event.sender_id, getattr(event.message, "thread_id", None))
    if key in user_sessions and user_sessions[key].get("state") in ["waiting_quality", "downloading"]:
        return  # ignore duplicate
    try:
        url = event.text.split(" ", 1)[1]
        user_sessions[key] = {"state": "waiting_quality", "url": url, "stop": False}
        await event.reply("🎬 Send quality: 720 or 1080")
    except:
        await event.reply("❌ Use:\n/drm your_link_here")

@client.on(events.NewMessage(pattern="/txt"))
async def txt_handler(event):
    key = (event.sender_id, getattr(event.message, "thread_id", None))
    if key in user_sessions and user_sessions[key].get("state") == "waiting_file":
        return  # already waiting for file
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
    if not session or session["state"] != "waiting_file":
        return
    if not event.file or not event.file.name.endswith(".txt"):
        await event.reply("❌ Please send a proper TXT file.")
        return
    file_path = os.path.join(DOWNLOAD_PATH, f"{event.file.name}")
    await client.download_media(event.message, file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    links = parse_txt_lines(lines)
    video_count, pdf_count = compute_counts(links)
    session["links"] = links
    session["state"] = "waiting_start_index"
    await event.reply(
        f"Total links found: {len(links)}\n"
        f"┃\n"
        f"┠ Total Video Count: {video_count}\n"
        f"┠ Total PDF Count: {pdf_count}\n"
        f"┠ Send starting index to download (initial: 1)\n"
        f"┠ Send /stop to abort\n"
        f"┖ Bot By: @do_land_trump"
    )

@client.on(events.NewMessage(pattern="/stop"))
async def stop_handler(event):
    key = (event.sender_id, getattr(event.message, "thread_id", None))
    session = user_sessions.get(key)
    if session:
        session["stop"] = True
        await event.reply("🛑 Stopped!")

# ================= DOWNLOAD LOOP =================
async def process_links(key, chat_id):
    session = user_sessions[key]
    links = session["links"]
    for idx, (title, url) in enumerate(links):
        if session["stop"]:
            break
        try:
            status_msg = await client.send_message(chat_id, f"⬇ Downloading: {title}")
            file_path, duration, width, height = await download_video(url, "1080")
            thumb = download_thumbnail()

            # animated upload progress
            async def progress(current, total):
                percent = int(current*100/total)
                bar_len = 10
                filled = int(bar_len*percent/100)
                bar = "█"*filled + "-"*(bar_len-filled)
                await status_msg.edit(f"📤 Uploading [{bar}] {percent}%")

            await client.send_file(
                chat_id,
                file_path,
                caption=title,
                thumb=thumb,
                supports_streaming=True,
                attributes=[types.DocumentAttributeVideo(duration=int(duration), w=width, h=height, supports_streaming=True)],
                progress_callback=progress
            )
            await status_msg.edit("✅ Upload Complete!")
            os.remove(file_path)
            os.remove(thumb)
        except Exception:
            await client.send_message(chat_id, f"❌ Failed at index {idx+1} - {title}")
            break
    user_sessions.pop(key, None)

# ================= BOT RUN =================
print("🚀 Bot Running...")
client.run_until_disconnected()
