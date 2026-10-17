"""The signed-out login dialog's server-side half: its translated labels and
the archive.org third-party sign-in frame (``shell/login_dialog.html.jinja``)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LoginDialogContext:
    """What ``<ol-login-dialog>`` needs from the server, for a signed-out visitor.

    The labels are built here rather than in the Jinja template for the same
    reason as the search modal's: they reach the browser as JSON and are
    filled client-side, so ``%(email)s`` has to survive the render, and
    Jinja's formatting ``_()`` would raise on it. Keys and English text must
    match ``DEFAULT_LABELS`` in ``OlLoginDialog.js``.
    """

    third_party_src: str = ""
    labels: dict[str, Any] = field(default_factory=dict)


def _third_party_src() -> str:
    """archive.org's frame of third-party sign-in buttons (Google and the
    like), which posts S3 keys back to this origin: the frame the login page
    embeds (account/ia_thirdparty_logins.html), for the dialog."""
    from urllib.parse import urlencode

    import web

    from openlibrary.plugins.upstream.utils import get_ia_host

    origin = (getattr(web.ctx, "home", "") or "").replace("http:", "https:")
    return f"https://{get_ia_host(allow_dev=True)}/account/login.thirdparty.php?{urlencode({'origin': origin})}"


def build_login_dialog_context() -> LoginDialogContext:
    from openlibrary.core.shell._util import _safe
    from openlibrary.i18n import gettext as _

    return LoginDialogContext(
        third_party_src=_safe(_third_party_src, ""),
        labels={
            "heading": _("Log in or sign up"),
            "signupPrompt": _("New to Open Library?"),
            "signup": _("Create a free account"),
            "orLogIn": _("or log in"),
            "email": _("Email"),
            "password": _("Password"),
            "forgotPassword": _("Forgot your password?"),
            "rememberMe": _("Remember me"),
            "logIn": _("Log in"),
            "iaHint": _("Open Library accounts are Internet Archive accounts: log in with that email and password."),
            "useCode": _("Email me a one-time code instead"),
            "usePassword": _("Use a password instead"),
            "otpTitle": _("Get a one-time code"),
            "otpIntro": _("Enter your Internet Archive email and we'll send you a login code."),
            "sendCode": _("Send code"),
            "enterCode": _("Enter your code"),
            "codeSent": _("We sent a 6-digit code to %(email)s."),
            "useOtherEmail": _("Use a different email"),
            "continueOnLoginPage": _("Continue on the login page"),
            "thirdParty": _("Sign in with a third-party account"),
            "errorGeneric": _("Something went wrong. Please try again."),
            "errorNetwork": _("A network error occurred. Please try again."),
            "errorRateLimit": _("Too many attempts. Please wait a moment and try again."),
            "errorCodeSend": _("Unable to send code. Please try again."),
            "close": _("Close dialog"),
            # Read by login-session.js when it swaps the signed-out header controls.
            "myBooks": _("My Books"),
        },
    )
