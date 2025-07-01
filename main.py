import asyncio
import time
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from HyperDL import HyperTGDownloader, DownloadStatus
from config import Config

helper_bots = {}
for i, token in enumerate(Config.HELPER_TOKENS.split()):
    helper_bots[i] = Client(
        f"helper_{i}",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        bot_token=token,
        in_memory=True
    )
helper_loads = {i: 0 for i in helper_bots}

downloader = HyperTGDownloader(
    helper_bots=helper_bots,
    helper_loads=helper_loads,
    num_parts=Config.HYPER_THREADS,
    chunk_size=Config.CHUNK_SIZE,
    download_dir=Config.DOWNLOAD_DIR,
    progress_interval=2.0
)

main_bot = Client(
    "main_bot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN,
    in_memory=True
)

DOWNLOAD_TASKS = {}

async def progress_callback(status, downloaded_bytes, total_bytes, percentage, file_name, bot, message, start_time):
    elapsed = time.time() - start_time
    speed = downloaded_bytes / elapsed if elapsed > 0 else 0
    eta = (total_bytes - downloaded_bytes) / speed if speed > 0 else float('inf')
    text = (
        f"📥 Downloading: {file_name}\n"
        f"Progress: {percentage:.1f}%\n"
        f"Downloaded: {downloaded_bytes / 1024 / 1024:.2f} MB / {total_bytes / 1024 / 1024:.2f} MB\n"
        f"Speed: {speed / 1024 / 1024:.2f} MB/s\n"
        f"Elapsed: {elapsed:.0f} seconds\n"
        f"ETA: {eta:.0f} seconds"
    )
    if status == DownloadStatus.DOWNLOADING:
        try:
            await message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Cancel", callback_data=f"cancel_{message.id}")]
                ])
            )
        except Exception:
            pass
    elif status == DownloadStatus.COMPLETED:
        await message.edit_text(f"✅ Download completed: {file_name}")
    elif status == DownloadStatus.CANCELLED:
        await message.edit_text(f"❌ Download cancelled: {file_name}")
    elif status == DownloadStatus.ERROR:
        await message.edit_text(f"❗ Download failed: {file_name}")

@main_bot.on_message(filters.command("dl") & filters.reply)
async def download_handler(client, message):
    replied = message.reply_to_message
    if not replied or not hasattr(replied, 'media'):
        await message.reply("Reply to a media message with /dl.")
        return
    status_message = await message.reply("Downloading, please wait...")
    start_time = time.time()
    DOWNLOAD_TASKS[message.id] = downloader
    try:
        file_path = await downloader.download_media(
            message=replied,
            file_name=f"{Config.DOWNLOAD_DIR}/{replied.id}_{downloader.file_name}",
            progress=progress_callback,
            progress_args=(client, status_message, start_time),
            dump_chat=Config.LEECH_DUMP_CHAT
        )
        if file_path:
            await client.send_document(
                chat_id=message.chat.id,
                document=file_path,
                caption=f"Downloaded: {downloader.file_name}"
            )
            await status_message.delete()
        else:
            await status_message.edit_text("Download failed or cancelled.")
    except Exception as e:
        await status_message.edit_text(f"Error: {str(e)}")
    finally:
        DOWNLOAD_TASKS.pop(message.id, None)

@main_bot.on_callback_query(filters.regex(r"cancel_(\d+)"))
async def cancel_download(client, callback_query):
    message_id = int(callback_query.data.split("_")[1])
    downloader = DOWNLOAD_TASKS.get(message_id)
    if downloader:
        downloader._cancel_event.set()
        downloader._download_status = DownloadStatus.CANCELLED
        await callback_query.message.edit_text("Download cancellation requested.")
    await callback_query.answer()

async def main():
    await asyncio.gather(*(bot.start() for bot in helper_bots.values()))
    await main_bot.start()
    await downloader.start()
    print("All bots started. Send /dl as a reply to a media message.")
    await idle()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    finally:
        loop.run_until_complete(main_bot.stop())
        for bot in helper_bots.values():
            loop.run_until_complete(bot.stop())
        loop.close()
