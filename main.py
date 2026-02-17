
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

# Set your target group/channel and optional topic_id
TARGET_GROUP = os.getenv("TARGET_GROUP")  # example: -1001234567890 or "@groupusername"
TOPIC_ID = int(os.getenv("TOPIC_ID", 0))  # 0 if no topic

client = TelegramClient("bot", api_id, api_hash).start(bot_token=bot_token)

# ================= GLOBALS =================
user_links = {}
stop_flags = {}

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

def parse_txt(file_path):
    links = []
    total_pdf = total_video = 0
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if ": http" in line:
                title = line.split(": http")[0].strip()
                url = "http" + line.split(": http")[1].strip()
                links.append((title, url))
                if url.endswith(".pdf"):
                    total_pdf += 1
                else:
                    total_video += 1
    return links, total_video, total_pdf

# ================= DOWNLOAD =================
async def download_video(url):
    qualities = ["720", "480"]
    for q in qualities:
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
                "concurrent_fragment_downloads": 45,
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
    raise Exception("❌ Video download failed")

async def download_pdf(url, title):
    file_name = os.path.join(DOWNLOAD_PATH, f"{title}.pdf")
    r = requests.get(url, stream=True)
    total = int(r.headers.get("content-length", 0))
    with open(file_name, "wb") as f:
        downloaded = 0
        start = time.time()
        for chunk in r.iter_content(1024*1024):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                percent = int(downloaded * 100 / total) if total else 0
                now = time.time()
                if now - download_pdf.last_update > 1:
                    print(f"⬇ Downloading PDF {title}... {percent}%")
                    download_pdf.last_update = now
    download_pdf.last_update = 0
    return file_name
download_pdf.last_update = 0

# ================= BOT =================
@client.on(events.NewMessage(pattern="/txt"))
async def txt_handler(event):
    sender = event.sender_id
    if sender in user_links:
        return
    user_links[sender] = None
    stop_flags[sender] = False
    await event.reply(
        "➠ Send your TXT file in proper format:\n"
        "FORMAT: FILE NAME : URL\n"
        "Bot will upload all PDFs and videos to the group/topic."
    )

@client.on(events.NewMessage)
async def file_handler(event):
    sender = event.sender_id
    if sender not in user_links or stop_flags.get(sender):
        return

    # TXT file processing
    if event.message.file and event.message.file.name.endswith(".txt"):
        path = await event.message.download_media(DOWNLOAD_PATH)
        links, total_video, total_pdf = parse_txt(path)
        user_links[sender] = links

        if not links:
            await event.reply("❌ No valid links found in TXT.")
            return

        await event.reply(
            f"Found {len(links)} links ({total_video} videos, {total_pdf} PDFs).\n"
            f"Starting upload to group..."
        )

        thumbnail = download_thumbnail()

        for idx, (title, url) in enumerate(links, start=1):
            if stop_flags.get(sender):
                break
            try:
                status_msg = await event.reply(f"⬇ Processing {title}...")
                if url.endswith(".pdf"):
                    file_path = await download_pdf(url, title)
                    await client.send_file(
                        TARGET_GROUP,
                        file_path,
                        caption=f"📄 {title}",
                        force_document=True,
                        reply_to=TOPIC_ID if TOPIC_ID else None
                    )
                else:
                    try:
                        file_path, duration, width, height = await download_video(url)
                        formatted_duration = format_duration(duration)
                        await client.send_file(
                            TARGET_GROUP,
                            file_path,
                            caption=f"🎬 {title}\n⏱ Duration: {formatted_duration}",
                            thumb=thumbnail,
                            supports_streaming=True,
                            attributes=[types.DocumentAttributeVideo(
                                duration=int(duration),
                                w=width,
                                h=height,
                                supports_streaming=True
                            )],
                            progress_callback=lambda cur, total: print(f"⬇ Downloading {title}: {int(cur*100/total)}%")
                        )
                    except Exception:
                        await event.reply(f"❌ FAILED INDEX: {idx} | TITLE: {title}")
                        continue
                # cleanup
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                await event.reply(f"❌ Error: {str(e)}")
        user_links.pop(sender, None)
        stop_flags.pop(sender, None)

print("🚀 Bot Running...")
client.run_until_disconnected()
