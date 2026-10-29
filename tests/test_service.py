import grpc
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.grpc import vk_pb2 as pb, vk_pb2_grpc as rpc
from app.grpc.server import Analytics
from app.infrastructure.database import Database
from app.main import create_app
from app.services.tracker import Tracker


class FakeVk:
    async def users(self, ids):
        return [{'id': int(i), 'online': 1, 'first_name': 'Test'} for i in ids]

    async def group(self, identifier):
        return {'id': 5, 'name': 'Group', 'members_count': 42}


@pytest.mark.asyncio
async def test_poll_records_only_changes_and_removal(tmp_path):
    db = Database(str(tmp_path / 'test.db'))
    await db.init()
    await db.add(1)
    await Tracker(db, FakeVk(), 1).poll()
    await Tracker(db, FakeVk(), 1).poll()
    assert len(await db.history(1, 100)) == 1
    assert (await db.list_users())[0]['online'] == 1
    assert await db.remove(1)
    await db.record(1, False)
    assert await db.list_users() == []
    assert await db.history(1, 100) == []


@pytest.mark.asyncio
async def test_grpc_roundtrip(tmp_path):
    db = Database(str(tmp_path / 'test.db'))
    await db.init()
    await db.add(10)
    server = grpc.aio.server()
    rpc.add_VkAnalyticsServicer_to_server(Analytics(db, FakeVk()), server)
    port = server.add_insecure_port('127.0.0.1:0')
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f'127.0.0.1:{port}') as channel:
            client = rpc.VkAnalyticsStub(channel)
            response = await client.ListTrackedUsers(pb.Empty())
            assert response.users[0].id == 10
            assert not response.users[0].HasField('online')
            assert (await client.GetUser(pb.EntityRequest(id='10'))).first_name == 'Test'
            assert (await client.GetGroup(pb.EntityRequest(id='test'))).members_count == 42
            with pytest.raises(grpc.aio.AioRpcError) as exc:
                await client.GetOnlineHistory(pb.HistoryRequest(user_id=-1))
            assert exc.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    finally:
        await server.stop(None)


def test_http_management(tmp_path):
    app = create_app(Settings(database=str(tmp_path / 'test.db'), grpc_host='127.0.0.1', grpc_port=0))
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        assert client.post('/tracked-users', json={'user_id': 123}).status_code == 201
        assert client.post('/tracked-users', json={'user_id': 0}).status_code == 422
        assert client.delete('/tracked-users/123').status_code == 204
        assert client.delete('/tracked-users/123').status_code == 404
