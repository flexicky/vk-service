import asyncio
import logging

logger = logging.getLogger(__name__)


class Tracker:
    def __init__(self, db, vk, interval):
        self.db, self.vk, self.interval = db, vk, interval

    async def poll(self):
        users = await self.db.list_users()
        # VK users.get accepts up to 1000 IDs per request.
        for offset in range(0, len(users), 1000):
            batch = users[offset:offset + 1000]
            try:
                profiles = await self.vk.users([str(user['id']) for user in batch])
                requested_ids = {user['id'] for user in batch}
                for profile in profiles:
                    # Deactivated or inaccessible profiles are not evidence of being offline.
                    if profile.get('id') in requested_ids and 'online' in profile and not profile.get('deactivated'):
                        await self.db.record(profile['id'], bool(profile['online']))
            except Exception:
                logger.exception("Online polling failed for a batch")

    async def run(self):
        while True:
            try:
                await self.poll()
            except Exception:
                logger.exception("Online polling failed")
            await asyncio.sleep(self.interval)
