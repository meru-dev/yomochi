from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.application.users.session import Session
from app.domain.value_objects.ids import SessionId, UserId
from app.outbound.auth.jwt import JwtCodec

# 32-byte keys (HS256 RFC 7518 §3.2 minimum)
_KEY_A = "a" * 32
_KEY_B = "b" * 32
_KEY_C = "c" * 32


def _session() -> Session:
    return Session(
        id_=SessionId(uuid4()),
        user_id=UserId(uuid4()),
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
        user_agent="pytest",
        ip="127.0.0.1",
    )


class TestEncodeDecodeRoundTrip:
    def test_round_trip_with_single_key(self) -> None:
        codec = JwtCodec(signing_key=_KEY_A, algorithm="HS256")
        session = _session()

        token = codec.encode(session)
        decoded = codec.decode(token)

        assert decoded is not None
        user_id, session_id = decoded
        assert user_id == session.user_id
        assert session_id == session.id_

    def test_garbage_token_returns_none(self) -> None:
        codec = JwtCodec(signing_key=_KEY_A, algorithm="HS256")
        assert codec.decode("not.a.jwt") is None
        assert codec.decode("") is None


class TestKeyRotation:
    def test_token_signed_with_previous_key_still_decodes(self) -> None:
        old = JwtCodec(signing_key=_KEY_A, algorithm="HS256")
        session = _session()
        token_signed_with_old = old.encode(session)

        # Rotation step 2: KEY_B promoted, KEY_A demoted to verification list
        rotated = JwtCodec(
            signing_key=_KEY_B,
            algorithm="HS256",
            verification_keys=(_KEY_A,),
        )

        decoded = rotated.decode(token_signed_with_old)
        assert decoded is not None
        user_id, _ = decoded
        assert user_id == session.user_id

    def test_new_tokens_sign_with_primary_only(self) -> None:
        rotated = JwtCodec(
            signing_key=_KEY_B,
            algorithm="HS256",
            verification_keys=(_KEY_A,),
        )
        token = rotated.encode(_session())

        # The decoder that only knows KEY_A must reject the new token.
        only_old = JwtCodec(signing_key=_KEY_A, algorithm="HS256")
        assert only_old.decode(token) is None

        # A decoder that knows KEY_B accepts it.
        only_new = JwtCodec(signing_key=_KEY_B, algorithm="HS256")
        assert only_new.decode(token) is not None

    def test_three_key_rotation_window(self) -> None:
        # Mid-rotation: primary B, decode A, B, C
        codec = JwtCodec(
            signing_key=_KEY_B,
            algorithm="HS256",
            verification_keys=(_KEY_A, _KEY_C),
        )

        for key in (_KEY_A, _KEY_B, _KEY_C):
            issuer = JwtCodec(signing_key=key, algorithm="HS256")
            token = issuer.encode(_session())
            assert codec.decode(token) is not None, f"key {key[:1]} not accepted"

    def test_token_signed_with_unknown_key_rejected(self) -> None:
        codec = JwtCodec(
            signing_key=_KEY_A,
            algorithm="HS256",
            verification_keys=(_KEY_B,),
        )
        attacker = JwtCodec(signing_key=_KEY_C, algorithm="HS256")
        forged = attacker.encode(_session())

        assert codec.decode(forged) is None

    def test_after_full_rotation_old_tokens_rejected(self) -> None:
        old_issuer = JwtCodec(signing_key=_KEY_A, algorithm="HS256")
        old_token = old_issuer.encode(_session())

        # Rotation step 3: KEY_A removed from verification list
        post_rotation = JwtCodec(signing_key=_KEY_B, algorithm="HS256")
        assert post_rotation.decode(old_token) is None


class TestEdgeCases:
    def test_duplicate_keys_in_list_deduplicated(self) -> None:
        codec = JwtCodec(
            signing_key=_KEY_A,
            algorithm="HS256",
            verification_keys=(_KEY_A, _KEY_A, _KEY_B),
        )
        # Internal invariant — exposed only via behaviour: still decodes both
        token_a = JwtCodec(signing_key=_KEY_A, algorithm="HS256").encode(_session())
        token_b = JwtCodec(signing_key=_KEY_B, algorithm="HS256").encode(_session())
        assert codec.decode(token_a) is not None
        assert codec.decode(token_b) is not None

    def test_expired_token_not_retried_with_other_keys(self) -> None:
        import jwt as _jwt

        codec = JwtCodec(
            signing_key=_KEY_A,
            algorithm="HS256",
            verification_keys=(_KEY_B,),
        )
        # Manually craft an expired but otherwise valid token signed by KEY_A
        payload = {
            JwtCodec.SESSION_ID_CLAIM: str(uuid4()),
            JwtCodec.USER_ID_CLAIM: str(uuid4()),
            JwtCodec.EXPIRATION_CLAIM: datetime.now(UTC) - timedelta(hours=1),
        }
        expired = _jwt.encode(payload, _KEY_A, algorithm="HS256")

        # Token shape is valid for KEY_A but expired → reject without trying KEY_B
        assert codec.decode(expired) is None

    def test_malformed_uuid_claims_return_none(self) -> None:
        import jwt as _jwt

        payload = {
            JwtCodec.SESSION_ID_CLAIM: "not-a-uuid",
            JwtCodec.USER_ID_CLAIM: str(uuid4()),
            JwtCodec.EXPIRATION_CLAIM: datetime.now(UTC) + timedelta(minutes=5),
        }
        token = _jwt.encode(payload, _KEY_A, algorithm="HS256")

        codec = JwtCodec(signing_key=_KEY_A, algorithm="HS256")
        assert codec.decode(token) is None


class TestSettings:
    def test_jwt_verification_key_list_parses_csv(self) -> None:
        from app.main.config.settings import AuthSettings

        s = AuthSettings(
            jwt_secret=_KEY_A,
            jwt_verification_keys=f"{_KEY_B}, {_KEY_C}",
        )
        assert s.jwt_verification_key_list == (_KEY_B, _KEY_C)

    def test_jwt_verification_key_list_empty_when_unset(self) -> None:
        from app.main.config.settings import AuthSettings

        s = AuthSettings(jwt_secret=_KEY_A)
        assert s.jwt_verification_key_list == ()

    def test_short_verification_key_rejected(self) -> None:
        from app.main.config.settings import AuthSettings

        with pytest.raises(ValueError, match="at least 32 bytes"):
            AuthSettings(jwt_secret=_KEY_A, jwt_verification_keys="too-short")
