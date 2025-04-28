# bot.py

import os
import aiohttp
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from zipfile import ZipFile

from config import BOT_TOKEN, API_ID, API_HASH, OWNER_ID

bot = Client(
    "OWNER_IS_MR_MAYURESHKUMAR_BOT",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

user_data = {}

# Safe file download
async def safe_download(session, url, dest):
    try:
        async with session.get(url) as response:
            if response.status == 200:
                with open(dest, 'wb') as f:
                    while True:
                        chunk = await response.content.read(1024)
                        if not chunk:
                            break
                        f.write(chunk)
                return True
            else:
                return False
    except Exception:
        return False

# Folder size checker
async def get_folder_size(folder):
    total = 0
    for dirpath, _, filenames in os.walk(folder):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total

# Zip creator
async def zip_folder(folder_path, zip_path):
    with ZipFile(zip_path, 'w') as zipf:
        for root, _, files in os.walk(folder_path):
            for file in files:
                full_path = os.path.join(root, file)
                relative_path = os.path.relpath(full_path, folder_path)
                zipf.write(full_path, relative_path)

# Flood safe sending
async def flood_safe_send(client, chat_id, file_path):
    try:
        await client.send_document(chat_id, file_path)
    except Exception as e:
        if "FloodWait" in str(e):
            wait_time = int(str(e).split("FloodWait")[1].split()[0])
            await asyncio.sleep(wait_time + 2)
            await client.send_document(chat_id, file_path)
        else:
            print(f"Error sending file: {e}")

# Bot start command
@bot.on_message(filters.command("start") & filters.private)
async def start(client, message: Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("Access Denied!")
        return
    await message.reply(
        "OWNER IS MR=MAYURESHKUMAR 👑\n\nChoose what you want to do:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✔ Batch Download", callback_data="batch_download")],
            [InlineKeyboardButton("➕ Forward One-by-One", callback_data="forward_files")]
        ])
    )

# Receive text or document (links)
@bot.on_message((filters.document | filters.text) & filters.private)
async def receive_links(client, message: Message):
    if message.from_user.id != OWNER_ID:
        return

    uid = message.from_user.id
    links = []

    if message.document:
        if message.document.file_name.endswith('.txt'):
            file_path = await message.download()
            with open(file_path, 'r') as f:
                links = [line.strip() for line in f if line.strip()]
            os.remove(file_path)
        else:
            await message.reply("Only .txt files are allowed!")
            return
    else:
        links = message.text.strip().splitlines()

    user_data[uid] = {"links": links}
    await message.reply(
        f"Received {len(links)} links!\n\nSelect Mode:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✔ Batch Download", callback_data="batch_download")],
            [InlineKeyboardButton("➕ Forward One-by-One", callback_data="forward_files")]
        ])
    )

# Batch download logic
@bot.on_callback_query(filters.regex("batch_download"))
async def batch_download_handler(client, callback_query):
    if callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("Access Denied!", show_alert=True)
        return

    uid = callback_query.from_user.id
    links = user_data.get(uid, {}).get("links", [])

    if not links:
        await callback_query.answer("No links found!", show_alert=True)
        return

    base_folder = f"downloads_{uid}"
    video_folder = os.path.join(base_folder, "Videos")
    image_folder = os.path.join(base_folder, "Images")
    os.makedirs(video_folder, exist_ok=True)
    os.makedirs(image_folder, exist_ok=True)

    downloaded_files = set()

    async with aiohttp.ClientSession() as session:
        for link in links:
            filename = link.split("/")[-1].split("?")[0]
            ext = filename.lower().split(".")[-1]
            dest_folder = None

            if ext in ["mp4", "mkv"]:
                dest_folder = video_folder
            elif ext in ["jpg", "jpeg", "png", "gif"]:
                dest_folder = image_folder
            else:
                continue  # Skip non-video/image

            filepath = os.path.join(dest_folder, filename)

            if filename in downloaded_files:
                continue

            success = await safe_download(session, link, filepath)
            if success:
                downloaded_files.add(filename)
            else:
                print(f"Failed: {link}")

    # Now batch and send
    for folder_type in ["Videos", "Images"]:
        folder_path = os.path.join(base_folder, folder_type)
        if not os.path.exists(folder_path):
            continue

        batch_num = 1
        current_batch = os.path.join(folder_path, f"batch_{batch_num}")
        os.makedirs(current_batch, exist_ok=True)

        for file in sorted(os.listdir(folder_path)):
            src_file = os.path.join(folder_path, file)
            dest_file = os.path.join(current_batch, file)
            shutil.move(src_file, dest_file)

            size = await get_folder_size(current_batch)
            if size >= 500 * 1024 * 1024:  # 500MB
                zip_name = f"{folder_type}_batch_{batch_num}.zip"
                await zip_folder(current_batch, zip_name)
                await flood_safe_send(client, callback_query.message.chat.id, zip_name)
                os.remove(zip_name)

                batch_num += 1
                current_batch = os.path.join(folder_path, f"batch_{batch_num}")
                os.makedirs(current_batch, exist_ok=True)

        if os.listdir(current_batch):
            zip_name = f"{folder_type}_batch_{batch_num}.zip"
            await zip_folder(current_batch, zip_name)
            await flood_safe_send(client, callback_query.message.chat.id, zip_name)
            os.remove(zip_name)

    shutil.rmtree(base_folder)
    await callback_query.message.reply("All files sent in batches!")

# Forward files logic
@bot.on_callback_query(filters.regex("forward_files"))
async def forward_files_handler(client, callback_query):
    if callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("Access Denied!", show_alert=True)
        return

    uid = callback_query.from_user.id
    links = user_data.get(uid, {}).get("links", [])

    if not links:
        await callback_query.answer("No links found!", show_alert=True)
        return

    await callback_query.message.edit("Starting to forward files one by one...")

    async with aiohttp.ClientSession() as session:
        for link in links:
            filename = link.split("/")[-1].split("?")[0]
            ext = filename.lower().split(".")[-1]
            filepath = f"temp_{uid}_{filename}"

            if ext not in ["mp4", "mkv", "jpg", "jpeg", "png", "gif"]:
                continue

            success = await safe_download(session, link, filepath)
            if success:
                try:
                    if ext in ["mp4", "mkv"]:
                        await client.send_video(callback_query.message.chat.id, filepath)
                    elif ext in ["jpg", "jpeg", "png", "gif"]:
                        await client.send_photo(callback_query.message.chat.id, filepath)
                    await asyncio.sleep(2)  # Safe delay
                except Exception as e:
                    print(f"Error sending file: {e}")

            if os.path.exists(filepath):
                os.remove(filepath)

    await callback_query.message.reply("All files forwarded successfully!")

# Run bot
if __name__ == "__main__":
    bot.run()