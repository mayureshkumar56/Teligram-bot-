import re
import os
import asyncio
import subprocess
import random
import threading
import gc
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update, LinkPreviewOptions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==========================================
# 1. BOT TOKEN & GROUP E CONFIGURATION
# ==========================================
# ⚠️ Yahan apna asli Telegram Bot Token aur update ki hui sahi Group IDs bhariye
BOT_TOKEN = "8648804848:AAHKWQ9WSlVzAH1hqcpPf9OKcY77h_pLRzA"
GROUP_E_CHAT_ID = -1003938588965  

# ==========================================
# 2. MAIN GROUPS CONFIGURATION (600 LIMIT)
# ==========================================
GROUPS_CONFIG = {
    "A": {"name": "Group A", "chat_id": -1003810828255, "limit": 600},  
    "B": {"name": "Group B (Strict Adult Filter)", "chat_id": -1003791464998, "limit": 600},  
    "C": {"name": "Group C", "chat_id": -1003956008527, "limit": 600},  
    "D": {"name": "Group D", "chat_id": -1003934725687, "limit": 600}   
}

TARGET_BLOCKLIST = [
    "xhamster.com", "xhamster45.desi", "xhamster2.com", "xhamster.desi",          
    "freepornvideo.sex", "aagmaal.dog", "xhopen.com", "beeg.porn", "desixx.net",
    "wonporn.com", "xxxvideosind.com"
]

DB_FILE = "posted_text_strict_filter.txt"
LINK_REGEX = re.compile(r'(https?://[^\s]+)')
MONITORED_CHAT_IDS = [g["chat_id"] for g in GROUPS_CONFIG.values()]

def run_render_port_server():
    port = int(os.environ.get("PORT", 10000))
    try:
        server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
        server.serve_forever()
    except Exception:
        pass

def get_posted_data():
    if not os.path.exists(DB_FILE): return set()
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

# ==========================================
# 3. CUSTOM MULTI-LAYOUT GENERATOR (🥵 = LINK FIXED)
# ==========================================
def generate_custom_layout(group_key, title, count, link, date, data_size_val, social_link):
    if group_key == "A":
        layout = (
            f"🔞 <b>Video :-</b> <code>{title}</code>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🛑 <b>Number :-</b> # {count}\n"
            f"🥵 <b>Link :-</b> {link}\n"
            f"🔥 <b>Date :-</b> {date}\n"
            f"💥 <b>Data size :-</b> {data_size_val}"
        )
    elif group_key == "B":
        layout = (
            f"🔞 <b>Video :-</b> {title}\n"
            f"🔺━━━━━━━━━━━━━━🔺\n"
            f"🛑 <b>Number :-</b> [ {count} ]\n"
            f"🥵 <b>Link :-</b> {link}\n"
            f"🔥 <b>Date :-</b> {date}\n"
            f"💥 <b>Data size :-</b> {data_size_val}"
        )
    elif group_key == "C":
        layout = (
            f"🔞 <b>Video :-</b> {title}\n"
            f"⚡⚡⚡⚡⚡⚡⚡⚡⚡⚡\n"
            f"🛑 <b>Number :-</b> {count}\n"
            f"🥵 <b>Link :-</b> {link}\n"
            f"🔥 <b>Date :-</b> {date}\n"
            f"💥 <b>Data size :-</b> {data_size_val}"
        )
    else:  # Group D
        layout = (
            f"🔞 <b>Video :-</b> {title}\n"
            f"🔹──────────────🔹\n"
            f"🛑 <b>Number :-</b> {count}\n"
            f"🥵 <b>Link :-</b> {link}\n"
            f"🔥 <b>Date :-</b> {date}\n"
            f"💥 <b>Data size :-</b> {data_size_val}"
        )
        
    if social_link:
        layout += f"\n\n<b>Joined. :-</b> {social_link}"
        
    return layout

# ==========================================
# 4. SUPER FAST METADATA & VIDEO CLIP CUTTER
# ==========================================
async def get_video_metadata_and_stream(url: str) -> tuple:
    try:
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36"
        ]
        cmd = [
            "yt-dlp", "-j", "--no-playlist", "--socket-timeout", "3",
            "--user-agent", random.choice(user_agents), url
        ]
        process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=3.5)
        except asyncio.TimeoutError:
            process.kill()
            return None, "Premium Content", "N/A"
            
        if process.returncode != 0:
            return None, "Premium Content", "N/A"
            
        import json
        data = json.loads(stdout.decode('utf-8'))
        stream_url = data.get('url', '')
        video_title = data.get('title', 'Premium Content')
        if len(video_title) > 50:
            video_title = video_title[:47] + "..."
            
        bytes_size = data.get('filesize') or data.get('filesize_approx')
        size_str = "N/A"
        if bytes_size:
            mb_size = bytes_size / (1024 * 1024)
            if mb_size >= 1024:
                size_str = f"{round(mb_size / 1024, 2)} GB"
            else:
                size_str = f"{round(mb_size, 2)} MB"
                
        return stream_url, video_title, size_str
    except Exception:
        return None, "Premium Content", "N/A"

async def cut_video_clip(stream_url: str, output_filename: str) -> bool:
    """⚡ TURBO CLIPPING: Exact 7-second auto-playing loop preview video cut"""
    try:
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-threads", "1", "-ss", "00:00:04", "-i", stream_url, "-t", "7",
            "-c:v", "libx264", "-an", "-preset", "superfast", "-tune", "fastdecode",
            "-pix_fmt", "yuv420p", output_filename
        ]
        ffmpeg_process = await asyncio.create_subprocess_exec(*ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            await asyncio.wait_for(ffmpeg_process.communicate(), timeout=6.0)
        except asyncio.TimeoutError:
            ffmpeg_process.kill()
            return False
        return ffmpeg_process.returncode == 0 and os.path.exists(output_filename)
    except Exception:
        return False

# ==========================================
# 5. ENGINE 1: LIVE GROUP MONITORING
# ==========================================
async def monitor_live_group_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message if update.message else update.channel_post
    if not message or not message.text: return
    chat_id = message.chat_id
    if chat_id in MONITORED_CHAT_IDS:
        links = LINK_REGEX.findall(message.text)
        if not links: return
        posted_database = get_posted_data()
        for link in links:
            link = link.strip()
            if link not in posted_database:
                try:
                    await asyncio.sleep(0.2) 
                    await context.bot.send_message(chat_id=GROUP_E_CHAT_ID, text=f"{link}")
                    await context.bot.delete_message(chat_id=chat_id, message_id=message.message_id)
                    break  
                except Exception as e:
                    if "FloodControl" in str(e) or "Retry in" in str(e):
                        await asyncio.sleep(3)
                    continue

# ==========================================
# 6. ENGINE 2: AUTOMATED INPUT PROCESSING
# ==========================================
async def process_automated_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message if update.message else update.channel_post
    if not message: return
    links = []
    joined_caption_link = ""
    
    if message.document:
        try:
            file = await context.bot.get_file(message.document.file_id)
            content = await file.download_as_bytearray()
            links = LINK_REGEX.findall(content.decode('utf-8'))
        except Exception as e:
            await message.reply_text(f"❌ File Engine Error: {e}")
            return
        if message.caption:
            found_caption_links = LINK_REGEX.findall(message.caption)
            if found_caption_links:
                joined_caption_link = found_caption_links[0].strip()
    elif message.text:
        links = LINK_REGEX.findall(message.text)
    if not links: return

    status_msg = await message.reply_text("⚡ Super Turbo Clipper Engine Active...")
    posted_database = get_posted_data()
    sent_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    normal_groups_pool = ["A", "C", "D"]
    pool_index = 0
    total_processed_counter = 0  
    backup_storage = {"A": [], "B": [], "C": [], "D": []}

    for link in links:
        link = link.strip()
        if not link or link in posted_database: continue
        is_adult_link = any(domain in link.lower() for domain in TARGET_BLOCKLIST)
        target_key = None
        if is_adult_link:
            if sent_counts["B"] < GROUPS_CONFIG["B"]["limit"]: target_key = "B"
            else: continue
        else:
            started_index = pool_index
            while pool_index < len(normal_groups_pool):
                current_pool_key = normal_groups_pool[pool_index]
                if sent_counts[current_pool_key] < GROUPS_CONFIG[current_pool_key]["limit"]:
                    target_key = current_pool_key
                    pool_index = (pool_index + 1) % len(normal_groups_pool)
                    break
                else:
                    pool_index = (pool_index + 1) % len(normal_groups_pool)
                    if pool_index == started_index: break
            if not target_key: continue

        group = GROUPS_CONFIG[target_key]
        video_filename = f"preview_{int(asyncio.get_event_loop().time())}.mp4"
        try:
            total_processed_counter += 1
            current_date_str = datetime.now().strftime("%d-%m-%Y")
            
            # Fetch stream link, title and data size
            stream_url, video_title_val, data_size_val = await get_video_metadata_and_stream(link)
            
            # Generate custom specific layout
            post_format = generate_custom_layout(
                group_key=target_key, title=video_title_val, count=total_processed_counter, 
                link=link, date=current_date_str, data_size_val=data_size_val, social_link=joined_caption_link
            )
            
            # 🌟 STRIKT VIDEO CLIP CALL EXECUTION
            video_success = False
            if stream_url:
                video_success = await cut_video_clip(stream_url, video_filename)
            
            if video_success:
                # Video cutting is successful, send 7s animation to main targeted groups!
                with open(video_filename, "rb") as video_file:
                    await context.bot.send_animation(
                        chat_id=group["chat_id"], animation=video_file, 
                        caption=post_format, parse_mode="HTML"
                    )
                if os.path.exists(video_filename): os.remove(video_filename)
                backup_storage[target_key].append(link)
                sent_counts[target_key] += 1
            else:
                # ⏩ Timeout/Slow links direct routed fallback into Group E with large preview cards
                fallback_format = (
                    f"📥 <b>Fallback Direct Link</b>\n━━━━━━━━━━━━━━━━━━\n"
                    f"🔞 <b>Video :-</b> {video_title_val}\n🛑 <b>Number :-</b> {total_processed_counter}\n"
                    f"🥵 <b>Link :-</b> {link}\n🔥 <b>Date :-</b> {current_date_str}\n💥 <b>Data size :-</b> {data_size_val}"
                )
                if joined_caption_link: fallback_format += f"\n\n<b>Joined. :-</b> {joined_caption_link}"
                preview_settings = LinkPreviewOptions(is_disabled=False, prefer_large_media=True, show_above_text=True)
                await context.bot.send_message(chat_id=GROUP_E_CHAT_ID, text=fallback_format, parse_mode="HTML", link_preview_options=preview_settings)
            
            with open(DB_FILE, "a", encoding="utf-8") as f: f.write(link + "\n")
            posted_database.add(link)
            
            if total_processed_counter % 5 == 0:
                progress_text = (
                    f"🔥 <b>Turbo Clipper Live Status:</b>\n\n"
                    f"Group A: {sent_counts['A']}\n"
                    f"Group B: {sent_counts['B']}\n"
                    f"Group C: {sent_counts['C']}\n"
                    f"Group D: {sent_counts['D']}\n\n"
                    f"Processed loop counts: {total_processed_counter} links."
                )
                await status_msg.edit_text(progress_text, parse_mode="HTML")
            gc.collect() 
            await asyncio.sleep(2.5) 
        except Exception:
            if os.path.exists(video_filename): os.remove(video_filename)
            continue
    await message.reply_text("🎉 All tasks finished loop successfully with video clips!", parse_mode="HTML")

async def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("👋 Premium Video Clipper Bot Active!")))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.TEXT, process_automated_input))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT, monitor_live_group_links))
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    while True: await asyncio.sleep(3600)

def main():
    t = threading.Thread(target=run_render_port_server, daemon=True)
    t.start()
    try: asyncio.run(run_bot())
    except KeyboardInterrupt: pass

if __name__ == '__main__': main()
