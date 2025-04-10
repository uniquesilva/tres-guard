import os
import time
import threading
from flask import Flask
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram import ChatPermissions, ParseMode
from collections import defaultdict

# --- Flask keep-alive server ---
app = Flask(__name__)

@app.route('/')
def home():
    return 'Tres Guard is live!'

def run_flask():
    app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_flask).start()

# --- Token and secrets ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Please set the BOT_TOKEN in Replit Secrets")

# --- Storage ---
BANNED_KEYWORDS = ["airdrop", "giveaway", "http", "t.me/", "claim now"]
custom_filters = set()
admin_only_mode = defaultdict(lambda: False)
report_counts = defaultdict(int)
message_timestamps = {}
muted_users = {}
user_activity = defaultdict(int)

# --- Utility ---
def is_admin(update):
    user_id = update.effective_user.id
    member = update.effective_chat.get_member(user_id)
    return member.status in ["administrator", "creator"]

# --- Commands ---
def start(update, context):
    update.message.reply_text("Tres Guard is active and watching your group.")

def help_command(update, context):
    text = (
        "*Tres Guard Help*\n\n"
        "/start - Check bot status\n"
        "/help - Show help message\n"
        "/commands - List commands\n"
        "/filter <word> - Add keyword to filter\n"
        "/filters - Show filter list\n"
        "/removefilter <word> - Remove keyword\n"
        "/adminmode on/off - Only admins can chat\n"
        "/mute @user <seconds> - Mute user\n"
        "/ban @user - Ban user\n"
        "/report - Report a message\n"
        "/setchart <link> - Set chart URL\n"
        "/setrules <text> - Set group rules\n"
        "/rules - Show rules"
    )
    update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

def commands(update, context):
    update.message.reply_text("/start /help /commands /filter /filters /removefilter /adminmode /mute /ban /report /setchart /setrules /rules")

def set_chart(update, context):
    if not is_admin(update):
        return
    context.chat_data['chart'] = " ".join(context.args)
    update.message.reply_text("Chart link updated.")

def set_rules(update, context):
    if not is_admin(update):
        return
    context.chat_data['rules'] = " ".join(context.args)
    update.message.reply_text("Rules updated.")

def show_rules(update, context):
    rules = context.chat_data.get('rules')
    if rules:
        update.message.reply_text(rules)
    else:
        update.message.reply_text("No rules have been set yet.")

# --- Filter management ---
def add_filter(update, context):
    if not is_admin(update):
        update.message.reply_text("Only admins can add filters.")
        return
    if context.args:
        word = " ".join(context.args).lower()
        custom_filters.add(word)
        update.message.reply_text(f"Added '{word}' to filters.")
    else:
        update.message.reply_text("Usage: /filter <word>")

def show_filters(update, context):
    filters_list = BANNED_KEYWORDS + list(custom_filters)
    update.message.reply_text("Current filters:\n" + "\n".join(filters_list))

def remove_filter(update, context):
    if not is_admin(update):
        update.message.reply_text("Only admins can remove filters.")
        return
    if context.args:
        word = " ".join(context.args).lower()
        if word in custom_filters:
            custom_filters.remove(word)
            update.message.reply_text(f"Removed '{word}' from filters.")
        else:
            update.message.reply_text(f"'{word}' is not in custom filters.")
    else:
        update.message.reply_text("Usage: /removefilter <word>")

# --- Admin mode ---
def toggle_admin_mode(update, context):
    chat_id = update.effective_chat.id
    if not is_admin(update):
        update.message.reply_text("Only admins can toggle admin mode.")
        return
    if context.args and context.args[0].lower() == "on":
        admin_only_mode[chat_id] = True
        update.message.reply_text("Admin-only mode is now ON.")
    else:
        admin_only_mode[chat_id] = False
        update.message.reply_text("Admin-only mode is now OFF.")

# --- Mute / Ban ---
def mute_user(update, context):
    if not is_admin(update):
        return
    if not context.args or len(context.args) < 2:
        update.message.reply_text("Usage: /mute @user <seconds>")
        return
    try:
        user = update.message.reply_to_message.from_user
        duration = int(context.args[1])
        until = time.time() + duration
        muted_users[user.id] = until
        permissions = ChatPermissions(can_send_messages=False)
        context.bot.restrict_chat_member(update.effective_chat.id, user.id, permissions, until_date=until)
        update.message.reply_text(f"Muted {user.first_name} for {duration} seconds.")
    except:
        update.message.reply_text("Could not mute user.")

def ban_user(update, context):
    if not is_admin(update):
        return
    try:
        user = update.message.reply_to_message.from_user
        context.bot.kick_chat_member(update.effective_chat.id, user.id)
        update.message.reply_text(f"Banned {user.first_name}.")
    except:
        update.message.reply_text("Could not ban user.")

# --- Report ---
def report(update, context):
    message = update.message
    report_counts[message.message_id] += 1
    update.message.reply_text("Reported. Admins will review this.")

# --- Welcome ---
def welcome(update, context):
    for member in update.message.new_chat_members:
        if member.is_bot or not member.username or any(char.isdigit() for char in member.username):
            try:
                context.bot.kick_chat_member(update.effective_chat.id, member.id)
            except:
                pass
        else:
            context.bot.send_message(chat_id=update.effective_chat.id, text=f"Welcome, {member.full_name}!\nPlease read the group rules.")

# --- Chat handler ---
def handle_message(update, context):
    user = update.effective_user
    user_id = user.id
    chat_id = update.effective_chat.id
    text = update.message.text.lower()

    if admin_only_mode[chat_id] and not is_admin(update):
        update.message.delete()
        return

    if user_id in muted_users and time.time() < muted_users[user_id]:
        update.message.delete()
        return

    for word in BANNED_KEYWORDS + list(custom_filters):
        if word in text:
            try:
                update.message.delete()
                return
            except:
                pass

    if "/chart" in text or "dexscreener" in text:
        message_timestamps[update.message.message_id] = time.time()

# --- Chart cleanup ---
def cleanup_messages(context):
    now = time.time()
    for msg_id in list(message_timestamps):
        if now - message_timestamps[msg_id] > 120:
            try:
                context.bot.delete_message(chat_id=context.job.context, message_id=msg_id)
            except:
                pass
            del message_timestamps[msg_id]

# --- Main ---
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("commands", commands))
    dp.add_handler(CommandHandler("filter", add_filter))
    dp.add_handler(CommandHandler("filters", show_filters))
    dp.add_handler(CommandHandler("removefilter", remove_filter))
    dp.add_handler(CommandHandler("adminmode", toggle_admin_mode))
    dp.add_handler(CommandHandler("mute", mute_user))
    dp.add_handler(CommandHandler("ban", ban_user))
    dp.add_handler(CommandHandler("report", report))
    dp.add_handler(CommandHandler("setchart", set_chart))
    dp.add_handler(CommandHandler("setrules", set_rules))
    dp.add_handler(CommandHandler("rules", show_rules))
    dp.add_handler(MessageHandler(Filters.status_update.new_chat_members, welcome))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

    job_queue = updater.job_queue
    job_queue.run_repeating(cleanup_messages, interval=30, first=30, context=None)

    updater.start_polling()
    print("Tres Guard is running...")
    updater.idle()

if __name__ == "__main__":
    main()
