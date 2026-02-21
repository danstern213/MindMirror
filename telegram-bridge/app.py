"""
Telegram Bridge for AI Note Copilot
Receives Telegram messages and forwards to chat API with SSE handling.
No Twilio needed — uses Telegram Bot API directly (free).
"""
import json
import os
import threading
import requests
from flask import Flask, request, Response

app = Flask(__name__)

# Configuration from environment variables
API_URL = os.environ.get('CHAT_API_URL', 'https://mindmirror-production.up.railway.app/api/v1')
API_KEY = os.environ.get('API_KEY')        # Long-lived API key (ak_...)
USER_ID = os.environ.get('USER_ID')        # Your Supabase user UUID

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_SECRET = os.environ.get('TELEGRAM_WEBHOOK_SECRET')
APP_URL = os.environ.get('APP_URL')        # Your Railway public URL, e.g. https://xxx.up.railway.app


def register_webhook():
    """Register this service's webhook URL with Telegram on startup."""
    if not BOT_TOKEN or not APP_URL:
        print("WARNING: BOT_TOKEN or APP_URL not set — skipping webhook registration")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    payload = {
        "url": f"{APP_URL}/webhook/telegram",
        "secret_token": WEBHOOK_SECRET,
        "drop_pending_updates": True,
    }
    resp = requests.post(url, json=payload)
    print(f"Webhook registration: {resp.json()}")


def send_telegram_message(chat_id, text):
    """Send a message back to the user via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})


def accumulate_sse_response(url, headers, data, timeout=60):
    """
    POST to the SSE endpoint and accumulate the full streamed response.
    Returns the complete content string.
    """
    try:
        response = requests.post(
            url,
            headers=headers,
            json=data,
            stream=True,
            timeout=timeout
        )

        if response.status_code == 401:
            return "Authentication failed. Please contact admin."
        elif response.status_code != 200:
            return f"API error (status {response.status_code}). Please try again."

        full_content = ""
        for line in response.iter_lines():
            if not line:
                continue
            line = line.decode('utf-8')
            if line.startswith('data: '):
                data_str = line[6:]
                if data_str == '[DONE]':
                    break
                try:
                    chunk = json.loads(data_str)
                    if chunk.get('content'):
                        full_content += chunk['content']
                except json.JSONDecodeError:
                    continue

        return full_content if full_content else "Received response but no content was generated."

    except requests.exceptions.Timeout:
        return "Request timed out. The AI is taking longer than expected. Please try a simpler query."
    except requests.exceptions.RequestException as e:
        return f"Connection error: {str(e)}"


def split_message(text, max_length=4000):
    """
    Split a long message into chunks, breaking at paragraph/sentence/word boundaries.
    Telegram allows 4096 chars (vs WhatsApp's 1600), so splitting is rarely needed.
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        chunk = remaining[:max_length]

        # Prefer paragraph break
        break_point = chunk.rfind('\n\n')
        if break_point < max_length // 2:
            # Try sentence break
            for ending in ['. ', '! ', '? ', '.\n', '!\n', '?\n']:
                pos = chunk.rfind(ending)
                if pos > max_length // 2:
                    break_point = pos + len(ending) - 1
                    break
            else:
                # Word break
                break_point = chunk.rfind(' ')
                if break_point < max_length // 2:
                    break_point = max_length

        chunks.append(remaining[:break_point + 1].strip())
        remaining = remaining[break_point + 1:].strip()

    return chunks


def process_and_respond(chat_id, user_message):
    """
    Background task: call chat API and send response back via Telegram.
    Uses chat_id as thread_id so conversation history persists.
    """
    try:
        chat_url = f"{API_URL}/chat/message"
        headers = {
            'X-API-Key': API_KEY,
            'Content-Type': 'application/json'
        }
        data = {
            'message': user_message,
            'user_id': USER_ID,
        }

        response_content = accumulate_sse_response(chat_url, headers, data)

        chunks = split_message(response_content)
        for i, chunk in enumerate(chunks):
            if len(chunks) > 1:
                chunk = f"({i+1}/{len(chunks)}) {chunk}"
            send_telegram_message(chat_id, chunk)

        print(f"Sent response to chat {chat_id}: {response_content[:80]}...")

    except Exception as e:
        print(f"Error processing message: {e}")
        try:
            send_telegram_message(chat_id, "Sorry, there was an error processing your message. Please try again.")
        except Exception as send_error:
            print(f"Failed to send error message: {send_error}")


@app.route('/webhook/telegram', methods=['POST'])
def telegram_webhook():
    """
    Telegram webhook endpoint.
    Verifies the secret token, extracts message, returns 200 immediately,
    and processes the AI response in a background thread.
    """
    # Verify Telegram's secret token header
    incoming_secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token', '')
    if WEBHOOK_SECRET and incoming_secret != WEBHOOK_SECRET:
        return Response(status=403)

    update = request.get_json(silent=True) or {}
    message = update.get('message', {})
    text = message.get('text', '').strip()
    chat_id = message.get('chat', {}).get('id')

    print(f"Received from chat {chat_id}: {text}")

    if not text or not chat_id:
        return Response(status=200)

    if not API_KEY or not USER_ID:
        print("ERROR: API_KEY or USER_ID not configured")
        return Response(status=200)

    # Process in background — return 200 immediately so Telegram doesn't retry
    thread = threading.Thread(target=process_and_respond, args=(chat_id, text))
    thread.start()

    return Response(status=200)


@app.route('/health', methods=['GET'])
def health():
    return {
        'status': 'healthy',
        'api_url': API_URL,
        'configured': bool(API_KEY and USER_ID and BOT_TOKEN),
    }


@app.route('/', methods=['GET'])
def index():
    return """
    <html>
        <body>
            <h1>Telegram Bridge for AI Note Copilot</h1>
            <p>Status: Running</p>
            <p>Webhook URL: <code>/webhook/telegram</code></p>
            <p><a href="/health">Health Check</a></p>
        </body>
    </html>
    """


# Register webhook with Telegram when the app starts
register_webhook()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
