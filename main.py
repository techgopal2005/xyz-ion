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

async def download_video(url, title):
    safe_title = clean_filename(title)

    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": os.path.join(DOWNLOAD_PATH, f"{safe_title}.%(ext)s"),
        "merge_output_format": "mp4",
        "prefer_ffmpeg": True,
        "noplaylist": True,
        "overwrites": True,
        "quiet": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    file_path = os.path.join(DOWNLOAD_PATH, f"{safe_title}.mp4")
    duration = info.get("duration", 0)
    width = info.get("width", 1280)
    height = info.get("height", 720)

    return file_path, duration, width, height

# ================= COMMANDS =================
@client.on(events.NewMessage(pattern=r"^/start$"))
async def start_handler(event):
    await event.reply("🚀 Bot is running in this topic!")

@client.on(events.NewMessage(pattern=r"^/txt$"))
async def txt_handler(event):
    stop_flags[event.sender_id] = False
    await event.reply("📂 Send TXT file. All PDFs & Videos will upload in this topic.")

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

    if event.message.file and event.message.file.name.endswith(".txt"):

        topic_id = event.message.reply_to_msg_id  # important for topic

        path = await event.message.download_media(DOWNLOAD_PATH)
        links = parse_txt(path)

        await event.reply(
            f"🔍 Found {len(links)} links.\n🚀 Starting upload in this topic..."
        )

        for title, url in links:

            if stop_flags.get(sender):
                await event.reply("🛑 Stopped!")
                break

            try:
                status = await event.reply(f"⬇ Downloading {title}...")

                # ===== PDF =====
                if url.endswith(".pdf"):
                    safe_title = clean_filename(title)
                    file_path = os.path.join(DOWNLOAD_PATH, f"{safe_title}.pdf")

                    r = requests.get(url)
                    with open(file_path, "wb") as f:
                        f.write(r.content)

                    await client.send_file(
                        event.chat_id,
                        file_path,
                        caption=title,
                        reply_to=event.id
                    )

                    os.remove(file_path)
                    await status.edit(f"✅ PDF Uploaded: {title}")
                    continue

                # ===== VIDEO =====
                file_path, duration, width, height = await download_video(url, title)

                await client.send_file(
                    event.chat_id,
                    file_path,
                    caption=title,
                    supports_streaming=True,
                    attributes=[
                        types.DocumentAttributeVideo(
                            duration=int(duration),
                            w=width,
                            h=height,
                            supports_streaming=True
                        )
                    ],
                    reply_to=event.id
                )

                os.remove(file_path)
                await status.edit(f"✅ Uploaded: {title}")

            except Exception as e:
                await event.reply(f"❌ Failed: {title}\n{e}")
                continue

        await event.reply("🎉 All files uploaded in this topic!")

# ================= MAIN =================
async def main():
    await client.start(bot_token=bot_token)
    print("🚀 Bot Running...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
