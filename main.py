import re
import os
import asyncio
import subprocess
import random
import threading
import gc  # Server ki RAM safa karne ke liye
from http.server import SimpleHTTPRequestHandler, HTTPServer
from telegram import Update, LinkPreviewOptions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==========================================
# 1. BOT TOKEN & GROUP E CONFIGURATION
# ==========================================
# ⚠️ Yahan "" ke andar apna asli Telegram Bot Token daalna mat bhoolna!
BOT_TOKEN = "8648804848:AAFM_CH5-3PKHiOrfqyK3giZZbS7WFfbQpQ"

# 🌟 Aapke diye hue Group E ka asli Chat ID yahan set kar diya hai!
GROUP_E_CHAT_ID = -1005127775582  

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

# Saare monitoring groups ke chat IDs ki ek fast list lookup ke liye
MONITORED_CHAT_IDS = [g["chat_id"] for g in GROUPS_CONFIG.values()]

# ==========================================
# 3. RENDER PORT BINDER
# ==========================================
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
# 4. ULTRA-LOW RAM VIDEO CUTTER (20s Mode)
# ==========================================
async def download_and_trim_video(url: str, output_filename: str) -> bool:
    try:
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36"
        ]
        cmd = [
            "yt-dlp", "-g", "--no-playlist", "--socket-timeout", "4",
            "--prefer-free-formats", "--no-warnings", "--no-cache-dir",
            "--user-agent", random.choice(user_agents),
            "-f", "worst[ext=mp4]/worst", url
        ]
        process = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=6.0)
        except asyncio.TimeoutError:
            process.kill()
            return False
            
        stream_url = stdout.decode('utf-8').strip().split('\n')[0]
        if not stream_url or "http" not in stream_url:
            return False
            
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-threads", "1", "-ss", "00:00:05", "-i", stream_url, "-t", "20",
            "-c:v", "libx264", "-an", "-preset", "ultrafast", "-tune", "fastdecode",
            "-pix_fmt", "yuv420p", output_filename
        ]
        ffmpeg_process = await asyncio.create_subprocess_exec(*ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            await asyncio.wait_for(ffmpeg_process.communicate(), timeout=15.0)
        except asyncio.TimeoutError:
            ffmpeg_process.kill()
            return False
        
        return ffmpeg_process.returncode == 0 and os.path.exists(output_filename)
    except Exception:
        return False

# ==========================================
# 5. ENGINE 1: LIVE GROUP MONITORING & ROUTER
# ==========================================
async def monitor_live_group_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Groups me aane wale text links par nazar rakhne aur filter karne wala engine"""
    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id
    # Agar message hamare target groups (A, B, C, D) me se kisi ek me aaya hai
    if chat_id in MONITORED_CHAT_IDS:
        links = LINK_REGEX.findall(update.message.text)
        if not links:
            return

        posted_database = get_posted_data()
        for link in links:
            link = link.strip()
            
            # 🌟 LOGIC: Agar link abhi tak database me nahi hai (yani iska video clip nahi bana hai)
            if link not in posted_database:
                try:
                    # 1. Message ko chupchaap Group E me transfer/forward karein
                    forward_text = f"📥 <b>Unprocessed Incoming Link:</b>\n\n🔗 {link}\n\n👤 From Group ID: <code>{chat_id}</code>"
                    await context.bot.send_message(chat_id=GROUP_E_CHAT_ID, text=forward_text, parse_mode="HTML")
                    
                    # 2. Original group se us link wale message ko delete kar dein
                    await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
                    print(f"♻️ Moved unprocessed link to Group E & deleted from source group: {link}")
                    break  # Ek baar handle hone par loop break karein
                except Exception as e:
                    print(f"⚠️ Live router error: {e}")

# ==========================================
# 6. ENGINE 2: AUTOMATED FILE PROCESSING
# ==========================================
async def process_automated_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await context.bot.get_file(update.message.document.file_id)
    content = await file.download_as_bytearray()
    links = LINK_REGEX.findall(content.decode('utf-8'))
    
    if not links:
        await update.message.reply_text("❌ Is file me koi valid links nahi mile!")
        return

    join_link = ""
    if update.message.caption:
        found_caption_links = LINK_REGEX.findall(update.message.caption)
        if found_caption_links:
            join_link = found_caption_links[0].strip()

    status_msg = await update.message.reply_text("🔍 Video-Clip (20s) Memory-Flush Filter chalu...")
    
    posted_database = get_posted_data()
    sent_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    normal_groups_pool = ["A", "C", "D"]
    pool_index = 0
    
    backup_storage = {"A": [], "B": [], "C": [], "D": []}

    for link in links:
        link = link.strip()
        if not link or link in posted_database:
            continue

        is_adult_link = any(domain in link.lower() for domain in TARGET_BLOCKLIST)

        target_key = None
        if is_adult_link:
            if sent_counts["B"] < GROUPS_CONFIG["B"]["limit"]:
                target_key = "B"
            else:
                continue
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
                    if pool_index == started_index:
                        break
            if not target_key:
                continue

        group = GROUPS_CONFIG[target_key]
        video_filename = f"preview_{int(asyncio.get_event_loop().time())}.mp4"

        try:
            if join_link:
                post_format = f"{link}\n\n✨ <a href='{join_link}'>Join us!</a>"
            else:
                post_format = f"{link}"
            
            video_success = await download_and_trim_video(link, video_filename)
            
            if video_success:
                with open(video_filename, "rb") as video_file:
                    await context.bot.send_animation(
                        chat_id=group["chat_id"], animation=video_file,
                        caption=post_format, parse_mode="HTML"
                    )
                if os.path.exists(video_filename):
                    os.remove(video_filename)
            else:
                preview_settings = LinkPreviewOptions(
                    is_disabled=False, prefer_large_media=True, show_above_text=True 
                )
                await context.bot.send_message(
                    chat_id=group["chat_id"], text=post_format, 
                    parse_mode="HTML", link_preview_options=preview_settings
                )
            
            with open(DB_FILE, "a", encoding="utf-8") as f:
                f.write(link + "\n")
            posted_database.add(link)
            
            backup_storage[target_key].append(link)
            sent_counts[target_key] += 1
            
            if sum(sent_counts.values()) % 5 == 0:
                progress_text = (
                    f"⏳ <b>Live Status (Safe Mode):</b>\n\n"
                    f"🟢 Group A: {sent_counts['A']}/{GROUPS_CONFIG['A']['limit']}\n"
                    f"🔴 Group B: {sent_counts['B']}/{GROUPS_CONFIG['B']['limit']}\n"
                    f"🟢 Group C: {sent_counts['C']}/{GROUPS_CONFIG['C']['limit']}\n"
                    f"🟢 Group D: {sent_counts['D']}/{GROUPS_CONFIG['D']['limit']}\n\n"
                    f"📦 Total Processed: {sum(sent_counts.values())} links."
                )
                await status_msg.edit_text(progress_text, parse_mode="HTML")
            
            gc.collect() 
            await asyncio.sleep(8.0) 
            
        except Exception as e:
            if os.path.exists(video_filename):
                os.remove(video_filename)
            if "Flood" in str(e):
                await asyncio.sleep(300) 
            continue

    await update.message.reply_text("📦 Posts complete! Backup logs send ho rahe hain...")
    for key, group_info in GROUPS_CONFIG.items():
        links_to_save = backup_storage[key]
        if links_to_save:
            temp_file_name = f"Group_{key}_Backup_Links.txt"
            with open(temp_file_name, "w", encoding="utf-8") as f:
                for b_link in links_to_save:
                    f.write(b_link + "\n")
            try:
                with open(temp_file_name, "rb") as f:
                    await context.bot.send_document(
                        chat_id=group_info["chat_id"], document=f,
                        caption=f"📋 <b>{group_info['name']} Safe Record Backup</b>",
                        parse_mode="HTML"
                    )
            except Exception:
                pass
            if os.path.exists(temp_file_name):
                os.remove(temp_file_name)

    await update.message.reply_text("🎉 All tasks finished successfully!", parse_mode="HTML")

# ==========================================
# 7. LIFECYCLE MANAGEMENT WITH DUAL HANDLERS
# ==========================================
async def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Core commands aur document file parser system
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("👋 Hybrid Video Strict Bot Active!")))
    app.add_handler(MessageHandler(filters.Document.ALL, process_automated_file))
    
    # 🌟 MessageHandler for live text links routing
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), monitor_live_group_links))
    
    await app.initialize()
    await app.start()
    print("🚀 Hybrid Bot engines initialized successfully...")
    await app.updater.start_polling(drop_pending_updates=True)
    
    while True:
        await asyncio.sleep(3600)

def main():
    t = threading.Thread(target=run_render_port_server, daemon=True)
    t.start()
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("Bot stopped.")

if __name__ == '__main__':
    main()
