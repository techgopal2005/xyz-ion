import os
import asyncio
import yt_dlp
import time
import requests
from telethon import TelegramClient, events, types
from telethon.errors import FloodWaitError

# ================= CONFIG =================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
DOWNLOAD_PATH = "/tmp"
THUMB_URL = "https://static.pw.live/5eb393ee95fab7468a79d189/ADMIN/6e008265-fef8-4357-a290-07e1da1ff964.png"

# ================= SAFE BOT START =================
client = TelegramClient("bot_session", API_ID, API_HASH)

async def safe_start():
    try:
        await client.start(bot_token=BOT_TOKEN)
    except FloodWaitError as e:
        print(f"FloodWait: wait {e.seconds} seconds")
        exit(1)

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
    if quality == "1080":
        format_string = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
    elif quality == "720":
        format_string = "bestvideo[height<=720]+bestaudio/best[height<=720]"
    else:
        format_string = "bestvideo[height<=480]+bestaudio/best[height<=480]"

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
        return file_path, info.get("duration", 0), info.get("width", 1280), info.get("height", 720), info.get("title", "")

# ================= GLOBALS =================
user_links = {}
user_txt = {}
stop_flags = {}

# ================= BOT HANDLERS =================
@client.on(events.NewMessage(pattern="/drm"))
async def drm_handler(event):
    try:
        url = event.text.split(" ", 1)[1]
        user_links[event.sender_id] = url
        await event.reply("🎬 Send quality: 720 or 1080")
    except:
        await event.reply("❌ Use:\n/drm your_link_here")

@client.on(events.NewMessage(pattern="/txt"))
async def txt_handler(event):
    sender = event.sender_id
    if sender in user_txt:
        return  # already prompted
    user_txt[sender] = None
    await event.reply(
        "➠ 𝐒𝐞𝐧𝐝 𝐌𝐞 𝐘𝐨𝐮𝐫 𝐓𝐗𝐓 𝐅𝐢𝐥𝐞 𝐢𝐧 𝐀 𝐏𝐫𝐨𝐩𝐞𝐫 𝐖𝐚𝐲\n\n"
        "➠ TXT FORMAT : FILE NAME : URL/LINK\n"
        "➠ 𝐌𝐨𝐝𝐢𝐟𝐢𝐞𝐝 𝐁𝐲: @do_land_trump"
    )

@client.on(events.NewMessage)
async def txt_file_handler(event):
    sender = event.sender_id
    if sender not in user_txt or user_txt[sender] is not None:
        return

    if not event.file or not event.file.name.endswith(".txt"):
        await event.reply("❌ Please send a proper TXT file.")
        return

    path = await event.download_media(file=os.path.join(DOWNLOAD_PATH, f"{sender}_links.txt"))
    links = []
    video_count = 0
    pdf_count = 0

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if ": http" in line or ": https" in line:
                title = line.split(":", 1)[0].strip()
                url = line.split(":", 2)[-1].strip()
                links.append({"title": title, "url": url})
                if url.endswith(".mpd"):
                    video_count += 1
                elif url.endswith(".pdf"):
                    pdf_count += 1

    user_txt[sender] = links
    stop_flags[sender] = False

    await event.reply(
        f"Total links found: {len(links)}\n"
        f"┃\n"
        f"┠ Total Video Count: {video_count}\n"
        f"┠ Total Pdf Count: {pdf_count}\n"
        f"┠ Send From where you want to download initial is: 1\n"
        f"┃\n"
        f"┠ Send /stop if you don't want to continue\n"
        f"┖ Bot By: @do_land_trump"
    )

@client.on(events.NewMessage(pattern="/stop"))
async def stop_handler(event):
    sender = event.sender_id
    stop_flags[sender] = True
    await event.reply("🛑 Stopped all processes.")

@client.on(events.NewMessage)
async def quality_and_download(event):
    sender = event.sender_id
    if sender not in user_links and sender not in user_txt:
        return

    # DRM handler
    if sender in user_links and event.text in ["720", "1080"]:
        quality = event.text
        url = user_links[sender]
        status_msg = await event.reply("⬇ Downloading...")
        try:
            file_path, duration, width, height, title = await download_video(url, quality)
            thumbnail = download_thumbnail()
            formatted_duration = format_duration(duration)

            async def progress(current, total):
                percent = int(current * 100 / total)
                bar = "█" * (percent // 5) + "-" * (20 - percent // 5)
                try:
                    await status_msg.edit(f"📤 Uploading... |{bar}| {percent}%")
                except:
                    pass

            await client.send_file(
                event.chat_id,
                file_path,
                caption=f"{title}\n⏱ Duration: {formatted_duration}",
                thumb=thumbnail,
                supports_streaming=True,
                attributes=[types.DocumentAttributeVideo(duration=int(duration), w=width, h=height)],
                progress_callback=progress
            )

            await status_msg.edit("✅ Upload Complete!")

        except Exception as e:
            await status_msg.edit(f"❌ Failed: {str(e)}")

        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
            if os.path.exists(thumbnail):
                os.remove(thumbnail)
            del user_links[sender]

# ================= RUN BOT =================
async def main():
    await safe_start()
    print("🚀 Bot Running...")
    await client.run_until_disconnected()

asyncio.run(main())
