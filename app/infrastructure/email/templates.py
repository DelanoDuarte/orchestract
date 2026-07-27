def _wrapper(heading: str, body_html: str, cta_label: str, cta_link: str) -> str:
    return f"""
<div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px 24px;">
  <h1 style="font-size: 20px; margin-bottom: 16px;">{heading}</h1>
  <p style="font-size: 14px; color: #444; line-height: 1.5;">{body_html}</p>
  <p style="margin: 24px 0;">
    <a href="{cta_link}" style="background: #0d9488; color: #fff; padding: 10px 20px; border-radius: 6px;
       text-decoration: none; font-size: 14px; font-weight: 600;">{cta_label}</a>
  </p>
  <p style="font-size: 12px; color: #888;">If the button doesn't work, copy this link into your browser:<br>{cta_link}</p>
</div>
""".strip()


def verification_email_html(link: str) -> str:
    return _wrapper(
        "Verify your email",
        "Thanks for signing up for Orchestract. Confirm your email address to activate your account.",
        "Verify email",
        link,
    )


def password_reset_email_html(link: str) -> str:
    return _wrapper(
        "Reset your password",
        "We received a request to reset your Orchestract password. This link expires in 1 hour. "
        "If you didn't request this, you can ignore this email.",
        "Reset password",
        link,
    )
