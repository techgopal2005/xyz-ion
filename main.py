import os
import asyncio
import yt_dlp
import time
import requests
from telethon import TelegramClient, events, types
from telethon.errors import FloodWaitError

# ================= CONFIG =================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")
DOWNLOAD_PATH = "/tmp"
THUMB_URL = "https://static.pw.live/5eb393ee95fab7468a79d189/ADMIN/6e008265-fef8-4357-a290-07e1da1ff964.png"

# Persistent session to prevent FloodWait
client = TelegramClient("bot_session", api_id, api_hash)

# ================= HELPER =================
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

        return file_path, info.get("duration", 0), info.get("width", 1280), info.get("height", 720)

# ================= BOT STATE =================
user_state = {}

# ================= BOT COMMANDS =================
@client.on(events.NewMessage(pattern="/drm"))
async def drm_handler(event):
    try:
        url = event.text.split(" ", 1)[1]
        user_state[event.sender_id] = {"url": url}
        await event.reply("🎬 Send quality: 720 or 1080")
    except:
        await event.reply("❌ Use:\n/drm your_link_here")

@client.on(events.NewMessage)
async def quality_handler(event):
    state = user_state.get(event.sender_id)
    if not state or "url" not in state:
        return

    if event.text not in ["720", "1080"]:
        return

    url = state["url"]
    quality = event.text
    status_msg = await event.reply("⬇ Downloading...")

    try:
        file_path, duration, width, height = await download_video(url, quality)
        thumbnail = download_thumbnail()
        formatted_duration = format_duration(duration)

        # Animated progress callback
        async def progress(current, total):
            percent = int(current * 100 / total)
            now = time.time()
            new_text = f"📤 Uploading... {percent}%"
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
            caption=f"{url.split(': http')[0].strip()}\n✅ Upload Complete!\n⏱ Duration: {formatted_duration}",
            thumb=thumbnail,
            supports_streaming=True,
            attributes=[types.DocumentAttributeVideo(duration=int(duration), w=width, h=height, supports_streaming=True)],
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
        user_state.pop(event.sender_id, None)

# ================= TXT HANDLER =================
@client.on(events.NewMessage(pattern="/txt"))
async def txt_handler(event):
    if event.sender_id in user_state:
        return  # Prevent asking twice
    user_state[event.sender_id] = {"txt_wait": True}
    await event.reply(
        "➠ 𝐒𝐞𝐧𝐝 𝐌𝐞 𝐘𝐨𝐮𝐫 𝐓𝐗𝐓 𝐅𝐢𝐥𝐞 𝐢𝐧 𝐀 𝐏𝐫𝐨𝐩𝐞𝐫 𝐖𝐚𝐲\n\n"
        "➠ TXT FORMAT : FILE NAME : URL/LINK\n"
        "➠ 𝐌𝐨𝐝𝐢𝐟𝐢𝐞𝐝 𝐁𝐲: @do_land_trump"
    )

@client.on(events.NewMessage)
async def txt_file_process(event):
    state = user_state.get(event.sender_id)
    if not state or "txt_wait" not in state:
        return

    if not event.file or not event.file.name.endswith(".txt"):
        await event.reply("❌ Please send a proper TXT file.")
        return

    path = await event.download_media(file=DOWNLOAD_PATH)
    titles = []
    video_count = 0
    pdf_count = 0

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if ": http" in line or ": https" in line:
                title = line.split(": http")[0].strip()
                url = line.split(": ", 1)[1].strip()
                titles.append({"index": i+1, "title": title, "url": url})
                if url.endswith(".mpd"):
                    video_count += 1
                if url.endswith(".pdf"):
                    pdf_count += 1

    user_state[event.sender_id].pop("txt_wait")
    user_state[event.sender_id]["txt_data"] = titles

    total_links = len(titles)
    await event.reply(
        f"Total links found: {total_links}\n"
        f"┃\n"
        f"┠ Total Video Count: {video_count}\n"
        f"┠ Total Pdf Count: {pdf_count}\n"
        f"┠ Send From where you want to download initial is : 1\n"
        f"┃\n"
        f"┠ Send /stop if you don't want to continue\n"
        f"┖ Bot By: @do_land_trump"
    )

# ================= STOP HANDLER =================
@client.on(events.NewMessage(pattern="/stop"))
async def stop_handler(event):
    if event.sender_id in user_state:
        user_state.pop(event.sender_id)
    await event.reply("⛔ Process stopped!")

# ================= RUN BOT =================
async def main():
    await client.start(bot_token=bot_token)
    print("🚀 Bot Running...")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
