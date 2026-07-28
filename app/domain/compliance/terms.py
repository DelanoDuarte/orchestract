"""The canonical, versioned Terms & Conditions the app requires users to accept.

The long-form text lives in the `terms.html` template; this module holds the
machine-readable metadata (version + effective date) that acceptance records
are pinned to. Bump ``CURRENT_TERMS_VERSION`` whenever the terms materially
change -- every user is then re-prompted to accept the new version on their
next request (see ``enforce_login_and_membership``), and the audit trail keeps
the older acceptances intact.
"""

from datetime import date

# ISO-date version string. Acceptance records store exactly this value, so the
# audit trail always says which revision a user agreed to. Keep it in sync with
# TERMS_EFFECTIVE_DATE and the "Effective" line shown in terms.html.
CURRENT_TERMS_VERSION = "2026-07-28"
TERMS_EFFECTIVE_DATE = date(2026, 7, 28)
