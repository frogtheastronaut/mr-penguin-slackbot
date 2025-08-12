#!/usr/bin/env python3

import os
import re
import logging
import json
import random
import threading
import traceback
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from datetime import datetime
from dotenv import load_dotenv # type: ignore
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Build path to .env in the same folder
dotenv_path = os.path.join(BASE_DIR, '.env')

# Load it
load_dotenv(dotenv_path)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize the Slack app with bot token and socket mode
app = App(
    token=os.environ.get("SLACK_BOT_TOKEN"),
)

# Bot configuration
BOT_NAME = "mr-penguin"
WELCOME_CHANNEL = "penguin-playground"  # Channel where welcome messages are sent
TRIVIA_FILE = "questions.json"
LEADERBOARD_FILE = "leaderboard.json"

# Trivia game state
trivia_questions = []
current_trivia = {
    "question": None,
    "answer": None,
    "timer": None,
    "channel": None
}

def load_trivia_questions():
    """Load trivia questions from the JSON file"""
    global trivia_questions
    try:
        with open(TRIVIA_FILE, "r") as f:
            data = json.load(f)
            if isinstance(data, dict) and "results" in data:
                trivia_questions = data["results"]
            else:
                trivia_questions = data
    except Exception as e:
        logger.error(f"Could not load trivia questions: {e}")

def ask_trivia_question(channel, client):
    """Ask a random trivia question in the given channel"""
    global current_trivia
    if not trivia_questions:
        load_trivia_questions()
    q = random.choice(trivia_questions)
    current_trivia["question"] = q.get("question")
    current_trivia["type"] = q.get("type", "multiple")
    current_trivia["channel"] = channel
    answer = q.get("answer") or q.get("correct_answer")
    current_trivia["answer"] = answer.strip().lower() if answer else None
    # Cancel any previous timer
    if current_trivia.get("timer"):
        current_trivia["timer"].cancel()
    # Start a new timer for 30 minutes
    timer = threading.Timer(1800, trivia_timeout, args=(channel, client))
    current_trivia["timer"] = timer
    timer.start()
    # Format question based on type
    if current_trivia["type"] == "boolean":
        question_text = f"Trivia Time!\n(True/False) {q['question']}\n(Reply with @mr-penguin true or false to win!)"
    elif current_trivia["type"] == "multiple":
        # Dynamically create possible_answers if missing
        if "possible_answers" in q:
            choices = q["possible_answers"][:]
        else:
            choices = q.get("incorrect_answers", []) + [answer]
        random.shuffle(choices)
        choice_labels = ['a', 'b', 'c', 'd']
        current_trivia["choices"] = {label: choice for label, choice in zip(choice_labels, choices)}
        for label, choice in current_trivia["choices"].items():
            if choice.strip().lower() == current_trivia["answer"]:
                current_trivia["correct_label"] = label
                break
        choices_text = '\n'.join([f"{label}) {choice}" for label, choice in current_trivia["choices"].items()])
        question_text = f"Trivia Time!\n{q['question']}\nChoices:\n{choices_text}\n(Reply with @mr-penguin a, b, c, or d to win! Alternatively, you can type the answer.)"
    else:
        question_text = f"Trivia Time!\n{q['question']}\n(Reply with @mr-penguin <your answer> to win!)"
    client.chat_postMessage(
        channel=channel,
        text=question_text,
        username=BOT_NAME
    )

def trivia_timeout(channel, client):
    """Handle trivia question timeout"""
    global current_trivia
    client.chat_postMessage(
        channel=channel,
        text=f"No one answered the last trivia question. Let's try another!",
        username=BOT_NAME
    )
    ask_trivia_question(channel, client)

def update_leaderboard(user_id, user_name):
    try:
        # Load leaderboard
        try:
            with open(LEADERBOARD_FILE, "r") as f:
                leaderboard = json.load(f)
        except Exception:
            leaderboard = {}
        # Update score
        if user_id in leaderboard:
            leaderboard[user_id]["score"] += 1
        else:
            leaderboard[user_id] = {"name": user_name, "score": 1}
        # Save leaderboard
        with open(LEADERBOARD_FILE, "w") as f:
            json.dump(leaderboard, f, indent=2)
        return leaderboard[user_id]["score"]  # Return updated score
    except Exception as e:
        logger.error(f"Error updating leaderboard: {e}")
        return None

def get_leaderboard():
    try:
        with open(LEADERBOARD_FILE, "r") as f:
            leaderboard = json.load(f)
        # Sort by score descending
        sorted_leaderboard = sorted(leaderboard.items(), key=lambda x: x[1]["score"], reverse=True)
        msg = "🏆 *Trivia Leaderboard* 🏆\n"
        for idx, (user_id, entry) in enumerate(sorted_leaderboard[:3], 1):
            msg += f"{idx}. <@{user_id}>: {entry['score']}\n"
        return msg
    except Exception:
        return "No leaderboard data yet. Answer trivia to get on the board!"

def check_trivia_answer(text, user, client, channel):
    global current_trivia
    if current_trivia["question"] and current_trivia["answer"]:
        # Remove all Slack mentions and extra spaces
        answer_attempt = re.sub(r'<@[^>]+>', '', text)
        answer_attempt = answer_attempt.strip().lower()
        if current_trivia.get("type") == "multiple" and answer_attempt in ['a', 'b', 'c', 'd']:
            if answer_attempt == current_trivia.get("correct_label"):
                update_leaderboard(user, user)
                winner_msg = f"🎉 Congratulations <@{user}>! You answered correctly: {current_trivia['choices'][answer_attempt]}\nNext question coming up...\n{get_leaderboard()}"
                client.chat_postMessage(
                    channel=channel,
                    text=winner_msg,
                    username=BOT_NAME
                )
                # Cancel timer
                if current_trivia["timer"]:
                    current_trivia["timer"].cancel()
                ask_trivia_question(channel, client)
                return True
            else:
                client.chat_postMessage(
                    channel=channel,
                    text=f"Sorry, {answer_attempt} is not correct.",
                    username=BOT_NAME
                )
                return False
        elif answer_attempt == current_trivia["answer"]:
            update_leaderboard(user, user)
            winner_msg = f"🎉 Congratulations <@{user}>! You answered correctly: {current_trivia['answer']}\nNext question coming up...\n{get_leaderboard()}"
            client.chat_postMessage(
                channel=channel,
                text=winner_msg,
                username=BOT_NAME
            )
            # Cancel timer
            if current_trivia["timer"]:
                current_trivia["timer"].cancel()
            ask_trivia_question(channel, client)
            return True
        else:
            client.chat_postMessage(
                channel=channel,
                text=f"I don't know what you said, but {answer_attempt} is not correct.",
                username=BOT_NAME
            )
    return False

def process_command(command, user_id, client, channel=None):
    command = re.sub(r'<@[^>]+>', '', command)
    command = command.strip().lower()
    try:
        user_info = client.users_info(user=user_id)
        user_name = user_info["user"]["real_name"] or user_info["user"]["name"]
    except:
        user_name = "friend"
    if not command:
        return get_help_message()
    if command == "trivia!":
        ask_trivia_question(channel, client)
        return ""
    elif command == "leaderboard!":
        return get_leaderboard()
    elif command == "help!":
        return get_help_message()
    elif command == "hello!" or command == "hi!":
        return f"Hello there, {user_name}. Today, I'm sponsored by NordVPN!"
    else:
        return ""

def get_help_message():
    """Return help message with available commands"""
    return f"""
Don't know how to use this bot? Well, should've installed NORDVPN!!
@{BOT_NAME} [answer] to answer a question
@{BOT_NAME} trivia! to start a trivia question
@{BOT_NAME} help! to see this message
@{BOT_NAME} hello! or hi! to greet the bot
Not working? Don't forget the exclamation mark!
Most importantly, don't forget our sponsor, NORDVPN!!!
    """

@app.event("app_mention")
def handle_mention(event, client, logger):
    try:
        channel = event["channel"]
        user = event["user"]
        text = event["text"].lower()
        mention_pattern = r'<@[A-Z0-9]+>'
        command = re.sub(mention_pattern, '', text).strip()
        # Check for trivia answer first
        if check_trivia_answer(text, user, client, channel):
            return
        response = process_command(command, user, client, channel)
        if response:
            client.chat_postMessage(
                channel=channel,
                text=response,
                username=BOT_NAME
            )
    except Exception as e:
        logger.error(f"Error handling mention: {e}")
        logger.error(traceback.format_exc())

def main():
    """Main function to start the bot"""
    load_trivia_questions()
    try:
        logger.info(f"Starting {BOT_NAME}...")
        
        # Check if required environment variables are set
        if not os.environ.get("SLACK_BOT_TOKEN"):
            logger.error("SLACK_BOT_TOKEN environment variable is required!")
            return
            
        if not os.environ.get("SLACK_APP_TOKEN"):
            logger.error("SLACK_APP_TOKEN environment variable is required for Socket Mode!")
            return
        
        # Start the bot using Socket Mode
        handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
        
        logger.info(f"{BOT_NAME} is now running! 🐧")
        handler.start()
        
    except Exception as e:
        logger.error(f"Error starting bot: {e}")

if __name__ == "__main__":
    main()
