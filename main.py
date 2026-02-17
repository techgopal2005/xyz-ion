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
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

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

def download_file(url, out_path):
    """Download video using yt_dlp"""
    ydl_opts = {
        "outtmpl": out_path,
        "merge_output_format": "mp4",
        "prefer_ffmpeg": True,
        "noplaylist": True,
        "quiet": True,
        "retries": 5,
        "fragment_retries": 5,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info)
        if not file_path.endswith(".mp4") and url.endswith(".mpd"):
            file_path = file_path.rsplit(".", 1)[0] + ".mp4"
        return file_path, info.get("duration", 0), info.get("width", 1280), info.get("height", 720)

# ================= USER SESSIONS =================
user_sessions = {}

# ================= /stop HANDLER =================
@client.on(events.NewMessage(pattern="/stop"))
async def stop_handler(event):
    user_id = event.sender_id
    thread_id = getattr(event.message, "thread_id", None)
    key = (user_id, thread_id)
    if key in user_sessions:
        user_sessions[key]['stop'] = True
    msg = "✅ Process Stopped ✔"
    if thread_id:
        await client.send_message(event.chat_id, msg, thread_id=thread_id)
    else:
        await event.reply(msg)

# ================= /txt HANDLER =================
@client.on(events.NewMessage(pattern="/txt"))
async def txt_handler(event):
    user_id = event.sender_id
    thread_id = getattr(event.message, "thread_id", None)
    key = (user_id, thread_id)

    # Only ask once if already waiting
    if key in user_sessions and user_sessions[key].get("state") == "waiting_file":
        return

    msg_text = (
        "➠ 𝐒𝐞𝐧𝐝 𝐌𝐞 𝐘𝐨𝐮𝐫 𝐓𝐗𝐓 𝐅𝐢𝐥𝐞 𝐢𝐧 𝐀 𝐏𝐫𝐨𝐩𝐞𝐫 𝐖𝐚𝐲 \n\n"
        "➠ TXT FORMAT : FILE NAME : URL/LINK \n"
        "➠ 𝐌𝐨𝐝𝐢𝐟𝐢𝐞𝐝 𝐁𝐲: @do_land_trump"
    )

    if thread_id:
        await client.send_message(event.chat_id, msg_text, thread_id=thread_id)
    else:
        await event.reply(msg_text)

    # Mark session waiting for file
    user_sessions[key] = {"state": "waiting_file", "links": [], "stop": False}

# ================= TXT FILE RECEIVED =================
@client.on(events.NewMessage(func=lambda e: e.file is not None))
async def file_handler(event):
    user_id = event.sender_id
    thread_id = getattr(event.message, "thread_id", None)
    key = (user_id, thread_id)

    if key not in user_sessions or user_sessions[key]['state'] != "waiting_file":
        return

    if not event.file.name.endswith(".txt"):
        msg = "❌ Only TXT files are supported."
        if thread_id:
            await client.send_message(event.chat_id, msg, thread_id=thread_id)
        else:
            await event.reply(msg)
        return

    path = os.path.join(DOWNLOAD_PATH, event.file.name)
    await event.download_media(file=path)

    # Parse TXT lines
    links = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "http" not in line:
                continue
            idx = line.find("http")
            title = line[:idx].strip(" :")
            url = line[idx:].strip()
            links.append({"title": title, "url": url})

    if not links:
        msg = "❌ No valid links found in TXT."
        if thread_id:
            await client.send_message(event.chat_id, msg, thread_id=thread_id)
        else:
            await event.reply(msg)
        return

    mpd_count = sum(1 for l in links if l['url'].endswith(".mpd"))
    pdf_count = sum(1 for l in links if l['url'].endswith(".pdf"))

    user_sessions[key]['links'] = links
    user_sessions[key]['state'] = "waiting_start_index"

    msg = (
        f"Total links found are : {len(links)}\n"
        f"┃\n"
        f"┠ Total Video Count : {mpd_count}\n"
        f"┠ Total Pdf Count : {pdf_count}\n"
        f"┠ Send From where you want to download initial is  : 1\n"
        f"┃\n"
        f"┠ Send /stop If don't want to Continue\n"
        f"┖ Bot By : @do_land_trump"
    )
    if thread_id:
        await client.send_message(event.chat_id, msg, thread_id=thread_id)
    else:
        await event.reply(msg)

# ================= INDEX HANDLER =================
@client.on(events.NewMessage(func=lambda e: e.text and e.text.isdigit()))
async def index_handler(event):
    user_id = event.sender_id
    thread_id = getattr(event.message, "thread_id", None)
    key = (user_id, thread_id)

    if key not in user_sessions:
        return

    session = user_sessions[key]

    # Start index
    if session.get('state') == "waiting_start_index":
        start = int(event.text)
        if start < 1 or start > len(session['links']):
            msg = f"❌ Invalid start index. Must be 1-{len(session['links'])}"
            if thread_id:
                await client.send_message(event.chat_id, msg, thread_id=thread_id)
            else:
                await event.reply(msg)
            return
        session['start_index'] = start - 1
        session['state'] = "waiting_end_index"
        msg = (
            f"ENTER TILL WHERE YOU WANT TO DOWNLOAD \n"
            f"┃\n"
            f"┠ Starting Download From : {start}\n"
            f"┖ Last Index Of Links is : {len(session['links'])}"
        )
        if thread_id:
            await client.send_message(event.chat_id, msg, thread_id=thread_id)
        else:
            await event.reply(msg)
        return

    # End index
    if session.get('state') == "waiting_end_index":
        end = int(event.text)
        start_index = session['start_index']
        if end <= start_index or end > len(session['links']):
            msg = f"❌ Invalid end index. Must be {start_index+1}-{len(session['links'])}"
            if thread_id:
                await client.send_message(event.chat_id, msg, thread_id=thread_id)
            else:
                await event.reply(msg)
            return
        session['end_index'] = end
        session['state'] = "downloading"
        asyncio.create_task(download_links(event, session, key))
        return

# ================= DOWNLOAD FUNCTION WITH PROGRESS =================
async def download_links(event, session, key):
    thread_id = getattr(event.message, "thread_id", None)
    chat_id = event.chat_id
    links = session['links'][session['start_index']:session['end_index']]

    for idx, item in enumerate(links, start=session['start_index'] + 1):
        if session['stop']:
            break
        title = item['title']
        url = item['url']
        try:
            status_msg_text = f"⬇ Downloading {title}..."
            if thread_id:
                status_msg = await client.send_message(chat_id, status_msg_text, thread_id=thread_id)
            else:
                status_msg = await event.reply(status_msg_text)

            if url.endswith(".pdf"):
                out_path = os.path.join(DOWNLOAD_PATH, url.split("/")[-1])
                r = requests.get(url)
                with open(out_path, "wb") as f:
                    f.write(r.content)
                # Animated progress while sending file
                await send_file_with_progress(chat_id, out_path, title, thread_id)
                os.remove(out_path)
            else:  # video
                success = False
                for _ in ["1080", "720", "480"]:
                    try:
                        out_path = os.path.join(DOWNLOAD_PATH, f"{title}.mp4")
                        file_path, duration, width, height = download_file(url, out_path)
                        await send_file_with_progress(chat_id, file_path, title, thread_id, duration, width, height)
                        os.remove(file_path)
                        success = True
                        break
                    except:
                        continue
                if not success:
                    msg = f"❌ Download Failed\n\nFailed Index : {idx}\nTitle : {title}"
                    if thread_id:
                        await client.send_message(chat_id, msg, thread_id=thread_id)
                    else:
                        await event.reply(msg)
                    session['stop'] = True
                    break

            try:
                await status_msg.delete()
            except:
                pass

        except Exception:
            msg = f"❌ Download Failed\n\nFailed Index : {idx}\nTitle : {title}"
            if thread_id:
                await client.send_message(chat_id, msg, thread_id=thread_id)
            else:
                await event.reply(msg)
            session['stop'] = True
            break

    if not session['stop']:
        msg = "✅ All downloads completed!"
        if thread_id:
            await client.send_message(chat_id, msg, thread_id=thread_id)
        else:
            await event.reply(msg)

    user_sessions.pop(key, None)

# ================= SEND FILE WITH ANIMATED PROGRESS =================
async def send_file_with_progress(chat_id, file_path, caption, thread_id=None, duration=0, width=1280, height=720):
    progress_msg = None
    last_percent = 0

    async def progress(current, total):
        nonlocal progress_msg, last_percent
        percent = int(current * 100 / total)
        if percent - last_percent >= 5:  # update every 5%
            text = f"📤 Uploading {caption}... {percent}%"
            if progress_msg:
                try:
                    await progress_msg.edit(text)
                except:
                    pass
            last_percent = percent

    if thread_id:
        progress_msg = await client.send_message(chat_id, f"📤 Uploading {caption}... 0%", thread_id=thread_id)
    else:
        progress_msg = await client.send_message(chat_id, f"📤 Uploading {caption}... 0%")

    if file_path.endswith(".mp4"):
        await client.send_file(
            chat_id,
            file_path,
            caption=caption,
            supports_streaming=True,
            attributes=[types.DocumentAttributeVideo(duration=int(duration), w=width, h=height, supports_streaming=True)],
            progress_callback=progress,
            thread_id=thread_id
        )
    else:  # PDF
        await client.send_file(chat_id, file_path, caption=caption, progress_callback=progress, thread_id=thread_id)

    try:
        await progress_msg.delete()
    except:
        pass

# ================= RUN BOT =================
print("🚀 Bot Running...")
client.run_until_disconnected()
