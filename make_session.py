import asyncio
from getpass import getpass

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main():
    print("=== Telegram Session String Generator ===")
    api_id = int(input("API_ID: ").strip())
    api_hash = input("API_HASH: ").strip()
    phone = input("Phone number (example +937XXXXXXXXX): ").strip()

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        await client.send_code_request(phone)
        code = input("Telegram login code: ").strip()
        try:
            await client.sign_in(phone=phone, code=code)
        except Exception as exc:
            # Handles 2-step verification without importing version-specific errors.
            if "password" not in exc.__class__.__name__.lower() and "Password" not in str(exc):
                raise
            password = getpass("2-Step Verification password: ")
            await client.sign_in(password=password)

    me = await client.get_me()
    print(f"\nLogged in as: {me.first_name or ''} @{me.username or '(no username)'}")
    print("\n=== SESSION_STRING ===")
    print(client.session.save())
    print("\nCopy the whole line above into GitHub Secrets as SESSION_STRING.")
    print("NEVER share this string with anyone.")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
