
import os
import aiohttp
import asyncio
import shutil
from pyrogram import Client, filters
from pyrogram.types import Message
from zipfile import ZipFile
from tqdm import tqdm
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID

bot = Client(
    "terabox_downloader_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

user_data = {}

async def get_folder_size(folder):
    total = 0
    for dirpath, _, filenames in os.walk(folder):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total

async def parse_link(link):
    if "diskwala" in link or "xdisk" in link or "terabox" in link:
        return link  # Dummy parser for now
    return None

async def download_with_progress(session, url, dest_folder, message):
    filename = url.split("/")[-1].split("?")[0]
    dest_path = os.path.join(dest_folder, filename)
    if os.path.exists(dest_path):
        print(f"{filename} already exists, skipping.")
        return dest_path

    try:
        async with session.get(url) as response:
            total_size = int(response.headers.get('content-length', 0))
            with open(dest_path, "wb") as f, tqdm(total=total_size, unit='B', unit_scale=True, desc=filename) as pbar:
                while True:
                    chunk = await response.content.read(1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    pbar.update(len(chunk))

        await message.edit_text(f"✅ Downloaded: `{filename}`")
        return dest_path
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return None

@bot.on_message(filters.command("start") & filters.private)
async def start(client, message: Message):
    if message.from_user.id != OWNER_ID:
        await message.reply_text("❌ Access Denied!")
        return
    await message.reply_text("👋 Namaste! Apne Terabox/Diskwala/Xdisk links bhejiye.")

@bot.on_message((filters.text | filters.document) & filters.private)
async def handle_links(client, message: Message):
    if message.from_user.id != OWNER_ID:
        return

    links = []
    if message.document:
        if message.document.file_name.endswith(".txt"):
            path = await message.download()
            with open(path, "r") as f:
                links = [line.strip() for line in f if line.strip()]
            os.remove(path)
        else:
            await message.reply("❌ Sirf .txt files allow hain.")
            return
    else:
        links = message.text.strip().splitlines()

    if not links:
        await message.reply_text("⚠️ Koi valid link nahi mila.")
        return

    await message.reply_text(f"🔎 {len(links)} links mile. Downloading start ho raha hai...")

    await download_all_links(client, message, links)

async def download_all_links(client, message, links):
    base_folder = f"downloads_{message.from_user.id}"
    os.makedirs(base_folder, exist_ok=True)

    session = aiohttp.ClientSession()

    current_folder = os.path.join(base_folder, "folder_1")
    os.makedirs(current_folder, exist_ok=True)
    folder_index = 1

    downloaded_files = set()

    for link in links:
        real_url = await parse_link(link)
        if not real_url:
            continue

        filename = real_url.split("/")[-1].split("?")[0]
        if filename in downloaded_files:
            print(f"Skipping duplicate file: {filename}")
            continue

        size_now = await get_folder_size(current_folder)
        if size_now >= 500 * 1024 * 1024:
            folder_index += 1
            current_folder = os.path.join(base_folder, f"folder_{folder_index}")
            os.makedirs(current_folder, exist_ok=True)

        try:
            downloading_msg = await message.reply_text(f"⬇️ Downloading `{filename}`...")
            file_path = await download_with_progress(session, real_url, current_folder, downloading_msg)
            if file_path:
                downloaded_files.add(filename)
        except Exception as e:
            print(f"Error: {e}")
            continue

    await session.close()

    await zip_and_send_folders(client, message, base_folder)

    shutil.rmtree(base_folder)
    await message.reply_text("✅ Saare files bhej diye gaye. Download complete!")

async def zip_and_send_folders(client, message, base_folder):
    for folder_name in sorted(os.listdir(base_folder)):
        folder_path = os.path.join(base_folder, folder_name)
        zip_name = f"{folder_name}.zip"
        with ZipFile(zip_name, "w") as zipf:
            for root, _, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, folder_path)
                    zipf.write(file_path, arcname)

        try:
            await client.send_document(message.chat.id, zip_name)
            os.remove(zip_name)
        except Exception as e:
            print(f"Error sending ZIP: {e}")

if __name__ == "__main__":
    bot.run()