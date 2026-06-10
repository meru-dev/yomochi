import json
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis

from app.application.users.session import Session
from app.domain.value_objects.ids import SessionId, UserId

_SESSION_KEY = "session:{sid}"
_USER_SESSIONS_KEY = "sessions:{uid}"


class RedisSessionStore:
    def __init__(self, redis: Redis) -> None:  # type: ignore[type-arg]
        self._redis = redis

    async def save(self, session: Session) -> None:
        data = json.dumps(
            {
                "id_": str(session.id_),
                "user_id": str(session.user_id),
                "expires_at": session.expires_at.isoformat(),
                "user_agent": session.user_agent,
                "ip": session.ip,
            }
        )
        score = session.expires_at.timestamp()
        sid = str(session.id_)
        uid = str(session.user_id)
        async with self._redis.pipeline() as pipe:
            pipe.set(_SESSION_KEY.format(sid=sid), data)
            pipe.zadd(_USER_SESSIONS_KEY.format(uid=uid), {sid: score})
            await pipe.execute()

    async def get(self, session_id: SessionId, user_id: UserId) -> Session | None:
        raw = await self._redis.get(_SESSION_KEY.format(sid=str(session_id)))
        if raw is None:
            return None
        return _deserialize(json.loads(raw))

    async def revoke(self, session_id: SessionId, user_id: UserId) -> None:
        sid = str(session_id)
        uid = str(user_id)
        async with self._redis.pipeline() as pipe:
            pipe.delete(_SESSION_KEY.format(sid=sid))
            pipe.zrem(_USER_SESSIONS_KEY.format(uid=uid), sid)
            await pipe.execute()

    async def list_active(self, user_id: UserId) -> Sequence[Session]:
        now = datetime.now(UTC).timestamp()
        sids: list[bytes] = await self._redis.zrangebyscore(
            _USER_SESSIONS_KEY.format(uid=str(user_id)), min=now, max="+inf"
        )
        sessions: list[Session] = []
        for sid_bytes in sids:
            sid = sid_bytes.decode()
            raw = await self._redis.get(_SESSION_KEY.format(sid=sid))
            if raw is not None:
                sessions.append(_deserialize(json.loads(raw)))
        return sessions

    async def revoke_all(self, user_id: UserId) -> None:
        key = _USER_SESSIONS_KEY.format(uid=str(user_id))
        sids: list[bytes] = await self._redis.zrange(key, 0, -1)
        if not sids:
            return
        async with self._redis.pipeline() as pipe:
            for sid_bytes in sids:
                pipe.delete(_SESSION_KEY.format(sid=sid_bytes.decode()))
            pipe.delete(key)
            await pipe.execute()


def _deserialize(data: dict[str, str]) -> Session:
    return Session(
        id_=SessionId(UUID(data["id_"])),
        user_id=UserId(UUID(data["user_id"])),
        expires_at=datetime.fromisoformat(data["expires_at"]),
        user_agent=data["user_agent"],
        ip=data["ip"],
    )
