// WebAuthn browser helpers for the time-clock passkey flow.
// Two helpers: one to take a server-generated registration
// options blob through ``navigator.credentials.create()``, and
// one for ``navigator.credentials.get()`` on the punch path.
//
// Both translate the server's base64url-encoded byte fields back
// to ``Uint8Array`` (the browser API requires that shape) and
// then return the resulting credential as a plain JSON object
// with base64url-encoded bytes for transit back to the server.

function _b64urlToBytes(s: string): Uint8Array {
  const padded = s + "=".repeat((4 - (s.length % 4)) % 4);
  const b64 = padded.replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function _bytesToB64Url(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}


/** True when the browser exposes WebAuthn + a platform
 *  authenticator (Touch ID / Face ID / Windows Hello / hardware
 *  key). Surfaces a friendly fallback on browsers that don't. */
export function passkeysSupported(): boolean {
  return typeof window !== "undefined"
    && typeof window.PublicKeyCredential !== "undefined";
}


/** Run a server-issued registration options blob through
 *  ``navigator.credentials.create()`` and return the result
 *  as a plain JSON object the server can verify (bytes
 *  re-encoded as base64url strings). */
export async function performPasskeyRegister(
  optionsJson: string,
): Promise<Record<string, unknown>> {
  const opts = JSON.parse(optionsJson);
  // ``challenge`` + ``user.id`` + every ``excludeCredentials[].id``
  // need to become Uint8Array on the way into the browser API.
  opts.challenge = _b64urlToBytes(opts.challenge);
  if (opts.user && typeof opts.user.id === "string") {
    opts.user.id = _b64urlToBytes(opts.user.id);
  }
  if (Array.isArray(opts.excludeCredentials)) {
    opts.excludeCredentials = opts.excludeCredentials.map(
      (c: { id: string; type?: string; transports?: string[] }) => ({
        ...c,
        id: _b64urlToBytes(c.id),
      }),
    );
  }
  const cred = await navigator.credentials.create({ publicKey: opts }) as
    PublicKeyCredential | null;
  if (cred == null) {
    throw new Error("Browser returned no credential.");
  }
  const attResp = cred.response as AuthenticatorAttestationResponse;
  return {
    id: cred.id,
    rawId: _bytesToB64Url(cred.rawId),
    type: cred.type,
    response: {
      attestationObject: _bytesToB64Url(attResp.attestationObject),
      clientDataJSON:    _bytesToB64Url(attResp.clientDataJSON),
    },
    clientExtensionResults: cred.getClientExtensionResults(),
  };
}


/** Same shape as ``performPasskeyRegister`` but for the
 *  authentication ceremony. Used by the punch flow when the
 *  store requires a passkey. */
export async function performPasskeyAssert(
  optionsJson: string,
): Promise<Record<string, unknown>> {
  const opts = JSON.parse(optionsJson);
  opts.challenge = _b64urlToBytes(opts.challenge);
  if (Array.isArray(opts.allowCredentials)) {
    opts.allowCredentials = opts.allowCredentials.map(
      (c: { id: string; type?: string; transports?: string[] }) => ({
        ...c,
        id: _b64urlToBytes(c.id),
      }),
    );
  }
  const cred = await navigator.credentials.get({ publicKey: opts }) as
    PublicKeyCredential | null;
  if (cred == null) {
    throw new Error("Browser returned no credential.");
  }
  const assertResp = cred.response as AuthenticatorAssertionResponse;
  return {
    id: cred.id,
    rawId: _bytesToB64Url(cred.rawId),
    type: cred.type,
    response: {
      authenticatorData: _bytesToB64Url(assertResp.authenticatorData),
      clientDataJSON:    _bytesToB64Url(assertResp.clientDataJSON),
      signature:         _bytesToB64Url(assertResp.signature),
      userHandle: assertResp.userHandle
        ? _bytesToB64Url(assertResp.userHandle)
        : null,
    },
    clientExtensionResults: cred.getClientExtensionResults(),
  };
}
