from collections.abc import Callable

from app.domain.compliance.models import TermsAcceptance
from app.domain.tenancy.models import Organization
from app.domain.users.exceptions import SocialLoginError
from app.domain.users.models import Role, User
from app.infrastructure.auth.google_oidc import GoogleIdentity
from app.infrastructure.db.unit_of_work import UnitOfWork


class SocialAuthService:
    """Turns a verified Google identity into a logged-in User. Mirrors
    RegistrationService for the new-account case (Organization + Owner Role +
    User + TermsAcceptance in one transaction) but keyed off the provider
    identity instead of a signup form. Session issuance stays with the caller
    (UserService.create_session), exactly like the password login flow."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def login_or_register_google(
        self,
        identity: GoogleIdentity,
        terms_version: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> User:
        if not identity.email:
            raise SocialLoginError("Google didn't provide an email address for this account.")
        if not identity.email_verified:
            # Defense-in-depth: never trust an unverified provider email to map
            # onto (or create) an account.
            raise SocialLoginError("Your Google email address isn't verified, so we can't sign you in.")

        async with self._uow_factory() as uow:
            existing = await uow.users.get_by_email(identity.email)
            if existing is not None:
                # Link-by-verified-email: an existing account (password or
                # social) is logged into and gains the Google identity.
                if not existing.is_active:
                    raise SocialLoginError(
                        "This account has been deactivated. Contact your organization's admin."
                    )
                existing.link_google(identity.sub)
                await uow.commit()
                return existing

            # Brand-new person: provision an account plus their own organization.
            organization = Organization.create(self._derive_org_name(identity))
            await uow.organizations.add(organization)

            role = Role.create(organization.id, "Owner")
            await uow.roles.add(role)

            user = User.create_social(
                organization.id, identity.name or identity.email, identity.email, role.id, identity.sub
            )
            await uow.users.add(user)

            # Consent is captured on the "Continue with Google" screen (which
            # links the Terms); record it atomically like password signup does.
            acceptance = TermsAcceptance.record(
                user.id, organization.id, terms_version, ip_address, user_agent
            )
            await uow.terms_acceptances.add(acceptance)

            await uow.commit()
            return user

    @staticmethod
    def _derive_org_name(identity: GoogleIdentity) -> str:
        """A friendly default org name -- the user renames it later in settings.
        Prefer the given name, fall back to the first token of the full name,
        then the email local-part."""
        base = (identity.given_name or "").strip()
        if not base and identity.name:
            base = identity.name.strip().split()[0]
        if not base and identity.email:
            base = identity.email.split("@")[0]
        return f"{base or 'My'}'s workspace"
