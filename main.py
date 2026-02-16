import os
import re
import asyncio
import yt_dlp
import subprocess
import json

from telethon import TelegramClient, events, types

# ================= CONFIG =================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_token = os.getenv("BOT_TOKEN")

DOWNLOAD_PATH = "/tmp"

client = TelegramClient("bot", api_id, api_hash).start(bot_token=bot_token)

# ================= METADATA =================
def get_video_metadata(video_path):
    cmd = [
        "/usr/bin/ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    info = json.loads(result.stdout)

    duration = int(float(info["format"]["duration"]))

    video_stream = next(
        (stream for stream in info["streams"] if stream["codec_type"] == "video"),
        None
    )

    width = video_stream["width"]
    height = video_stream["height"]

    return duration, width, height


def generate_thumbnail(video_path):
    thumb_path = video_path.replace(".mp4", ".jpg")

    subprocess.run([
        "/usr/bin/ffmpeg",
        "-ss", "00:00:02",
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        thumb_path
    ])

    return thumb_path


# ================= DOWNLOAD =================
async def download_video(url, quality):

    if quality == "720":
        format_string = "bestvideo[height<=720]+bestaudio/best[height<=720]"
    else:
        format_string = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"

    ydl_opts = {
        "format": format_string,
        "outtmpl": os.path.join(DOWNLOAD_PATH, "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 10,
        "ffmpeg_location": "/usr/bin/ffmpeg",
        "postprocessors": [{
            "key": "FFmpegVideoRemuxer",
            "preferedformat": "mp4",
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info)

        if not file_path.endswith(".mp4"):
            file_path = file_path.rsplit(".", 1)[0] + ".mp4"

        return file_path


# ================= BOT =================
user_links = {}

@client.on(events.NewMessage(pattern="/drm"))
async def drm_handler(event):
    try:
        url = event.text.split(" ", 1)[1]
        user_links[event.sender_id] = url
        await event.reply("🎬 Send quality: 720 or 1080")
    except:
        await event.reply("❌ Send like:\n/drm your_link_here")


@client.on(events.NewMessage)
async def quality_handler(event):
    if event.sender_id not in user_links:
        return

    if event.text not in ["720", "1080"]:
        return

    url = user_links[event.sender_id]
    quality = event.text

    await event.reply("⬇ Downloading...")

    try:
        file_path = await download_video(url, quality)

        duration, width, height = get_video_metadata(file_path)
        thumbnail = generate_thumbnail(file_path)

        await event.reply("📤 Uploading...")

        await client.send_file(
            event.chat_id,
            file_path,
            caption="✅ Upload Complete!",
            thumb=thumbnail,
            supports_streaming=True,
            attributes=[
                types.DocumentAttributeVideo(
                    duration=duration,
                    w=width,
                    h=height,
                    supports_streaming=True
                )
            ]
        )

        os.remove(file_path)
        os.remove(thumbnail)

        del user_links[event.sender_id]

    except Exception as e:
        await event.reply(f"❌ Error: {str(e)}")


print("🚀 Bot Running...")
client.run_until_disconnected()

