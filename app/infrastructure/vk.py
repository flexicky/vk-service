import httpx


class VkError(Exception):
    pass


class VkClient:
    def __init__(self, token: str, version: str, timeout: float):
        self.token, self.version = token, version
        self.client = httpx.AsyncClient(base_url="https://api.vk.com/method/", timeout=timeout)

    async def close(self):
        await self.client.aclose()

    async def call(self, method: str, **params):
        if not self.token:
            raise VkError("VK access token is not configured")
        try:
            response = await self.client.post(method, data={**params, "access_token": self.token, "v": self.version})
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise VkError("VK API request failed") from exc
        if "error" in data:
            error = data['error']
            raise VkError(f"VK API error {error.get('error_code')}: {error.get('error_msg', 'unknown error')}")
        if "response" not in data:
            raise VkError("Invalid VK API response")
        return data['response']

    async def users(self, ids: list[str]):
        result = await self.call("users.get", user_ids=','.join(ids), fields="online,followers_count")
        if not isinstance(result, list):
            raise VkError("Invalid VK users response")
        return result

    async def group(self, identifier: str):
        result = await self.call("groups.getById", group_id=identifier, fields="members_count,description")
        groups = result.get('groups', []) if isinstance(result, dict) else result
        if not groups:
            raise VkError("VK group not found")
        return groups[0]
