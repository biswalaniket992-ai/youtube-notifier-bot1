from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler, ContextTypes
import os
import json
import threading
import time
from datetime import datetime

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

# Get latest video from channel
def get_latest_video(channel_id):
    """Get latest video info from channel"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
            'skip_unavailable_fragments': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/@{channel_id}/videos", download=False)
            if info and 'entries' in info and len(info['entries']) > 0:
                return info['entries'][0]
    except Exception as e:
        print(f"Error getting video: {e}")
    return None

# Download and send video
def download_and_send_video(application, video_url, channel_name):
    """Download video and send to user"""
    try:
        # Create folder for videos
        if not os.path.exists("downloads"):
            os.makedirs("downloads")
        
        print(f"Downloading video from {channel_name}...")
        
        # Download video with yt-dlp options to avoid bot detection
        ydl_opts = {
            'format': 'best[ext=mp4]',
            'outtmpl': 'downloads/%(title)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'skip_unavailable_fragments': True,
            'extractor_args': {'youtube': {'skip': ['dash', 'hls']}},
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_path = ydl.prepare_filename(info)
            
            if os.path.exists(video_path):
                print(f"Sending video: {video_path}")
                # Send video
                try:
                    with open(video_path, 'rb') as video_file:
                        application.bot.send_video(
                            chat_id=YOUR_TELEGRAM_ID,
                            video=video_file,
                            caption=f"🎥 New video from {channel_name}\n🔗 {video_url}"
                        )
                    print(f"✅ Video sent successfully!")
                except Exception as e:
                    print(f"Error sending video: {e}")
                
                # Delete after sending
                try:
                    os.remove(video_path)
                except:
                    pass
        
    except Exception as e:
        print(f"Error downloading video: {e}")

# Check for new videos periodically
def check_new_videos(application):
    """Background task to check for new videos every 6 hours"""
    print("🎬 Video checker started!")
    first_run = True
    
    while True:
        try:
            data = load_data()
            
            if data:
                for channel_id, channel_info in data.items():
                    try:
                        latest_video = get_latest_video(channel_id)
                        
                        if latest_video:
                            video_id = latest_video['id']
                            last_video_id = channel_info.get('last_video_id')
                            
                            # If new video found and different from last one
                            if video_id != last_video_id:
                                if not first_run:  # Don't send on first run
                                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                                    print(f"🎥 New video from {channel_info['name']}: {video_url}")
                                    download_and_send_video(application, video_url, channel_info['name'])
                                
                                # Update last video ID
                                channel_info['last_video_id'] = video_id
                                channel_info['updated_at'] = datetime.now().isoformat()
                                save_data(data)
                    except Exception as e:
                        print(f"Error checking {channel_id}: {e}")
            
            first_run = False
        
        except Exception as e:
            print(f"Error in check_new_videos: {e}")
        
        print(f"⏰ Checked at {datetime.now()}. Next check in 6 hours...")
        # Wait 6 hours before checking again (21600 seconds)
        time.sleep(21600)

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    
    if not data:
        context.user_data['channels'] = {}
        await update.message.reply_text(
            "🎬 YouTube Video Notifier Bot\n\n"
            "Add up to 3 YouTube channels and I'll send you new videos!\n\n"
            "📝 Send me a YouTube channel link\n\n"
            "Examples:\n"
            "• youtube.com/@TechnoGamerz\n"
            "• youtube.com/c/TechnoGamerz\n"
            "• @TechnoGamerz"
        )
        return ADDING_CHANNELS
    else:
        channels_list = "\n".join([f"✅ {ch['name']}" for ch in data.values()])
        await update.message.reply_text(
            f"✅ You have {len(data)} channel(s) configured!\n\n"
            f"{channels_list}\n\n"
            "🎥 New videos will be sent automatically every 6 hours!"
        )
        return ConversationHandler.END

# Receive channel link
async def receive_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    data = load_data()
    
    # Extract channel info
    channel_id = extract_channel_id(user_text)
    
    if not channel_id:
        await update.message.reply_text("❌ Invalid YouTube link!\n\nTry:\n• youtube.com/@channelname\n• youtube.com/c/channelname")
        return ADDING_CHANNELS
    
    # Check if already added (avoid duplicates)
    if channel_id in data:
        await update.message.reply_text("⚠️ This channel is already added!")
        return ADDING_CHANNELS
    
    # Check if max 3 channels reached
    if len(data) >= 3:
        await update.message.reply_text("❌ You can only add maximum 3 channels!")
        return ADDING_CHANNELS
    
    # Get channel name
    channel_name = "Unknown"
    try:
        ydl_opts = {'quiet': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/@{channel_id}", download=False)
            channel_name = info.get('uploader', channel_id)
    except:
        channel_name = channel_id
    
    # Add channel to data
    data[channel_id] = {
        'name': channel_name,
        'url': user_text,
        'last_video_id': None,
        'added_at': datetime.now().isoformat()
    }
    save_data(data)
    
    channels_count = len(data)
    
    if channels_count < 3:
        kb = [
            [
                InlineKeyboardButton("📄 Add More", callback_data="add_more"),
                InlineKeyboardButton("✅ Done", callback_data="done")
            ]
        ]
    else:
        kb = [[InlineKeyboardButton("✅ Done", callback_data="done")]]
    
    await update.message.reply_text(
        f"✅ Added: {channel_name}\n"
        f"📊 Total channels: {channels_count}/3\n\n"
        "What would you like to do?",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    
    return CONFIRM_DONE

# Add more button
async def add_more(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "📝 Send me another YouTube channel link:"
    )
    return ADDING_CHANNELS

# Done button
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "✅ Setup complete!\n\n"
        "🎥 I'll check for new videos every 6 hours and send them to you automatically.\n\n"
        "Thank you for using YouTube Video Notifier Bot! 🎬"
    )
    
    return ConversationHandler.END

def main():
    TOKEN = "8535489631:AAGCa_O2s6oMRwP6XU6i6t6515612jDPbIA"
    
    app = Application.builder().token(TOKEN).build()
    
    # Start background video checker in a separate thread
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
    
    print("✅ Bot is running! Type /start to begin.")
    app.run_polling()

if __name__ == "__main__":
    main()