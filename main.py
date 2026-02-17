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

# ================= DOWNLOAD VIDEO =================
async def download_video(url, quality="1080"):
    qualities = {"1080": "best[height<=1080]", "720": "best[height<=720]", "480": "best[height<=480]"}
    q_list = [quality] + [q for q in ["1080", "720", "480"] if q != quality]

    last_exception = None

    for q in q_list:
        try:
            ydl_opts = {
                "format": qualities[q],
                "outtmpl": os.path.join(DOWNLOAD_PATH, "%(title)s_%(id)s.%(ext)s"),
                "merge_output_format": "mp4",
                "prefer_ffmpeg": True,
                "noplaylist": True,
                "quiet": False,
                "retries": 10,
                "fragment_retries": 10,
                "concurrent_fragment_downloads": 10,
                "nocheckcertificate": True,
                "overwrites": True,
                "http_headers": {"User-Agent": "Mozilla/5.0"}
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
    await event.respond("🚀 Bot is running! Send /txt to upload your TXT file with links.")

@client.on(events.NewMessage(pattern=r"^/stop$"))
async def stop_handler(event):
    stop_flags[event.sender_id] = True
    await event.respond("🛑 Process stopped!")

@client.on(events.NewMessage(pattern=r"^/txt$"))
async def txt_handler(event):
    sender = event.sender_id
    stop_flags[sender] = False
    await event.respond(
        "➠ Send your TXT file in the following format:\n\n"
        "FILE NAME : URL\n"
        "All PDFs and videos in the TXT will be uploaded automatically."
    )

@client.on(events.NewMessage)
async def file_handler(event):
    sender = event.sender_id
    if stop_flags.get(sender):
        return

    if event.message.file and event.message.file.name.endswith(".txt"):
        path = await event.message.download_media(DOWNLOAD_PATH)
        links, total_video, total_pdf = parse_txt(path)
        thumbnail = download_thumbnail()

        if not links:
            await event.respond("❌ No valid links found in TXT.")
            return

        await event.respond(
            f"📄 Total Links: {len(links)}\n"
            f"🎬 Videos: {total_video}\n"
            f"📕 PDFs: {total_pdf}\n"
            f"🚀 Starting automatic upload..."
        )

        for idx, (title, url) in enumerate(links, start=1):
            if stop_flags.get(sender):
                await event.respond("🛑 Process stopped!")
                break
            try:
                status_msg = await event.respond(f"⬇ Downloading {title}...")

                # PDF
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

                # Video
                file_path, duration, width, height = await download_video(url)
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
                await event.respond(f"❌ Failed at index {idx}: {title}\n{e}")
                continue

        await event.respond("🎉 All files processed!")

# ================= MAIN =================
async def main():
    await client.start(bot_token=bot_token)
    print("🚀 Bot Running...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
