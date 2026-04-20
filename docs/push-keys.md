# Push notification keys

DineroBook supports Web Push (PWA notifications) for any user who
opts in from the avatar dropdown. The opt-in UI and the
`/api/push/*` endpoints are hidden until VAPID credentials are
present in the environment.

## Generate a keypair (once, per environment)

```bash
pip install pywebpush
python - <<'PY'
from py_vapid import Vapid
v = Vapid()
v.generate_keys()
print("VAPID_PUBLIC_KEY=", v.public_key_urlsafe_base64())
print("VAPID_PRIVATE_KEY=", v.private_key_urlsafe_base64())
PY
```

## Set on Render (or your host)

- `VAPID_PUBLIC_KEY` — the `public_key_urlsafe_base64` output
- `VAPID_PRIVATE_KEY` — the `private_key_urlsafe_base64` output
- `VAPID_SUBJECT` — a `mailto:` or `https://` URL you own, e.g.
  `mailto:ops@yourdomain.com` (the push provider contacts this
  address if your sends misbehave)

Redeploy. The avatar dropdown now shows "Enable notifications" for
every user on a supported browser.

## Sending from code

```python
from app import send_push
send_push(user.id, title="New ACH batch", body="INTX-2025-0421 cleared",
          url="/batches", tag="ach-INTX-2025-0421")
```

Use `tag` to collapse multiple sends of the same event so the user
sees the latest one, not a stack.

## Testing

Log in, open the avatar dropdown → "Enable notifications" → grant
permission. Then:

```bash
curl -X POST -b 'session=...' https://your-app/api/push/test
```

(Easier: hit `/api/push/test` from the browser devtools console
while logged in.)
