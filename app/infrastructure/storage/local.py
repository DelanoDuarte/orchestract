import asyncio
from pathlib import Path


class LocalFileStorage:
    """Disk-backed FileStorage. Dev/demo only -- not offered as a production
    choice in the UI; exists so this environment (no real cloud credentials)
    can still exercise the full upload pipeline end-to-end.
    """

    def __init__(self, root: str) -> None:
        self._root = Path(root)

    def _path_for(self, key: str) -> Path:
        path = (self._root / key).resolve()
        if self._root.resolve() not in path.parents and path != self._root.resolve():
            raise ValueError(f"invalid storage key: {key}")
        return path

    async def upload(self, key: str, content: bytes, content_type: str) -> None:
        await asyncio.to_thread(self._write, key, content)

    def _write(self, key: str, content: bytes) -> None:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    async def download(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path_for(key).read_bytes)

    async def get_url(self, key: str, expires_in: int = 3600) -> str:
        return f"/local-storage/{key}"

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path_for(key).unlink, missing_ok=True)
