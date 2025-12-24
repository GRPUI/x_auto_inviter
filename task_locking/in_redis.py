import asyncio
import uuid
from typing import Optional
from contextvars import ContextVar
from redis.asyncio import Redis

_redis_client: ContextVar[Optional[Redis]] = ContextVar("redis_client", default=None)


class DistributedLock:
    """
    Распределенная блокировка с поддержкой skip-if-locked режима
    """

    def __init__(
        self,
        key: str,
        ttl: int = 30,
        retry_delay: float = 0.1,
        retry_times: Optional[int] = None,
        auto_extend: bool = False,
        skip_if_locked: bool = False,  # Новый параметр!
    ):
        self.key = f"lock:{key}"
        self.ttl = ttl
        self.retry_delay = retry_delay
        self.retry_times = retry_times
        self.auto_extend = auto_extend
        self.skip_if_locked = skip_if_locked  # Режим "пропустить если занято"
        self.token: Optional[str] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._acquired = False  # Флаг успешного захвата

        self._release_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """

        self._extend_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """

    @property
    def redis(self) -> Redis:
        client = _redis_client.get()
        if client is None:
            raise RuntimeError(
                "Redis client not initialized. "
                "Call DistributedLock.init_redis() in lifespan."
            )
        return client

    @classmethod
    async def init_redis(
        cls,
        redis_url: str = "redis://localhost:6379",
        max_connections: int = 50,
        **kwargs,
    ) -> Redis:
        redis_client = Redis.from_url(
            redis_url,
            decode_responses=True,
            max_connections=max_connections,
            socket_keepalive=True,
            socket_connect_timeout=5,
            retry_on_timeout=True,
            **kwargs,
        )

        try:
            await redis_client.ping()
        except Exception as e:
            await redis_client.close()
            raise ConnectionError(f"Failed to connect to Redis at {redis_url}: {e}")

        _redis_client.set(redis_client)
        return redis_client

    @classmethod
    async def close_redis(cls):
        client = _redis_client.get()
        if client is not None:
            await client.close()
            _redis_client.set(None)

    async def acquire(self, blocking: bool = True) -> bool:
        """Захватить блокировку"""
        self.token = str(uuid.uuid4())
        attempts = 0

        while True:
            acquired = await self.redis.set(self.key, self.token, nx=True, ex=self.ttl)

            if acquired:
                self._acquired = True
                if self.auto_extend:
                    self._start_heartbeat()
                return True

            if not blocking:
                return False

            attempts += 1
            if self.retry_times is not None and attempts >= self.retry_times:
                return False

            await asyncio.sleep(self.retry_delay)

    async def release(self) -> bool:
        """Освободить блокировку"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if not self.token:
            return False

        result = await self.redis.eval(self._release_script, 1, self.key, self.token)

        released = bool(result)
        self.token = None
        self._acquired = False
        return released

    async def extend(self, additional_time: Optional[int] = None) -> bool:
        if not self.token:
            return False

        extend_time = additional_time or self.ttl
        result = await self.redis.eval(
            self._extend_script, 1, self.key, self.token, extend_time
        )

        return bool(result)

    async def is_locked(self) -> bool:
        return await self.redis.exists(self.key) > 0

    async def is_owned(self) -> bool:
        if not self.token:
            return False
        current_token = await self.redis.get(self.key)
        return current_token == self.token

    def _start_heartbeat(self):
        async def heartbeat():
            try:
                while True:
                    await asyncio.sleep(self.ttl / 3)
                    if not await self.extend():
                        break
            except asyncio.CancelledError:
                pass

        self._heartbeat_task = asyncio.create_task(heartbeat())

    async def __aenter__(self):
        """
        Context manager entry с поддержкой skip_if_locked режима
        """
        # В skip_if_locked режиме пытаемся захватить без ожидания
        blocking = not self.skip_if_locked
        acquired = await self.acquire(blocking=blocking)

        if not acquired and self.skip_if_locked:
            # Блокировка занята, но мы в skip режиме - просто возвращаем self
            # _acquired = False указывает, что блокировка не захвачена
            return self

        if not acquired:
            # Обычный режим - не смогли захватить
            raise RuntimeError(f"Failed to acquire lock: {self.key}")

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        # Освобождаем только если захватывали
        if self._acquired:
            await self.release()
        return False

    @property
    def acquired(self) -> bool:
        """Проверить, была ли блокировка успешно захвачена"""
        return self._acquired
