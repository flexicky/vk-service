import grpc
from app.grpc import vk_pb2 as pb, vk_pb2_grpc as rpc
from app.infrastructure.vk import VkError


class Analytics(rpc.VkAnalyticsServicer):
    def __init__(self, db, vk):
        self.db, self.vk = db, vk

    async def GetUser(self, request, context):
        if not request.id.strip():
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "id is required")
        try:
            users = await self.vk.users([request.id])
            if not users:
                await context.abort(grpc.StatusCode.NOT_FOUND, "User not found")
            u = users[0]
            return pb.UserResponse(id=u['id'], first_name=u.get('first_name', ''), last_name=u.get('last_name', ''), online=bool(u.get('online', 0)), followers_count=u.get('followers_count', 0))
        except VkError as exc:
            await context.abort(grpc.StatusCode.UNAVAILABLE, str(exc))

    async def GetGroup(self, request, context):
        if not request.id.strip():
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "id is required")
        try:
            g = await self.vk.group(request.id)
            return pb.GroupResponse(id=g['id'], name=g.get('name', ''), screen_name=g.get('screen_name', ''), members_count=g.get('members_count', 0), description=g.get('description', ''))
        except VkError as exc:
            await context.abort(grpc.StatusCode.UNAVAILABLE, str(exc))

    async def ListTrackedUsers(self, request, context):
        users = []
        for row in await self.db.list_users():
            item = pb.TrackedUser(id=row['id'])
            if row['online'] is not None:
                item.online = bool(row['online'])
            if row['checked_at'] is not None:
                item.checked_at = row['checked_at']
            users.append(item)
        return pb.TrackedUsersResponse(users=users)

    async def GetOnlineHistory(self, request, context):
        if request.user_id <= 0 or request.limit < 0 or request.limit > 1000:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id must be positive and limit must be between 0 and 1000")
        rows = await self.db.history(request.user_id, request.limit or 100)
        return pb.HistoryResponse(events=[pb.OnlineEvent(user_id=r['user_id'], online=bool(r['online']), observed_at=r['observed_at']) for r in rows])


def create_server(db, vk, host, port):
    server = grpc.aio.server()
    rpc.add_VkAnalyticsServicer_to_server(Analytics(db, vk), server)
    if not server.add_insecure_port(f"{host}:{port}"):
        raise RuntimeError("Unable to bind gRPC port")
    return server
