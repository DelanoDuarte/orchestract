from datetime import timedelta

from app.domain.shared.types import utcnow
from app.domain.users.models import User, UserToken, UserTokenPurpose


def test_user_starts_unverified_and_can_be_marked_verified():
    user = User.create(1, "Dana", "dana@example.com", "password123", role_id=1)
    assert not user.is_email_verified
    assert user.email_verified_at is None

    user.mark_email_verified()

    assert user.is_email_verified
    assert user.email_verified_at is not None


def test_user_token_issue_is_valid_until_expiry():
    token = UserToken.issue(user_id=1, purpose=UserTokenPurpose.EMAIL_VERIFICATION)
    assert token.is_valid()

    token.expires_at = utcnow() - timedelta(seconds=1)
    assert not token.is_valid()


def test_user_token_purposes_get_different_ttls():
    verification = UserToken.issue(1, UserTokenPurpose.EMAIL_VERIFICATION)
    reset = UserToken.issue(1, UserTokenPurpose.PASSWORD_RESET)
    assert verification.expires_at > reset.expires_at
