"""Login + 2FA + WebAuthn passkey state machine.

Extracted from ``app.py`` as part of the D2 Blueprint split. Eleven
routes covering the entire authentication surface that still lives
on Flask (the SPA login flow runs through ``/api/v2/auth/*``):

  GET/POST /login                     Generic password login
                                       (cookie-based session). Bounces
                                       owner → /app/owner/dashboard,
                                       admin/employee → /app/dashboard
                                       on success. PWA cookie
                                       (``ds_last_store``) auto-bounces
                                       returning employees to their
                                       store's branded login.
  GET/POST /login/<slug>              Per-store branded login. 301 →
                                       SPA; refreshes the PWA cookie.
  POST     /employee-login            "Enter your store code" escape
                                       hatch on the generic login page.

  GET/POST /login/2fa                 301 → /app/login (TOTP verify
  GET/POST /login/2fa/recover         301 → /app/login   moved to SPA;
  GET/POST /login/2fa/enroll          301 → /app/login   stubs keep
  GET/POST /login/2fa/recovery-codes  301 → /app/login   old links alive)

  POST     /account/passkeys/register/begin    WebAuthn enrollment
  POST     /account/passkeys/register/finish     challenge round-trip
  POST     /login/passkey/begin                 WebAuthn discoverable
  POST     /login/passkey/finish                 sign-in (passkey is
                                                  MFA by construction —
                                                  skips TOTP gate per
                                                  CLAUDE.md #13)

All app.py-resident helpers (state machine predicates, session
juggling, WebAuthn options builders) are pulled via late import
inside route bodies so this blueprint can load before app.py
finishes its module-level init.

Endpoint-name churn (every endpoint moves under ``auth.``):
  url_for("login")                 → url_for("auth.login")
  url_for("login_store")           → url_for("auth.login_store")
  url_for("employee_login_redirect") → url_for("auth.employee_login_redirect")
  url_for("login_totp")            → url_for("auth.login_totp")
  url_for("login_totp_recover")    → url_for("auth.login_totp_recover")
  url_for("login_totp_enroll")     → url_for("auth.login_totp_enroll")
  url_for("login_totp_recovery_codes") → url_for("auth.login_totp_recovery_codes")
  url_for("passkey_register_begin") → url_for("auth.passkey_register_begin")
  url_for("passkey_register_finish") → url_for("auth.passkey_register_finish")
  url_for("passkey_login_begin")   → url_for("auth.passkey_login_begin")
  url_for("passkey_login_finish")  → url_for("auth.passkey_login_finish")

The trial-exempt set (``app._TRIAL_EXEMPT``) doesn't need updating
because none of these routes goes through ``@login_required`` —
they're all session-prerequisite routes.
"""
from __future__ import annotations

import re
from datetime import datetime

from flask import (
    Blueprint, Response, jsonify, make_response, redirect,
    render_template, request, session, url_for,
)


bp = Blueprint("auth", __name__)


# ── Password login state machine ─────────────────────────────────


@bp.route("/login", methods=["GET", "POST"])
def login():
    """Generic password login. Handles password verify, employee
    redirect to the branded store login, TOTP gating, and final
    session promotion."""
    from app import (
        Store, _active_store_from_cookie, _needs_totp, _record_login,
        _set_last_store_slug_cookie, _totp_is_enrolled, current_user, db,
    )
    from api.Modules.Auth.Services import verify_password_cross_store

    if "user_id" in session:
        u = current_user()
        if u and u.role == "owner":
            return redirect(url_for("owner.owner_dashboard"))
        return redirect("/app/dashboard")
    # On a fresh GET from a device that previously signed in to a
    # store, bounce to that store's login so installed-PWA employees
    # aren't stuck on the generic page with the address bar hidden.
    if request.method == "GET":
        store = _active_store_from_cookie()
        if store:
            return redirect(url_for("auth.login_store", slug=store.slug))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        u = verify_password_cross_store(
            db.session, username, request.form.get("password", ""),
        )
        if u is not None:
            if u.role == "employee":
                # Don't authenticate on the generic page, but leave a
                # breadcrumb: persist the slug so their next hit to
                # `/` or `/login` auto-redirects to `/login/<slug>`
                # (helps PWA installs where the address bar is
                # hidden).
                emp_store = (
                    db.session.get(Store, u.store_id)
                    if u.store_id else None
                )
                error = (
                    "Please use your store's sign-in page. Enter your "
                    "store code below."
                )
                resp = make_response(render_template(
                    "login.html", error=error,
                    store_code_value=(
                        emp_store.slug
                        if emp_store and emp_store.is_active else ""
                    ),
                ))
                if emp_store and emp_store.is_active:
                    _set_last_store_slug_cookie(resp, emp_store.slug)
                return resp
            elif _needs_totp(u):
                # Drop any previous partial-auth before starting a
                # new one.
                session.pop("pending_auth_user_id", None)
                session.pop("totp_enrollment_codes", None)
                session["pending_auth_user_id"] = u.id
                if _totp_is_enrolled(u):
                    return redirect(url_for("auth.login_totp"))
                return redirect(url_for("auth.login_totp_enroll"))
            else:
                session["user_id"] = u.id
                session["role"] = u.role
                session["store_id"] = u.store_id
                _record_login(u)
                db.session.commit()
                if u.role == "owner":
                    return redirect(url_for("owner.owner_dashboard"))
                return redirect("/app/dashboard")
        else:
            error = "Invalid username or password."
    return render_template("login.html", error=error)


@bp.route("/login/<slug>", methods=["GET", "POST"])
def login_store(slug: str):
    """301 to the React /app/login/<slug> page. SPA submits directly
    to /api/v2/auth/login (which sets the same `ds_last_store`
    cookie when a store_id is provided).

    We also set the `ds_last_store` cookie on the redirect when the
    slug resolves to an active store, so an installed-PWA employee
    whose session expired keeps getting bounced back to their store
    on the legacy fallback paths (`/`, `/login`)."""
    from app import Store, _set_last_store_slug_cookie

    resp = redirect(f"/app/login/{slug}", code=301)
    store = Store.query.filter_by(slug=slug).first()
    if store is not None and store.is_active:
        _set_last_store_slug_cookie(resp, store.slug)
    return resp


@bp.route("/employee-login", methods=["POST"])
def employee_login_redirect():
    """Escape hatch for an installed-PWA employee who lands on the
    generic /login page (cleared cookies / fresh device). They
    enter their store code and we bounce them to /login/<slug>."""
    from app import Store, _set_last_store_slug_cookie

    raw = (request.form.get("store_code") or "").strip().lower()
    # Accept anything that could be a slug; trim to the allowed
    # charset.
    slug = re.sub(r"[^a-z0-9\-]", "", raw)
    if slug:
        store = Store.query.filter_by(slug=slug).first()
        if store and store.is_active:
            resp = redirect(url_for("auth.login_store", slug=slug))
            return _set_last_store_slug_cookie(resp, slug)
    return render_template(
        "login.html",
        error=(
            "We couldn't find a store with that code. Check with "
            "your manager for the correct code."
        ),
        store_code_value=raw,
    )


# ── 2FA SPA-cutover redirects ────────────────────────────────────


@bp.route("/login/2fa", methods=["GET", "POST"])
def login_totp():
    """301 → /app/login. The legacy Jinja form is retired; the SPA
    drives the verify hop inline from /app/login (it holds the
    pending_token in component state and POSTs to
    /api/v2/auth/login/totp). This stub keeps url_for(...) + old
    bookmarks working — they just bounce to the SPA login, which
    prompts the user to sign in again."""
    return redirect("/app/login", code=301)


@bp.route("/login/2fa/recover", methods=["GET", "POST"])
def login_totp_recover():
    """301 → /app/login. SPA equivalent is /app/login/2fa/recover,
    but reaching it requires the in-flight pending_token (held in
    React Router state). Direct visits here have no pending token,
    so we bounce to /app/login and let the user start fresh."""
    return redirect("/app/login", code=301)


@bp.route("/login/2fa/enroll", methods=["GET", "POST"])
def login_totp_enroll():
    """301 → /app/login. The SPA enrollment page lives at
    /app/login/2fa/enroll, but it needs a pending_token from a
    fresh /api/v2/auth/login response. Direct hits to the legacy
    URL don't carry that state, so we bounce to /app/login."""
    return redirect("/app/login", code=301)


@bp.route("/login/2fa/recovery-codes", methods=["GET", "POST"])
def login_totp_recovery_codes():
    """301 → /app/login. Recovery codes are shown exactly once
    inline on the SPA enrollment page; there is no standalone SPA
    URL for re-displaying them (the codes are not retrievable
    after the enrollment session ends). Direct visits to this
    legacy URL bounce to /app/login."""
    return redirect("/app/login", code=301)


# ── WebAuthn passkey enrollment ──────────────────────────────────


@bp.route("/account/passkeys/register/begin", methods=["POST"])
def passkey_register_begin():
    """Generate a WebAuthn registration challenge. Round-trips
    through the session (single-use — popped on /finish) so the
    browser can't replay a previous attestation."""
    from app import (
        _passkey_eligible, _passkey_exclude_list, _webauthn_rp_id,
        _webauthn_rp_name, current_user, login_required,
    )
    from webauthn import (
        generate_registration_options, options_to_json,
    )
    from webauthn.helpers import bytes_to_base64url
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria, ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    @login_required
    def _h():
        user = current_user()
        if not _passkey_eligible(user):
            return jsonify({
                "ok": False,
                "error": "Passkeys aren't enabled for this account.",
            }), 403
        options = generate_registration_options(
            rp_id=_webauthn_rp_id(),
            rp_name=_webauthn_rp_name(),
            user_id=str(user.id).encode("utf-8"),
            user_name=user.username,
            user_display_name=user.full_name or user.username,
            exclude_credentials=_passkey_exclude_list(user),
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=(
                    UserVerificationRequirement.PREFERRED
                ),
            ),
        )
        # Challenge is single-use — stored base64url-encoded in the
        # session so it survives the round-trip and the finish
        # route can decode it back.
        session["pk_reg_challenge"] = bytes_to_base64url(
            options.challenge,
        )
        return Response(
            options_to_json(options), mimetype="application/json",
        )

    return _h()


@bp.route("/account/passkeys/register/finish", methods=["POST"])
def passkey_register_finish():
    """Verify the attestation, persist the Passkey row."""
    from app import (
        Passkey, _passkey_eligible, _webauthn_origin, _webauthn_rp_id,
        current_user, db, login_required,
    )
    from webauthn import verify_registration_response
    from webauthn.helpers import base64url_to_bytes

    @login_required
    def _h():
        user = current_user()
        if not _passkey_eligible(user):
            return jsonify({
                "ok": False,
                "error": "Passkeys aren't enabled for this account.",
            }), 403
        challenge_b64 = session.pop("pk_reg_challenge", None)
        if not challenge_b64:
            return jsonify({
                "ok": False,
                "error": "No registration in progress. Start again.",
            }), 400
        body = request.get_json(silent=True) or {}
        credential = body.get("credential")
        if not credential:
            return jsonify({
                "ok": False, "error": "Missing credential.",
            }), 400
        name = (body.get("name") or "").strip()[:120] or "Passkey"
        try:
            verification = verify_registration_response(
                credential=credential,
                expected_challenge=base64url_to_bytes(challenge_b64),
                expected_origin=_webauthn_origin(),
                expected_rp_id=_webauthn_rp_id(),
                require_user_verification=False,
            )
        except Exception as e:
            # Normalize the error message — library raises a mix of
            # InvalidRegistrationResponse / InvalidJSONStructure /
            # …; the user just needs to know it didn't work.
            return jsonify({
                "ok": False,
                "error": (
                    f"Passkey could not be verified "
                    f"({type(e).__name__})."
                ),
            }), 400
        db.session.add(Passkey(
            user_id=user.id,
            credential_id=verification.credential_id,
            public_key=verification.credential_public_key,
            sign_count=verification.sign_count,
            name=name,
            aaguid=str(verification.aaguid or ""),
        ))
        db.session.commit()
        return jsonify({"ok": True, "name": name})

    return _h()


# ── WebAuthn passkey login ───────────────────────────────────────


@bp.route("/login/passkey/begin", methods=["POST"])
def passkey_login_begin():
    """Discoverable-credential sign-in. No username needed — the
    browser asks the platform to pick one of the user's stored
    passkeys for this RP ID. The server just generates a challenge
    and lets the authenticator decide which credential to use."""
    from app import _webauthn_rp_id
    from webauthn import (
        generate_authentication_options, options_to_json,
    )
    from webauthn.helpers import bytes_to_base64url
    from webauthn.helpers.structs import UserVerificationRequirement

    options = generate_authentication_options(
        rp_id=_webauthn_rp_id(),
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    session["pk_login_challenge"] = bytes_to_base64url(
        options.challenge,
    )
    return Response(
        options_to_json(options), mimetype="application/json",
    )


@bp.route("/login/passkey/finish", methods=["POST"])
def passkey_login_finish():
    """Verify the assertion, promote the session to full auth.

    Passkey IS MFA per CLAUDE.md invariant #13 — skip the TOTP
    gate even when _needs_totp(user) would normally be True."""
    from app import (
        Passkey, User, _record_login, _webauthn_origin,
        _webauthn_rp_id, db,
    )
    from webauthn import verify_authentication_response
    from webauthn.helpers import base64url_to_bytes

    challenge_b64 = session.pop("pk_login_challenge", None)
    if not challenge_b64:
        return jsonify({
            "ok": False,
            "error": "No sign-in challenge in progress.",
        }), 400
    body = request.get_json(silent=True) or {}
    credential = body.get("credential")
    if not credential:
        return jsonify({
            "ok": False, "error": "Missing credential.",
        }), 400
    raw_cred_id_b64 = credential.get("rawId") or credential.get("id")
    if not raw_cred_id_b64:
        return jsonify({
            "ok": False, "error": "Invalid credential.",
        }), 400
    try:
        cred_bytes = base64url_to_bytes(raw_cred_id_b64)
    except Exception:
        return jsonify({
            "ok": False, "error": "Invalid credential.",
        }), 400
    pk = Passkey.query.filter_by(credential_id=cred_bytes).first()
    if not pk:
        return jsonify({
            "ok": False, "error": "Passkey not recognized.",
        }), 400
    user = db.session.get(User, pk.user_id)
    if not user or not user.is_active:
        return jsonify({
            "ok": False, "error": "Account unavailable.",
        }), 403
    try:
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge_b64),
            expected_origin=_webauthn_origin(),
            expected_rp_id=_webauthn_rp_id(),
            credential_public_key=pk.public_key,
            credential_current_sign_count=pk.sign_count,
            require_user_verification=False,
        )
    except Exception:
        return jsonify({
            "ok": False, "error": "Passkey verification failed.",
        }), 400
    pk.sign_count = verification.new_sign_count
    pk.last_used_at = datetime.utcnow()
    _record_login(user)
    # Passkey IS MFA — skip the TOTP gate per the carve-out in
    # CLAUDE.md invariant #13. Clear any stale pending-auth too.
    session.pop("pending_auth_user_id", None)
    session.pop("totp_enrollment_codes", None)
    session["user_id"] = user.id
    session["role"] = user.role
    session["store_id"] = user.store_id
    db.session.commit()
    redirect_url = (
        url_for("owner.owner_dashboard")
        if user.role == "owner"
        else "/app/dashboard"
    )
    return jsonify({"ok": True, "redirect": redirect_url})
