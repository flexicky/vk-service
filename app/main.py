import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.config import Settings
from app.grpc.server import create_server
from app.infrastructure.database import Database
from app.infrastructure.vk import VkClient
from app.services.tracker import Tracker


class TrackRequest(BaseModel):
    user_id: int = Field(gt=0)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings.database)
        await db.init()
        vk = VkClient(settings.token, settings.api_version, settings.request_timeout)
        server = None
        task = None
        try:
            server = create_server(db, vk, settings.grpc_host, settings.grpc_port)
            await server.start()
            app.state.db = db
            task = asyncio.create_task(Tracker(db, vk, settings.poll_interval).run())
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if server:
                await server.stop(5)
            await vk.close()

    app = FastAPI(title="VK analytics service", lifespan=lifespan)

    @app.get('/health')
    async def health():
        return {'status': 'ok'}

    @app.post('/tracked-users', status_code=201)
    async def add_user(body: TrackRequest):
        await app.state.db.add(body.user_id)
        return {'user_id': body.user_id}

    @app.delete('/tracked-users/{user_id}', status_code=204)
    async def remove_user(user_id: int):
        if user_id <= 0:
            raise HTTPException(422, 'user_id must be positive')
        if not await app.state.db.remove(user_id):
            raise HTTPException(404, 'User is not tracked')

    return app


app = create_app()
