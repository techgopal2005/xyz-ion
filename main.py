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

# Persistent session file to avoid FloodWait
SESSION_NAME = "bot_session"

client = TelegramClient(SESSION_NAME, api_id, api_hash)

# ================= GLOBALS =================
user_txt_files = {}  # {user_id: {"file_path": ..., "links": [...], "stop": False}}
user_download_tasks = {}  # track ongoing tasks


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
    if quality == "720":
        format_string = "bestvideo[height<=720]+bestaudio/best[height<=720]"
    elif quality == "480":
        format_string = "bestvideo[height<=480]+bestaudio/best[height<=480]"
    else:
        format_string = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"

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


# ================= COMMANDS =================
@client.on(events.NewMessage(pattern="/txt"))
async def txt_handler(event):
    user_id = event.sender_id
    if user_id in user_txt_files:
        # Already asked once, ignore duplicate
        return

    user_txt_files[user_id] = {"file_path": None, "links": [], "stop": False}

    await event.reply(
        "➠ 𝐒𝐞𝐧𝐝 𝐌𝐞 𝐘𝐨𝐮𝐫 𝐓𝐗𝐓 𝐅𝐢𝐥𝐞 𝐢𝐧 𝐀 𝐏𝐫𝐨𝐩𝐞𝐫 𝐖𝐚𝐲\n\n"
        "➠ TXT FORMAT : FILE NAME : URL/LINK\n"
        "➠ 𝐌𝐨𝐝𝐢𝐟𝐢𝐞𝐝 𝐁𝐲: @do_land_trump"
    )


@client.on(events.NewMessage)
async def file_receive_handler(event):
    user_id = event.sender_id
    if user_id not in user_txt_files:
        return

    # Handle stop
    if event.text.lower() == "/stop":
        user_txt_files[user_id]["stop"] = True
        task = user_download_tasks.get(user_id)
        if task and not task.done():
            task.cancel()
        await event.reply("✅ Process stopped.")
        return

    if not event.file:
        return  # ignore non-file messages

    if not event.file.name.endswith(".txt"):
        await event.reply("❌ Please send a proper TXT file.")
        return

    # Save file locally
    file_path = os.path.join(DOWNLOAD_PATH, f"{user_id}_input.txt")
    await client.download_media(event.message, file_path)
    user_txt_files[user_id]["file_path"] = file_path

    # Read and parse links
    links = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if ": http" in line or ": https" in line:
                parts = line.split(": http")
                title = parts[0].strip()
                url = "http" + parts[1].strip()
                links.append((title, url))

    if not links:
        await event.reply("❌ No valid links found in TXT.")
        return

    user_txt_files[user_id]["links"] = links

    # Send total count
    total_videos = len([1 for t, u in links if ".mpd" in u])
    total_pdfs = len([1 for t, u in links if ".pdf" in u])
    await event.reply(
        f"Total links found: {len(links)}\n"
        f"┃\n"
        f"┠ Total Video Count: {total_videos}\n"
        f"┠ Total PDF Count: {total_pdfs}\n"
        f"┠ Send From where you want to download initial (default 1): 1\n"
        f"┃\n"
        f"┠ Send /stop if you don't want to continue\n"
        f"┖ Bot By: @do_land_trump"
    )


# ================= DOWNLOAD LOOP =================
async def start_download(user_id, chat_id, quality="1080"):
    user_data = user_txt_files[user_id]
    links = user_data["links"]
    thumb = download_thumbnail()

    for idx, (title, url) in enumerate(links, start=1):
        if user_data["stop"]:
            await client.send_message(chat_id, "✅ Download stopped.")
            break

        status_msg = await client.send_message(chat_id, f"⬇ Downloading {title}...")
        try:
            # Attempt 1080 → 720 → 480
            for q in ([quality] if quality != "720" else ["720", "480"]):
                try:
                    file_path, duration, w, h = await download_video(url, q)
                    break
                except Exception:
                    continue
            else:
                await client.send_message(chat_id, f"❌ Failed at index {idx}: {title}")
                break

            formatted_duration = format_duration(duration)

            # Animated upload progress
            async def progress(current, total):
                percent = int(current * 100 / total)
                now = time.time()
                new_text = f"📤 Uploading {title}: {percent}%"
                if now - progress.last_update > 1 and new_text != progress.last_text:
                    try:
                        await status_msg.edit(new_text)
                        progress.last_update = now
                        progress.last_text = new_text
                    except:
                        pass

            progress.last_update = 0
            progress.last_text = ""

            await client.send_file(
                chat_id,
                file_path,
                caption=title,
                thumb=thumb,
                supports_streaming=True,
                attributes=[types.DocumentAttributeVideo(duration=int(duration), w=w, h=h)],
                progress_callback=progress
            )
            await status_msg.edit(f"✅ Uploaded {title} successfully!")

            # cleanup
            if os.path.exists(file_path):
                os.remove(file_path)

        except asyncio.CancelledError:
            await client.send_message(chat_id, "✅ Process cancelled.")
            break

    if os.path.exists(thumb):
        os.remove(thumb)


# ================= START BOT =================
async def main():
    await client.start(bot_token=bot_token)
    print("🚀 Bot Running...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
