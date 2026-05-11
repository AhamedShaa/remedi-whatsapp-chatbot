"""Create the initial admin user in MongoDB.

Usage:
    python scripts/create_admin.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from database.mongodb import MongoDB

_EMAIL = "admin@remedi.lk"
_PASSWORD = "Admin@Remedi2025!"
_NAME = "System Admin"


async def main() -> None:
    db = MongoDB()
    await db.connect()

    try:
        existing = await db.get_user_by_email(_EMAIL)
        if existing:
            print(f"Admin already exists: {existing['user_id']}")
            return

        user_id = await db.create_admin_user(_EMAIL, _PASSWORD, _NAME)
        print(f"Admin created successfully: {user_id}")

    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
