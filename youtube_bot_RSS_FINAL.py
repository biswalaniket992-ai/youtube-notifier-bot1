from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler, ContextTypes
import os
import json
import threading
import time
from datetime import datetime
import requests
import feedparser

try:
    import yt_dlp
except ImportError:
    print("Installing yt-dlp...")
    os.system("pip install yt-dlp")
    import yt_dlp

# States
ADDING_CHANNELS, CONFIRM_DONE = range(2)

# Your Telegram ID
YOUR_TELEGRAM_ID = 5597686391

# File to store user channels and last videos
DATA_FILE = "yt_channels.json"

# MAX VIDEO SIZE FOR TELEGRAM (2GB in bytes)
MAX_VIDEO_SIZE = 2 * 1024 * 1024 * 1024  # 2GB

# Extract channel ID from YouTube URL
def extract_channel_id(url):
    """Extract channel ID from various YouTube URL formats"""
    try:
        if "youtube.com" in url or "youtu.be" in url:
            if "@" in url:
                return url.split("@")[1].split("/")[0]
            elif "/channel/" in url:
                return url.split("/channel/")[1].split("/")[0]
            elif "/c/" in url:
                return url.split("/c/")[1].split("/")[0]
        return None
    except:
        return None

# Load user data
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

# Save user data
def save_data(data):
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")

# Get latest video from YouTube RSS (NO BOT DETECTION!)
def get_latest_video_from_rss(channel_id):
    """Get latest video from YouTube RSS feed - much more reliable!"""
    try:
        # YouTube RSS URL format
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        
        response = requests.get(rss_url, timeout=10)
        response.raise_for_status()
        
        feed = feedparser.parse(response.content)
        
        if feed.entries:
            latest_entry = feed.entries[0]
            video_info = {
                'id': latest_entry.id.split('yt:video_id:')[1],
                'title': latest_entry.title,
                'url': latest_entry.link,
                'published': latest_entry.published,
            }
            return video_info
    except Exception as e:
        print(f"Error getting RSS feed: {e}")
    return None

# Download and send video
def download_and_send_video(application, video_url, channel_name, video_title):
    """Download video and send to user - handles large files"""
    try:
        # Create folder for videos
        if not os.path.exists("downloads"):
            os.makedirs("downloads")
        
        print(f"Downloading video from {channel_name}...")
        
        # First, get video info to check size
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_unavailable_fragments': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                video_size = info.get('filesize')
                
                print(f"Video: {video_title}")
                print(f"Size: {video_size} bytes")
                
                # If video is too big, send link instead
                if video_size and video_size > MAX_VIDEO_SIZE:
                    print(f"⚠️ Video too large ({video_size / (1024**3):.2f} GB), sending link instead...")
                    try:
                        application.bot.send_message(
                            chat_id=YOUR_TELEGRAM_ID,
                            text=f"🎥 New video from {channel_name}\n\n"
                                 f"📝 {video_title}\n"
                                 f"⚠️ File size: {video_size / (1024**3):.2f} GB (too large)\n\n"
                                 f"🔗 Watch: {video_url}"
                        )
                    except Exception as e:
                        print(f"Error sending message: {e}")
                    return
        except Exception as e:
            print(f"Info extraction failed: {e}")
            # Send link if we can't get info
            try:
                application.bot.send_message(
                    chat_id=YOUR_TELEGRAM_ID,
                    text=f"🎥 New video from {channel_name}\n\n"
                         f"📝 {video_title}\n\n"
                         f"🔗 Watch: {video_url}"
                )
            except:
                pass
            return
        
        # Download video
        ydl_opts = {
            'format': 'best[ext=mp4]',
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'skip_unavailable_fragments': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_path = ydl.prepare_filename(info)
            
            if os.path.exists(video_path):
                file_size = os.path.getsize(video_path)
                print(f"Downloaded: {video_path} ({file_size / (1024**2):.2f} MB)")
                
                # Check if file is too large
                if file_size > MAX_VIDEO_SIZE:
                    print(f"File too large after download, sending link...")
                    try:
                        application.bot.send_message(
                            chat_id=YOUR_TELEGRAM_ID,
                            text=f"🎥 New video from {channel_name}\n\n"
                                 f"📝 {video_title}\n"
                                 f"⚠️ File size: {file_size / (1024**3):.2f} GB\n\n"
                                 f"🔗 Watch: {video_url}"
                        )
                    except Exception as e:
                        print(f"Error: {e}")
                    os.remove(video_path)
                    return
                
                # Send video
                print(f"Sending video to Telegram...")
                try:
                    with open(video_path, 'rb') as video_file:
                        application.bot.send_video(
                            chat_id=YOUR_TELEGRAM_ID,
                            video=video_file,
                            caption=f"🎥 {channel_name}\n{video_title[:100]}"
                        )
                    print(f"✅ Video sent!")
                except Exception as e:
                    print(f"Error: {e}")
                    try:
                        application.bot.send_message(
                            chat_id=YOUR_TELEGRAM_ID,
                            text=f"🎥 {channel_name}\n{video_title}\n🔗 {video_url}"
                        )
                    except:
                        pass
                
                # Cleanup
                try:
                    os.remove(video_path)
                except:
                    pass
        
    except Exception as e:
        print(f"Error: {e}")

# Check for new videos periodically using RSS
def check_new_videos(application):
    """Check for new videos every 6 hours using RSS feeds"""
    print("🎬 Video checker started (using RSS feeds)!")
    first_run = True
    
    while True:
        try:
            data = load_data()
            
            if data:
                for channel_id, channel_info in data.items():
                    try:
                        latest_video = get_latest_video_from_rss(channel_id)
                        
                        if latest_video:
                            video_id = latest_video['id']
                            last_video_id = channel_info.get('last_video_id')
                            
                            # If new video found
                            if video_id != last_video_id:
                                if not first_run:
                                    print(f"🎥 New: {latest_video['title']}")
                                    download_and_send_video(
                                        application,
                                        latest_video['url'],
                                        channel_info['name'],
                                        latest_video['title']
                                    )
                                
                                # Update last video
                                channel_info['last_video_id'] = video_id
                                channel_info['updated_at'] = datetime.now().isoformat()
                                save_data(data)
                    except Exception as e:
                        print(f"Error checking {channel_id}: {e}")
            
            first_run = False
        
        except Exception as e:
            print(f"Error: {e}")
        
        print(f"⏰ Next check in 6 hours...")
        time.sleep(21600)

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    
    if not data:
        context.user_data['channels'] = {}
        await update.message.reply_text(
            "🎬 YouTube Video Notifier Bot\n\n"
            "Add up to 3 YouTube channels!\n\n"
            "📝 Send me a YouTube channel link:\n"
            "• youtube.com/@TechnoGamerz\n"
            "• youtube.com/c/TechnoGamerz"
        )
        return ADDING_CHANNELS
    else:
        channels_list = "\n".join([f"✅ {ch['name']}" for ch in data.values()])
        await update.message.reply_text(
            f"✅ You have {len(data)} channel(s)!\n\n"
            f"{channels_list}\n\n"
            "Videos coming every 6 hours!"
        )
        return ConversationHandler.END

# Receive channel link
async def receive_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    data = load_data()
    
    channel_id = extract_channel_id(user_text)
    
    if not channel_id:
        await update.message.reply_text("❌ Invalid link!\n\nTry: youtube.com/@channelname")
        return ADDING_CHANNELS
    
    if channel_id in data:
        await update.message.reply_text("⚠️ Already added!")
        return ADDING_CHANNELS
    
    if len(data) >= 3:
        await update.message.reply_text("❌ Max 3 channels!")
        return ADDING_CHANNELS
    
    channel_name = channel_id
    try:
        # Try to get channel name from RSS
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        response = requests.get(rss_url, timeout=5)
        feed = feedparser.parse(response.content)
        if feed.feed.get('title'):
            channel_name = feed.feed.title
    except:
        channel_name = channel_id
    
    data[channel_id] = {
        'name': channel_name,
        'url': user_text,
        'last_video_id': None,
        'added_at': datetime.now().isoformat()
    }
    save_data(data)
    
    channels_count = len(data)
    
    if channels_count < 3:
        kb = [[
            InlineKeyboardButton("📄 Add More", callback_data="add_more"),
            InlineKeyboardButton("✅ Done", callback_data="done")
        ]]
    else:
        kb = [[InlineKeyboardButton("✅ Done", callback_data="done")]]
    
    await update.message.reply_text(
        f"✅ Added: {channel_name}\n"
        f"📊 {channels_count}/3\n\n"
        "What next?",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    
    return CONFIRM_DONE

# Add more button
async def add_more(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("📝 Send another channel link:")
    return ADDING_CHANNELS

# Done button
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "✅ Done!\n\n"
        "🎥 Videos coming every 6 hours!"
    )
    return ConversationHandler.END

def main():
    TOKEN = "8535489631:AAGCa_O2s6oMRwP6XU6i6t6515612jDPbIA"
    
    app = Application.builder().token(TOKEN).build()
    
    print("Starting YouTube Video Notifier Bot...")
    checker_thread = threading.Thread(target=check_new_videos, args=(app,), daemon=True)
    checker_thread.start()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ADDING_CHANNELS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_channel),
            ],
            CONFIRM_DONE: [
                CallbackQueryHandler(add_more, pattern="^add_more$"),
                CallbackQueryHandler(done, pattern="^done$"),
            ]
        },
        fallbacks=[CommandHandler("start", start)]
    )
    
    app.add_handler(conv_handler)
    
    print("✅ Bot running!")
    app.run_polling()

if __name__ == "__main__":
    main()