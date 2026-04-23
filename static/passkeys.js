/*
 * Passkeys (WebAuthn) client helper.
 *
 * Shared by two surfaces:
 *   - Account Settings → Security: "Add a passkey" button wires into
 *     registerPasskey() to run the create() ceremony.
 *   - Login page: "Sign in with passkey" button wires into
 *     loginWithPasskey() to run the get() ceremony (discoverable
 *     credentials — no username required).
 *
 * Both do a begin → browser ceremony → finish round-trip with the
 * server. The server's JSON is browser-native on the wire (the
 * library's options_to_json produces arrays/strings — we have to
 * decode b64url → Uint8Array fields before handing them to the
 * browser API, and re-encode the authenticator response on the way
 * back).
 */
(function (global) {
  'use strict';

  function b64urlDecode(s) {
    // base64url → ArrayBuffer
    s = String(s).replace(/-/g, '+').replace(/_/g, '/');
    while (s.length % 4) s += '=';
    var bin = atob(s);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes.buffer;
  }

  function b64urlEncode(buf) {
    // ArrayBuffer → base64url
    var bytes = new Uint8Array(buf);
    var s = '';
    for (var i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  function serializeAttestation(cred) {
    // PublicKeyCredential → plain JSON that py_webauthn can verify.
    return {
      id: cred.id,
      rawId: b64urlEncode(cred.rawId),
      type: cred.type,
      response: {
        clientDataJSON:    b64urlEncode(cred.response.clientDataJSON),
        attestationObject: b64urlEncode(cred.response.attestationObject),
      },
      clientExtensionResults: cred.getClientExtensionResults
                              ? cred.getClientExtensionResults() : {},
    };
  }

  function serializeAssertion(cred) {
    return {
      id: cred.id,
      rawId: b64urlEncode(cred.rawId),
      type: cred.type,
      response: {
        clientDataJSON:    b64urlEncode(cred.response.clientDataJSON),
        authenticatorData: b64urlEncode(cred.response.authenticatorData),
        signature:         b64urlEncode(cred.response.signature),
        userHandle: cred.response.userHandle
                    ? b64urlEncode(cred.response.userHandle) : null,
      },
      clientExtensionResults: cred.getClientExtensionResults
                              ? cred.getClientExtensionResults() : {},
    };
  }

  function inflateRegistrationOptions(opts) {
    // Server hands us b64url strings for challenge/user.id + every
    // excludeCredentials[].id; the browser API wants ArrayBuffer.
    opts.challenge = b64urlDecode(opts.challenge);
    opts.user.id = b64urlDecode(opts.user.id);
    if (opts.excludeCredentials) {
      opts.excludeCredentials = opts.excludeCredentials.map(function (c) {
        return Object.assign({}, c, { id: b64urlDecode(c.id) });
      });
    }
    return opts;
  }

  function inflateAuthenticationOptions(opts) {
    opts.challenge = b64urlDecode(opts.challenge);
    if (opts.allowCredentials) {
      opts.allowCredentials = opts.allowCredentials.map(function (c) {
        return Object.assign({}, c, { id: b64urlDecode(c.id) });
      });
    }
    return opts;
  }

  function isSupported() {
    return !!(global.PublicKeyCredential
              && global.navigator && global.navigator.credentials
              && typeof global.navigator.credentials.create === 'function'
              && typeof global.navigator.credentials.get === 'function');
  }

  async function registerPasskey(name) {
    if (!isSupported()) {
      throw new Error('This browser does not support passkeys.');
    }
    var beginResp = await fetch('/account/passkeys/register/begin', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Accept': 'application/json' },
    });
    if (!beginResp.ok) {
      var msg = 'Could not start passkey setup.';
      try { msg = (await beginResp.json()).error || msg; } catch (e) {}
      throw new Error(msg);
    }
    var options = inflateRegistrationOptions(await beginResp.json());
    var credential = await navigator.credentials.create({ publicKey: options });
    var finishResp = await fetch('/account/passkeys/register/finish', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({
        credential: serializeAttestation(credential),
        name: name || '',
      }),
    });
    var payload = await finishResp.json().catch(function () { return {}; });
    if (!finishResp.ok || !payload.ok) {
      throw new Error(payload.error || 'Passkey could not be saved.');
    }
    return payload;
  }

  async function loginWithPasskey() {
    if (!isSupported()) {
      throw new Error('This browser does not support passkeys.');
    }
    var beginResp = await fetch('/login/passkey/begin', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Accept': 'application/json' },
    });
    if (!beginResp.ok) {
      var msg = 'Could not start passkey sign-in.';
      try { msg = (await beginResp.json()).error || msg; } catch (e) {}
      throw new Error(msg);
    }
    var options = inflateAuthenticationOptions(await beginResp.json());
    // mediation: "required" would only prompt on user gesture; default
    // is fine for a button click, but we pass it explicitly for clarity.
    var credential = await navigator.credentials.get({ publicKey: options });
    var finishResp = await fetch('/login/passkey/finish', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({ credential: serializeAssertion(credential) }),
    });
    var payload = await finishResp.json().catch(function () { return {}; });
    if (!finishResp.ok || !payload.ok) {
      throw new Error(payload.error || 'Passkey sign-in failed.');
    }
    return payload;
  }

  global.Passkeys = {
    isSupported: isSupported,
    registerPasskey: registerPasskey,
    loginWithPasskey: loginWithPasskey,
  };
})(window);
