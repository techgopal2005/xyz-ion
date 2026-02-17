import os
import re
import asyncio
import yt_dlp
import requests
from telethon import TelegramClient, events, types

# ================= CONFIG =================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

DOWNLOAD_PATH = "/tmp"
SESSION_NAME = "bot_session"

client = TelegramClient(SESSION_NAME, api_id, api_hash)
stop_flags = {}

# ================= HELPERS =================
def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|&]', "", name)

def parse_txt(file_path):
    links = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if ": http" in line:
                title = line.split(": http")[0].strip()
                url = "http" + line.split(": http")[1].strip()
                links.append((title, url))
    return links

def format_duration(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}" if h > 0 else f"{m:02}:{s:02}"


# ================= VIDEO DOWNLOAD WITH TELEGRAM PROGRESS =================
async def download_video(url, title, index_no, status_msg):
    safe_title = clean_filename(title)
    file_path = os.path.join(DOWNLOAD_PATH, f"{safe_title}.mp4")
    last_edit = 0

    def progress_hook(d):
        nonlocal last_edit
        if d['status'] == 'downloading':
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
            pct = int(d.get('downloaded_bytes', 0) * 100 / total_bytes)
            if pct - last_edit >= 5:
                asyncio.get_event_loop().create_task(
                    status_msg.edit(f"⬇ [{index_no}] Downloading {title}... {pct}%")
                )
                last_edit = pct
        elif d['status'] == 'finished':
            asyncio.get_event_loop().create_task(
                status_msg.edit(f"⬇ [{index_no}] Download complete, processing...")
            )

    base_opts = {
        "outtmpl": file_path,
        "merge_output_format": "mp4",
        "prefer_ffmpeg": True,
        "noplaylist": True,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 45,
        "overwrites": True,
        "quiet": True,
        "progress_hooks": [progress_hook],
        "http_headers": {"User-Agent": "Mozilla/5.0"},
    }

    # Prefer 720p, fallback to best available
    for fmt in [
        "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "bestvideo[height<=480]+bestaudio/best[height<=480]",
        "bestvideo+bestaudio/best"  # 🔹 fallback to any available
    ]:
        try:
            opts = base_opts.copy()
            opts["format"] = fmt
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            return file_path, info
        except Exception:
            continue

    # if all fails
    print(f"❌ FAILED INDEX: {index_no} | TITLE: {title}")
    raise Exception(f"Failed to download\nIndex: {index_no}\nTitle: {title}")

    # TRY 720P THEN 480P
    for fmt in [
        "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "bestvideo[height<=480]+bestaudio/best[height<=480]"
    ]:
        try:
            opts = base_opts.copy()
            opts["format"] = fmt
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            return file_path, info
        except Exception:
            continue

    print(f"❌ FAILED INDEX: {index_no} | TITLE: {title}")
    raise Exception(f"Both 720p & 480p failed\nIndex: {index_no}\nTitle: {title}")


# ================= COMMANDS =================
@client.on(events.NewMessage(pattern=r"^/start$"))
async def start_handler(event):
    await event.reply("🚀 Bot is running in this topic!")


@client.on(events.NewMessage(pattern=r"^/txt$"))
async def txt_handler(event):
    stop_flags[event.sender_id] = False
    await event.reply("📂 Send your TXT file. All PDFs & Videos will upload in this topic.")


@client.on(events.NewMessage(pattern=r"^/stop$"))
async def stop_handler(event):
    stop_flags[event.sender_id] = True
    await event.reply("🛑 Stopped!")


# ================= FILE HANDLER =================
@client.on(events.NewMessage)
async def file_handler(event):
    sender = event.sender_id

    if stop_flags.get(sender):
        return

    # TXT file handling
    if event.message.file and event.message.file.name.endswith(".txt"):
        path = await event.message.download_media(DOWNLOAD_PATH)
        links = parse_txt(path)

        await event.reply(
            f"🔍 Found {len(links)} links.\n🚀 Starting upload in this topic..."
        )

        for index, (title, url) in enumerate(links, start=1):

            if stop_flags.get(sender):
                await event.reply("🛑 Stopped!")
                break

            try:
                status_msg = await event.reply(f"⬇ [{index}] Processing {title}...")

                # ===== PDF =====
                if url.endswith(".pdf"):
                    safe_title = clean_filename(title)
                    file_path_pdf = os.path.join(DOWNLOAD_PATH, f"{safe_title}.pdf")

                    r = requests.get(url)
                    with open(file_path_pdf, "wb") as f:
                        f.write(r.content)

                    await client.send_file(
                        event.chat_id,
                        file_path_pdf,
                        caption=f"[{index}] {title}",
                        reply_to=event.id
                    )

                    os.remove(file_path_pdf)
                    await status_msg.edit(f"✅ [{index}] PDF Uploaded")
                    continue

                # ===== VIDEO =====
                file_path, info = await download_video(url, title, index, status_msg)
                duration = info.get("duration", 0)
                width = info.get("width", 1280)
                height = info.get("height", 720)

                # UPLOAD PROGRESS
                async def upload_progress(current, total):
                    pct = int(current * 100 / (total or 1))
                    await status_msg.edit(f"📤 [{index}] Uploading {title}... {pct}%")

                await client.send_file(
                    event.chat_id,
                    file_path,
                    caption=f"[{index}] {title}",
                    supports_streaming=True,
                    attributes=[
                        types.DocumentAttributeVideo(
                            duration=int(duration),
                            w=width,
                            h=height,
                            supports_streaming=True
                        )
                    ],
                    progress_callback=upload_progress,
                    reply_to=event.id
                )

                os.remove(file_path)
                await status_msg.edit(f"✅ [{index}] Uploaded")

            except Exception as e:
                await event.reply(f"❌ ERROR at Index {index}\nTitle: {title}\n{e}")
                continue

        await event.reply("🎉 All files processed!")


# ================= MAIN =================
async def main():
    await client.start(bot_token=bot_token)
    print("🚀 Bot Running...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
