import asyncio
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateUsernameRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest

# --------------------------
# Environment / constants
# --------------------------
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_STRING = os.environ["SESSION_STRING"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])

ROTATE_EVERY_SECONDS = 600  # 10 minutes
STATE_MARKER = "PROFILE_ROTATOR_STATE_V1\n"
MAX_PROFILES = 100
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")

BOT_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"
FILE_BASE = f"https://api.telegram.org/file/bot{BOT_TOKEN}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "profiles": [],
        "index": 0,
        "enabled": True,
        "next_rotation_at": iso(utc_now()),
        "bot_offset": 0,
        "pending_username": None,
        "last_heartbeat_day": "",
    }


def bot_call(method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    r = requests.post(f"{BOT_BASE}/{method}", json=payload or {}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram Bot API error in {method}: {data}")
    return data["result"]


def bot_send(text: str):
    try:
        bot_call("sendMessage", {"chat_id": ADMIN_ID, "text": text})
    except Exception as exc:
        print(f"Bot notify failed: {exc}")


def select_photo_file_id(photo_sizes: list[dict[str, Any]]) -> str | None:
    if not photo_sizes:
        return None
    best = max(photo_sizes, key=lambda x: (x.get("width", 0) * x.get("height", 0), x.get("file_size", 0)))
    return best.get("file_id")


def load_state(client: TelegramClient) -> tuple[dict[str, Any], int | None]:
    async def _load():
        messages = await client.get_messages("me", limit=50)
        for msg in messages:
            if not msg.raw_text or not msg.raw_text.startswith(STATE_MARKER):
                continue
            try:
                state = json.loads(msg.raw_text[len(STATE_MARKER):])
                if not isinstance(state, dict):
                    continue
                return state, msg.id
            except Exception:
                continue
        return default_state(), None

    return asyncio.get_event_loop().run_until_complete(_load()) if False else (None, None)


async def load_state_async(client: TelegramClient) -> tuple[dict[str, Any], int | None]:
    messages = await client.get_messages("me", limit=50)
    for msg in messages:
        if not msg.raw_text or not msg.raw_text.startswith(STATE_MARKER):
            continue
        try:
            state = json.loads(msg.raw_text[len(STATE_MARKER):])
            if isinstance(state, dict):
                return state, msg.id
        except Exception:
            pass
    return default_state(), None


async def save_state(client: TelegramClient, state: dict[str, Any], old_message_id: int | None):
    payload = STATE_MARKER + json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    if len(payload) > 30_000:
        raise RuntimeError("Saved state is too large. Reduce the number of profiles.")

    if old_message_id:
        try:
            await client.edit_message("me", old_message_id, payload)
            return
        except Exception:
            pass

    await client.send_message("me", payload)


def username_from_add_command(text: str) -> str | None:
    parts = text.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None
    return parts[1].strip().lstrip("@")


def find_profile(state: dict[str, Any], username: str) -> int | None:
    for i, p in enumerate(state["profiles"]):
        if p.get("username", "").lower() == username.lower():
            return i
    return None


def upsert_profile(state: dict[str, Any], username: str, file_id: str, unique_id: str | None):
    idx = find_profile(state, username)
    item = {
        "username": username,
        "photo_file_id": file_id,
        "photo_unique_id": unique_id,
        "added_at": iso(utc_now()),
    }

    if idx is None:
        if len(state["profiles"]) >= MAX_PROFILES:
            raise RuntimeError(f"Maximum {MAX_PROFILES} profiles reached.")
        state["profiles"].append(item)
    else:
        state["profiles"][idx] = item


def help_text() -> str:
    return (
        "📋 Profile Rotator\n\n"
        "هر خط فرمان را برای مدیریت پروفایل‌ها بفرست:\n\n"
        "/add USERNAME\n"
        "بعدش عکس همان پروفایل را بفرست.\n\n"
        "یا عکس را با Caption شامل username بفرست.\n\n"
        "/list — لیست پروفایل‌ها\n"
        "/delete 3 — حذف شماره ۳\n"
        "/clear — حذف همه\n"
        "/pause — توقف چرخش\n"
        "/resume — شروع چرخش\n"
        "/status — وضعیت\n"
        "/help — راهنما\n\n"
        "⏱️ فاصله چرخش: ۱۰ دقیقه"
    )


async def process_updates(client: TelegramClient, state: dict[str, Any]) -> bool:
    changed = False
    offset = int(state.get("bot_offset", 0))

    updates = bot_call("getUpdates", {
        "offset": offset,
        "timeout": 1,
        "allowed_updates": ["message"],
    })

    for upd in updates:
        update_id = int(upd["update_id"])
        # Confirm only after handling this update by advancing the saved offset.
        state["bot_offset"] = update_id + 1

        msg = upd.get("message") or {}
        sender = msg.get("from") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")

        if sender.get("id") != ADMIN_ID or chat_id != ADMIN_ID:
            continue

        text = (msg.get("text") or "").strip()
        caption = (msg.get("caption") or "").strip()

        if text == "/start" or text == "/help":
            bot_send(help_text())
            changed = True
            continue

        if text.startswith("/add"):
            username = username_from_add_command(text)
            if not username:
                bot_send("❌ مثال:\n/add Makima_Control_Devil_Queen")
            elif not USERNAME_RE.fullmatch(username):
                bot_send("❌ Username باید ۵ تا ۳۲ کاراکتر باشد و فقط حروف انگلیسی، عدد و _ داشته باشد.")
            else:
                state["pending_username"] = username
                bot_send(f"✅ ثبت شد: @{username}\nحالا عکس این پروفایل را بفرست.")
                changed = True
            continue

        if text == "/list":
            profiles = state["profiles"]
            if not profiles:
                bot_send("📭 هنوز هیچ پروفایلی نداری.")
            else:
                lines = [f"{i+1}. @{p['username']}" for i, p in enumerate(profiles)]
                bot_send("📋 پروفایل‌ها:\n\n" + "\n".join(lines))
            continue

        if text.startswith("/delete"):
            parts = text.split()
            if len(parts) != 2 or not parts[1].isdigit():
                bot_send("❌ مثال: /delete 3")
                continue
            n = int(parts[1])
            profiles = state["profiles"]
            if not 1 <= n <= len(profiles):
                bot_send("❌ شماره وجود ندارد.")
                continue
            deleted = profiles.pop(n - 1)
            state["index"] %= max(1, len(profiles))
            bot_send(f"🗑️ حذف شد: @{deleted['username']}")
            changed = True
            continue

        if text == "/clear":
            state["profiles"] = []
            state["index"] = 0
            state["pending_username"] = None
            bot_send("🗑️ همه پروفایل‌ها حذف شدند.")
            changed = True
            continue

        if text == "/pause":
            state["enabled"] = False
            bot_send("⏸️ چرخش متوقف شد.")
            changed = True
            continue

        if text == "/resume":
            state["enabled"] = True
            state["next_rotation_at"] = iso(utc_now())
            bot_send("▶️ چرخش دوباره فعال شد. اولین تغییر در اجرای بعدی انجام می‌شود.")
            changed = True
            continue

        if text == "/status":
            nxt = state.get("next_rotation_at") or "unknown"
            bot_send(
                "📊 وضعیت\n\n"
                f"پروفایل‌ها: {len(state['profiles'])}\n"
                f"حالت: {'فعال ✅' if state['enabled'] else 'متوقف ⏸️'}\n"
                f"شماره بعدی: {state.get('index', 0)+1}\n"
                f"تغییر بعدی: {nxt}"
            )
            continue

        # Photo sent to the admin bot.
        if msg.get("photo"):
            file_id = select_photo_file_id(msg["photo"])
            unique_id = None
            if msg["photo"]:
                best = max(msg["photo"], key=lambda x: (x.get("width", 0) * x.get("height", 0), x.get("file_size", 0)))
                unique_id = best.get("file_unique_id")

            username = caption.lstrip("@").strip() if caption and not caption.startswith("/") else None
            if not username:
                username = state.get("pending_username")

            if not file_id:
                bot_send("❌ نتوانستم عکس را بخوانم.")
                continue

            if not username:
                bot_send("❌ اول /add USERNAME بفرست، بعد عکس را ارسال کن؛ یا username را در Caption عکس بنویس.")
                continue

            if not USERNAME_RE.fullmatch(username):
                bot_send("❌ Username نامعتبر است. ۵ تا ۳۲ کاراکتر؛ فقط a-z، 0-9 و _")
                continue

            try:
                upsert_profile(state, username, file_id, unique_id)
                state["pending_username"] = None
                bot_send(f"✅ پروفایل آماده شد:\n@{username}\n\nاین عکس همراه این username در چرخش استفاده می‌شود.")
                changed = True
            except Exception as exc:
                bot_send(f"❌ {exc}")
            continue

        if text and text.startswith("/"):
            bot_send("❓ فرمان ناشناخته. /help را بفرست.")

    return changed


async def download_photo(file_id: str) -> bytes:
    info = bot_call("getFile", {"file_id": file_id})
    file_path = info["file_path"]
    r = requests.get(f"{FILE_BASE}/{file_path}", timeout=60)
    r.raise_for_status()
    if len(r.content) > 20 * 1024 * 1024:
        raise RuntimeError("Photo is larger than Telegram Bot API download limit (20 MB).")
    return r.content


async def apply_profile(client: TelegramClient, profile: dict[str, Any]):
    username = profile["username"]
    username_ok = True
    try:
        await client(UpdateUsernameRequest(username))
        print(f"[OK] Username -> @{username}")
    except errors.UsernameNotModifiedError:
        print(f"[OK] Username already @{username}")
    except errors.UsernameOccupiedError:
        username_ok = False
        print(f"[SKIP] @{username} is occupied.")
    except errors.UsernameInvalidError:
        username_ok = False
        print(f"[SKIP] @{username} is invalid.")
    except errors.FloodWaitError as exc:
        raise RuntimeError(f"Telegram username FloodWait: {exc.seconds}s") from exc

    image_bytes = await download_photo(profile["photo_file_id"])
    uploaded = await client.upload_file(image_bytes, file_name="profile.jpg")
    await client(UploadProfilePhotoRequest(file=uploaded))
    print(f"[OK] Photo -> @{username}")
    return username_ok


async def heartbeat(client: TelegramClient, state: dict[str, Any], state_message_id: int | None):
    day = utc_now().date().isoformat()
    if state.get("last_heartbeat_day") == day:
        return state_message_id

    # A small Saved Messages heartbeat is not needed for rotation itself,
    # but repository activity is handled in the workflow. Keep this as a state marker.
    state["last_heartbeat_day"] = day
    return state_message_id


async def main():
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.start()

    me = await client.get_me()
    print(f"Logged in as {me.first_name or ''} @{me.username or '(no username)'}")

    state, state_message_id = await load_state_async(client)

    # Safety normalization for state loaded from Saved Messages.
    state.setdefault("profiles", [])
    state.setdefault("index", 0)
    state.setdefault("enabled", True)
    state.setdefault("next_rotation_at", iso(utc_now()))
    state.setdefault("bot_offset", 0)
    state.setdefault("pending_username", None)
    state.setdefault("last_heartbeat_day", "")

    changed = await process_updates(client, state)
    state_message_id = await heartbeat(client, state, state_message_id)

    if changed:
        # Make new/edited commands persistent before doing the rotation.
        await save_state(client, state, state_message_id)
        # Refresh state message reference after creation fallback.
        _, state_message_id = await load_state_async(client)

    if state["enabled"] and state["profiles"]:
        next_at = parse_iso(state.get("next_rotation_at")) or utc_now()
        now = utc_now()
        if now >= next_at:
            index = int(state.get("index", 0)) % len(state["profiles"])
            profile = state["profiles"][index]
            print(f"Rotating profile #{index+1}: @{profile['username']}")
            try:
                username_ok = await apply_profile(client, profile)
                state["index"] = (index + 1) % len(state["profiles"])
                state["next_rotation_at"] = iso(now + timedelta(seconds=ROTATE_EVERY_SECONDS))
                status = "username + photo" if username_ok else "photo only (username occupied/invalid)"
                bot_send(f"✅ Profile updated\n@{profile['username']}\n{status}\n\nNext rotation: {state['next_rotation_at']}")
            except errors.FloodWaitError as exc:
                state["next_rotation_at"] = iso(now + timedelta(seconds=max(exc.seconds, ROTATE_EVERY_SECONDS)))
                bot_send(f"⏳ Telegram rate limit: {exc.seconds} ثانیه. بعداً دوباره امتحان می‌کنم.")
            except Exception as exc:
                state["next_rotation_at"] = iso(now + timedelta(seconds=ROTATE_EVERY_SECONDS))
                print(f"Rotation error: {exc}")
                bot_send(f"❌ خطا در چرخش @{profile['username']}:\n{exc}")
            changed = True

    await save_state(client, state, state_message_id)
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
