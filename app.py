import re
import os
import asyncio
import subprocess
import random
import hashlib
from datetime import datetime
import httpx
from telegram import Update, LinkPreviewOptions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram.request import HTTPXRequest

# ✅ Config file se import
from config import BOT_TOKEN, PRIVATE_BACKUP_CHAT_ID, GROUPS_CONFIG, TARGET_BLOCKLIST

# 🌟 HEALTH CHECK SERVER
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(b"Bot is Healthy, ULTRA-FAST and Running 24/7!")
    def log_message(self, format, *args):
        return

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    httpd.serve_forever()

DB_FILE = "posted_text_strict_filter.txt"
MEDIA_HASH_DB = "posted_media_hashes.txt"
LINK_REGEX = re.compile(r'(https?://[^\s]+)')

POSTED_LINKS_CACHE = set()
POSTED_HASHES_CACHE = set()

GROUP_LOCK = asyncio.Lock()

def load_databases():
    global POSTED_LINKS_CACHE, POSTED_HASHES_CACHE
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r", encoding="utf-8") as f:
                POSTED_LINKS_CACHE = set(line.strip() for line in f if line.strip())
        if os.path.exists(MEDIA_HASH_DB):
            with open(MEDIA_HASH_DB, "r", encoding="utf-8") as f:
                POSTED_HASHES_CACHE = set(line.strip() for line in f if line.strip())
    except Exception:
        pass

def save_link_to_db(link: str):
    try:
        POSTED_LINKS_CACHE.add(link)
        with open(DB_FILE, "a", encoding="utf-8") as f:
            f.write(link + "\n")
    except Exception:
        pass

def save_hash_to_db(media_hash: str):
    try:
        POSTED_HASHES_CACHE.add(media_hash)
        with open(MEDIA_HASH_DB, "a", encoding="utf-8") as f:
            f.write(media_hash + "\n")
    except Exception:
        pass

def generate_file_hash(filepath: str) -> str:
    hasher = hashlib.md5()
    try:
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                buf = f.read(65536)
                while len(buf) > 0:
                    hasher.update(buf)
                    buf = f.read(65536)
    except Exception:
        pass
    return hasher.hexdigest()

def generate_custom_layout(group_key, title, count, link, date, data_size_val, social_link):
    if group_key == "A":
        layout = (f"🔞 <b>Video :-</b> <code>{title}</code>\n━━━━━━━━━━━━━━━━━━\n🛑 <b>Number :-</b> # {count}\n🥵 <b>Link :-</b> {link}\n🔥 <b>Date :-</b> {date}\n💥 <b>Data size :-</b> {data_size_val}")
    elif group_key == "B":
        layout = (f"🔞 <b>Video :-</b> {title}\n🔺━━━━━━━━━━━━━━🔺\n🛑 <b>Number :-</b> [ {count} ]\n🥵 <b>Link :-</b> {link}\n🔥 <b>Date :-</b> {date}\n💥 <b>Data size :-</b> {data_size_val}")
    elif group_key == "C":
        layout = (f"🔞 <b>Video :-</b> {title}\n⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡\n🛑 <b>Number :-</b> {count}\n🥵 <b>Link :-</b> {link}\n🔥 <b>Date :-</b> {date}\n💥 <b>Data size :-</b> {data_size_val}")
    elif group_key == "F":
        layout = (f"⚙️ <b>Fallback Video :-</b> {title}\n⚠️ <i>[Video Clip Failed / Small Preview Detected]</i>\n🔧──────────────🔧\n🛑 <b>Number :-</b> {count}\n🥵 <b>Link :-</b> {link}\n🔥 <b>Date :-</b> {date}")
    else:
        layout = (f"🔞 <b>Video :-</b> {title}\n🔹──────────────🔹\n🛑 <b>Number :-</b> {count}\n🥵 <b>Link :-</b> {link}\n🔥 <b>Date :-</b> {date}\n💥 <b>Data size :-</b> {data_size_val}")
    if social_link:
        layout += f"\n\n✨ <a href='{social_link}'>Join us!</a>"
    return layout

async def check_preview_size(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = await client.get(url, headers=headers)
            html = response.text
            return ('property="og:image:width"' in html or 'name="twitter:card" content="summary_large_image"' in html or 'property="og:image"' in html)
    except Exception:
        return False

async def download_full_and_extract_clip(url: str, output_clip_name: str, context: ContextTypes.DEFAULT_TYPE):
    rand_id = random.randint(1000, 9999)
    full_video_temp = f"full_backup_{rand_id}.mp4"
    user_agents = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"]
    proxy_options = ["", "http://igeazdow:gi6ke363yfow@38.154.203.95:5863/"]
    format_rule = "worst[ext=mp4]/worst"

    for proxy in proxy_options:
        try:
            cmd_info = [
                "yt-dlp", "--no-playlist", "--socket-timeout", "10",
                "--prefer-free-formats", "--no-warnings", "--rm-cache-dir",
                "--user-agent", random.choice(user_agents),
                "-f", format_rule, "--print", "%(title)s\n%(url)s", url
            ]
            if proxy:
                cmd_info.extend(["--proxy", proxy])

            process_info = await asyncio.create_subprocess_exec(*cmd_info, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                stdout, _ = await asyncio.wait_for(process_info.communicate(), timeout=15.0)
            except asyncio.TimeoutError:
                try: process_info.kill()
                except: pass
                continue

            output_lines = stdout.decode('utf-8').strip().split('\n')
            if len(output_lines) < 2:
                continue

            extracted_title = output_lines[0].strip()
            stream_url = output_lines[1].strip()

            url_hash = hashlib.md5(stream_url.encode('utf-8')).hexdigest()
            if url_hash in POSTED_HASHES_CACHE:
                return "DUPLICATE_HASH", extracted_title, None

            cmd_dl = [
                "yt-dlp", "--no-playlist", "--socket-timeout", "15",
                "--user-agent", random.choice(user_agents),
                "-f", format_rule, "-o", full_video_temp, url
            ]
            if proxy:
                cmd_dl.extend(["--proxy", proxy])

            dl_process = await asyncio.create_subprocess_exec(*cmd_dl, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                await asyncio.wait_for(dl_process.communicate(), timeout=60.0)
            except asyncio.TimeoutError:
                try: dl_process.kill()
                except: pass
                if os.path.exists(full_video_temp): os.remove(full_video_temp)
                continue

            if os.path.exists(full_video_temp) and os.path.getsize(full_video_temp) > 0:
                try:
                    with open(full_video_temp, "rb") as f_video:
                        await context.bot.send_video(
                            chat_id=PRIVATE_BACKUP_CHAT_ID, video=f_video,
                            caption=f"📋 <b>Backup</b>\n📌 {extracted_title}",
                            parse_mode="HTML"
                        )
                except Exception as e:
                    if "Too Many Requests" in str(e): await asyncio.sleep(3)

                ffmpeg_cmd = [
                    "ffmpeg", "-y", "-ss", "00:00:03", "-i", full_video_temp, "-t", "10",
                    "-c:v", "libx264", "-an", "-preset", "ultrafast", "-tune", "fastdecode",
                    "-pix_fmt", "yuv420p", output_clip_name
                ]
                ffmpeg_process = await asyncio.create_subprocess_exec(*ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    await asyncio.wait_for(ffmpeg_process.communicate(), timeout=20.0)
                except asyncio.TimeoutError:
                    try: ffmpeg_process.kill()
                    except: pass

                if os.path.exists(full_video_temp):
                    os.remove(full_video_temp)

                success = os.path.exists(output_clip_name) and os.path.getsize(output_clip_name) > 0
                return success, extracted_title, url_hash
        except Exception:
            if os.path.exists(full_video_temp):
                try: os.remove(full_video_temp)
                except: pass

    return False, "Exclusive Video", None

async def process_single_link(link, join_link, context, sent_counts, normal_groups_pool, status_state, semaphore):
    async with semaphore:
        if link in POSTED_LINKS_CACHE:
            return

        is_adult_link = any(domain in link.lower() for domain in TARGET_BLOCKLIST)
        video_filename = f"preview_{random.randint(1000, 99999)}.mp4"

        video_success, video_title, url_hash = await download_full_and_extract_clip(link, video_filename, context)

        if video_success == "DUPLICATE_HASH":
            save_link_to_db(link)
            status_state['processed'] += 1
            return

        has_large_preview = True
        if video_success and not is_adult_link:
            has_large_preview = await check_preview_size(link)

        if video_success and os.path.exists(video_filename):
            visual_hash = generate_file_hash(video_filename)
            if visual_hash in POSTED_HASHES_CACHE:
                os.remove(video_filename)
                save_link_to_db(link)
                status_state['processed'] += 1
                return
            else:
                save_hash_to_db(visual_hash)

        if url_hash:
            save_hash_to_db(url_hash)

        async with GROUP_LOCK:
            target_key = None
            if is_adult_link:
                if sent_counts["B"] < GROUPS_CONFIG["B"]["limit"]:
                    target_key = "B"
                else:
                    if os.path.exists(video_filename): os.remove(video_filename)
                    return
            else:
                if not video_success or not has_large_preview:
                    target_key = "F"
                else:
                    started_index = status_state['pool_index']
                    while status_state['pool_index'] < len(normal_groups_pool):
                        current_pool_key = normal_groups_pool[status_state['pool_index']]
                        if sent_counts[current_pool_key] < GROUPS_CONFIG[current_pool_key]["limit"]:
                            target_key = current_pool_key
                            status_state['pool_index'] = (status_state['pool_index'] + 1) % len(normal_groups_pool)
                            break
                        else:
                            status_state['pool_index'] = (status_state['pool_index'] + 1) % len(normal_groups_pool)
                            if status_state['pool_index'] == started_index:
                                break
                    if not target_key:
                        target_key = "F"

            group = GROUPS_CONFIG[target_key]
            sent_counts[target_key] += 1
            current_count = sent_counts[target_key]

        post_format = generate_custom_layout(
            group_key=target_key, title=video_title, count=current_count,
            link=link, date=datetime.now().strftime("%d-%m-%Y"), data_size_val="45 MB", social_link=join_link
        )

        try:
            if video_success and os.path.exists(video_filename) and target_key != "F":
                with open(video_filename, "rb") as video_file:
                    await context.bot.send_animation(chat_id=group["chat_id"], animation=video_file, caption=post_format, parse_mode="HTML")
                os.remove(video_filename)
            else:
                preview_settings = LinkPreviewOptions(is_disabled=False, prefer_large_media=True, show_above_text=True)
                await context.bot.send_message(chat_id=group["chat_id"], text=post_format, parse_mode="HTML", link_preview_options=preview_settings)
                if os.path.exists(video_filename): os.remove(video_filename)

            save_link_to_db(link)
        except Exception as tg_error:
            if "Too Many Requests" in str(tg_error): await asyncio.sleep(5)
            if os.path.exists(video_filename): os.remove(video_filename)

        status_state['processed'] += 1

async def process_automated_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        file = await context.bot.get_file(update.message.document.file_id)
        content = await file.download_as_bytearray()
        links = LINK_REGEX.findall(content.decode('utf-8'))
        links = list(dict.fromkeys([l.strip() for l in links if l.strip()]))

        if not links:
            await update.message.reply_text("❌ No valid links found in file!")
            return

        join_link = ""
        if update.message.caption:
            found_caption_links = LINK_REGEX.findall(update.message.caption)
            if found_caption_links: join_link = found_caption_links[0].strip()

        status_msg = await update.message.reply_text(f"🚀 <b>Turbo Mode Active</b>\nProcessing {len(links)} links concurrently...", parse_mode="HTML")
        load_databases()

        sent_counts = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        normal_groups_pool = ["A", "C", "D"]
        status_state = {'processed': 0, 'pool_index': 0}

        semaphore = asyncio.Semaphore(3)
        tasks = []

        for link in links:
            task = asyncio.create_task(process_single_link(link, join_link, context, sent_counts, normal_groups_pool, status_state, semaphore))
            tasks.append(task)

        async def update_progress():
            while status_state['processed'] < len(links):
                try:
                    await status_msg.edit_text(f"⚡ <b>Turbo Speed Live Status:</b>\n\n✅ Processed: {status_state['processed']}/{len(links)} links", parse_mode="HTML")
                except: pass
                await asyncio.sleep(5)

        progress_task = asyncio.create_task(update_progress())
        await asyncio.gather(*tasks)
        progress_task.cancel()

        await status_msg.edit_text(f"🎉 <b>BOOM!</b>\nAll {len(links)} links processed successfully at Turbo Speed!", parse_mode="HTML")
    except Exception as e:
        print(f"Error: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 <b>Turbo Bot Active!</b>\n\n"
        "📂 Mujhe ek <b>.txt file</b> bhejo jisme links hon.\n"
        "⚡ Main automatically sab groups mein post kar dunga!",
        parse_mode="HTML"
    )

def main():
    print(f"\n{'='*45}")
    print(f"===== Application Startup at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====")
    print(f"{'='*45}")

    print("🚀 Step 1: Starting health check server...")
    threading.Thread(target=run_health_server, daemon=True).start()

    print("📂 Step 2: Loading databases...")
    load_databases()

    print("🔑 Step 3: Checking BOT_TOKEN...")
    if not BOT_TOKEN or BOT_TOKEN == "APNA_BOT_TOKEN_YAHAN_LIKHO":
        print("[CRITICAL ERROR] config.py mein BOT_TOKEN set karo!")
        return
    print(f"✅ Step 4: Token loaded! Length: {len(BOT_TOKEN)} characters")

    print("🤖 Step 5: Building bot application...")
    custom_request = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0, write_timeout=60.0, connection_pool_size=20)
    app = Application.builder().token(BOT_TOKEN).request(custom_request).build()

    print("📡 Step 6: Registering handlers...")
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.Document.ALL, process_automated_file))

    print("✅ Step 7: All handlers registered!")
    print("🔄 Bot polling started in Turbo Mode...\n")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
