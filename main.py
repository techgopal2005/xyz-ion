import os
import asyncio
import yt_dlp
import requests
from telethon import TelegramClient, events, types

# ================= CONFIG =================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

DOWNLOAD_PATH = "/tmp"
THUMB_URL = "https://static.pw.live/5eb393ee95fab7468a79d189/ADMIN/6e008265-fef8-4357-a290-07e1da1ff964.png"
SESSION_NAME = "bot_session"

client = TelegramClient(SESSION_NAME, api_id, api_hash)

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
                elif url.endswith(".mpd") or url.endswith(".m3u8"):
                    total_video += 1
    return links, total_video, total_pdf

# ================= DOWNLOAD =================
async def download_video(url, quality):
    qualities = {"1080": "best[height<=1080]", "720": "best[height<=720]", "480": "best[height<=480]"}
    q_list = [quality] + [q for q in ["1080", "720", "480"] if q != quality]

    last_exception = None

    for q in q_list:
        try:
            ydl_opts = {
                "format": qualities[q],
                "outtmpl": os.path.join(DOWNLOAD_PATH, "%(title)s.%(ext)s"),
                "merge_output_format": "mp4",
                "prefer_ffmpeg": True,
                "noplaylist": True,
                "quiet": False,
                "retries": 10,
                "fragment_retries": 10,
                "concurrent_fragment_downloads": 15,
                "nocheckcertificate": True,
                "allow_unplayable_formats": True,
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
                }
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
        except Exception as e:
            last_exception = e
            continue

    raise Exception(f"All qualities failed: {last_exception}")

# ================= BOT HANDLERS =================
@client.on(events.NewMessage(pattern=r"^/start$"))
async def start_handler(event):
    await event.respond("🚀 Bot is running!")

@client.on(events.NewMessage(pattern=r"^/stop$"))
async def stop_handler(event):
    stop_flags[event.sender_id] = True
    await event.respond("🛑 Process stopped!")

@client.on(events.NewMessage(pattern=r"^/txt$"))
async def txt_handler(event):
    sender = event.sender_id
    if sender in user_links:
        return
    user_links[sender] = None
    stop_flags[sender] = False
    await event.respond(
        "➠ Send your TXT file in format:\n\n"
        "FILE NAME : URL\n"
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
            await event.respond("❌ No valid links found in TXT.")
            return

        await event.respond(
            f"Total links found: {len(links)}\n"
            f"┃\n"
            f"┠ Total Video Count: {total_video}\n"
            f"┠ Total PDF Count: {total_pdf}\n"
            f"┖ Send starting number to begin download (example: 1)"
        )
        return

    # Starting number input
    if user_links[sender] and event.text.isdigit():
        start_idx = int(event.text) - 1
        links = user_links[sender]
        thumbnail = download_thumbnail()

        for idx, (title, url) in enumerate(links[start_idx:], start=start_idx):
            if stop_flags.get(sender):
                await event.respond("🛑 Process stopped!")
                break
            try:
                status_msg = await event.respond(f"⬇ Downloading {title}...")

                # ======= PDF =======
                if url.endswith(".pdf"):
                    file_path = os.path.join(DOWNLOAD_PATH, f"{title}.pdf")
                    r = requests.get(url)
                    with open(file_path, "wb") as f:
                        f.write(r.content)

                    await client.send_file(
                        event.chat_id,
                        file_path,
                        caption=title
                    )
                    await status_msg.edit(f"✅ PDF Uploaded: {title}")
                    os.remove(file_path)
                    continue

                # ======= VIDEO =======
                file_path, duration, width, height = await download_video(url, "1080")
                formatted_duration = format_duration(duration)

                async def progress(current, total):
                    percent = int(current * 100 / total)
                    await status_msg.edit(f"📤 Uploading {title}... {percent}%")

                await client.send_file(
                    event.chat_id,
                    file_path,
                    caption=title,
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

                await status_msg.edit(f"✅ Upload Complete: {title}")
                os.remove(file_path)

            except Exception as e:
                await event.respond(f"❌ Failed at index {idx+1}: {title}\n{e}")
                continue  # Skip broken links and continue

        user_links.pop(sender, None)
        stop_flags.pop(sender, None)

# ================= MAIN =================
async def main():
    await client.start(bot_token=bot_token)
    print("🚀 Bot Running...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
