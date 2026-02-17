import os
import asyncio
import yt_dlp
import time
import requests

from telethon import TelegramClient, events, types

# ================= CONFIG =================
api_id = os.getenv("API_ID")
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

if not api_id or not api_hash or not bot_token:
    raise ValueError("❌ Please set API_ID, API_HASH, and BOT_TOKEN environment variables")

api_id = int(api_id)

DOWNLOAD_PATH = "/tmp"
THUMB_URL = "https://static.pw.live/5eb393ee95fab7468a79d189/ADMIN/6e008265-fef8-4357-a290-07e1da1ff964.png"

client = TelegramClient("bot", api_id, api_hash).start(bot_token=bot_token)

# ================= HELPER =================
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
    format_string = "bestvideo[height<=720]+bestaudio/best[height<=720]" if quality == "720" else "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
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

# ================= HANDLERS =================
user_links = {}   # For /drm users
txt_users = {}    # For /txt users

# ----- /drm command -----
@client.on(events.NewMessage(pattern="/drm"))
async def drm_handler(event):
    try:
        url = event.text.split(" ", 1)[1]
        user_links[event.sender_id] = url
        await event.reply("🎬 Send quality: 720 or 1080")
        raise events.StopPropagation
    except IndexError:
        await event.reply("❌ Use:\n/drm your_link_here")

@client.on(events.NewMessage(pattern="^(720|1080)$"))
async def quality_handler(event):
    if event.sender_id not in user_links:
        return
    url = user_links[event.sender_id]
    quality = event.text
    status_msg = await event.reply("⬇ Downloading...")
    try:
        file_path, duration, width, height = await download_video(url, quality)
        formatted_duration = format_duration(duration)
        thumbnail = download_thumbnail()
        await status_msg.edit("📤 Uploading...")

        async def progress(current, total):
            percent = int(current * 100 / total)
            now = time.time()
            new_text = f"📤 Uploading... {percent}%"
            if now - progress.last_update > 30 and new_text != progress.last_text:
                try:
                    await status_msg.edit(new_text)
                    progress.last_update = now
                    progress.last_text = new_text
                except:
                    pass

        progress.last_update = 0
        progress.last_text = ""

        await client.send_file(
            event.chat_id,
            file_path,
            caption=f"✅ Upload Complete!\n\n⏱ Duration: {formatted_duration}",
            thumb=thumbnail,
            supports_streaming=True,
            attributes=[types.DocumentAttributeVideo(
                duration=int(duration),
                w=width,
                h=height,
                supports_streaming=True
            )],
            progress_callback=progress
        )
        await status_msg.edit("✅ Upload Complete!")
    except Exception as e:
        await status_msg.edit(f"❌ Error:\n{str(e)}")
    finally:
        for f in [file_path, thumbnail]:
            if os.path.exists(f):
                os.remove(f)
        del user_links[event.sender_id]

# ----- /txt command -----
@client.on(events.NewMessage(pattern="/txt"))
async def txt_request_handler(event):
    txt_users[event.sender_id] = True
    await event.reply(
        "➠ 𝐒𝐞𝐧𝐝 𝐌𝐞 𝐘𝐨𝐮𝐫 𝐓𝐗𝐓 𝐅𝐢𝐥𝐞 𝐢𝐧 𝐀 𝐏𝐫𝐨𝐩𝐞𝐫 𝐖𝐚𝐲\n\n"
        "➠ TXT FORMAT : FILE NAME : URL/LINK\n"
        "➠ 𝐌𝐨𝐝𝐢𝐟𝐢𝐞𝐝 𝐁𝐲: @do_land_trump"
    )

@client.on(events.NewMessage)
async def txt_file_handler(event):
    if event.sender_id not in txt_users:
        return
    if not event.message.file or not event.message.file.name.lower().endswith(".txt"):
        await event.reply("❌ Please send a TXT file only.")
        return

    file_path = await event.download_media(file=DOWNLOAD_PATH)
    processed_lines = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if ":" not in line:
                    processed_lines.append(f"❌ Invalid format: {line}")
                    continue
                title, link = map(str.strip, line.split(":", 1))
                if not link.startswith("http://") and not link.startswith("https://"):
                    processed_lines.append(f"❌ Invalid URL: {line}")
                    continue
                processed_lines.append(f"✅ Title: {title}\n➡ Link: {link}\n")

        reply_text = "\n".join(processed_lines)
        if len(reply_text) > 4096:
            processed_file = os.path.join(DOWNLOAD_PATH, "processed.txt")
            with open(processed_file, "w", encoding="utf-8") as f:
                f.write(reply_text)
            await event.reply("✅ Processed TXT file:", file=processed_file)
            os.remove(processed_file)
        else:
            await event.reply(reply_text)
    except Exception as e:
        await event.reply(f"❌ Error processing file:\n{str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        del txt_users[event.sender_id]

# ================= RUN BOT =================
print("🚀 Bot Running...")
client.run_until_disconnected()
