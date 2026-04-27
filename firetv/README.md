# DineroBook TV — Fire TV companion app

Thin WebView shell for the [TV Display add-on](../app.py). On launch
the app shows a 6-character pair code; the operator types that code
into `/tv-display` in their DineroBook account, the app polls until
claimed, then runs the per-device rate-board URL fullscreen on a
Fire TV / Google TV / sideloaded Android device.

The app itself does almost nothing — the actual rate board is the
existing `templates/tv_display_public.html` rendered by the backend.
This APK exists to:

1. Get listed on the Amazon Appstore so operators can install with
   one click.
2. Tie each Fire TV to a single `TVPairing` row (enforced backend-
   side: claiming a new code revokes any prior pairing on that
   store's display).
3. Auto-recover from revocation by routing back to the pairing
   screen when the WebView hits a 404.

## Pairing flow

This is the standard "TV displays code, user enters code on their
phone" pattern (Netflix, YouTube, Disney+ all work this way):

1. Fire TV opens the app → POST `/api/tv-pair/init`. Server creates
   a `TVPendingPair` with a fresh 6-char code + a stable
   `device_token`. Returns both.
2. App displays the code huge + the line "Open dinerobook.com/...
   in your DineroBook account."
3. Operator on `/tv-display` types the code into the claim input,
   clicks Pair. Server validates → revokes any prior active
   `TVPairing` on this display → creates a new `TVPairing` reusing
   the `device_token` from the pending row.
4. App polls GET `/api/tv-pair/status?token=<device_token>` every
   2 seconds. When the response flips to `{status: "claimed",
   display_url}`, the app stashes the URL and transitions to the
   fullscreen WebView.
5. If the code expires before claim (10 min), the app silently
   re-inits — operator sees a fresh code with no manual reset
   needed.

## Architecture

| Component | File | Job |
|-----------|------|-----|
| `MainActivity` | `kotlin/.../MainActivity.kt` | Router — read prefs, fire either `PairingActivity` or `DisplayActivity`. |
| `PairingActivity` | `kotlin/.../PairingActivity.kt` | On launch: POST `/api/tv-pair/init`, display the code, poll `/api/tv-pair/status` until claimed. No on-screen input. |
| `DisplayActivity` | `kotlin/.../DisplayActivity.kt` | Fullscreen sticky-immersive WebView. On main-frame 404 → wipe prefs, bounce to `MainActivity` (which routes to pairing). |
| `PairApi` | `kotlin/.../PairApi.kt` | OkHttp wrapper for `/init` + `/status` (sealed result classes for compile-time pattern-matching). |
| `Prefs` | `kotlin/.../Prefs.kt` | SharedPreferences for the single stored URL. |

All five files together are ~280 lines. There is no business logic
here that isn't on the backend.

## Build

You'll need:

- **Android Studio** Hedgehog or newer (Iguana / Jellyfish are fine).
- **JDK 17** (Android Studio bundles one — no separate install
  needed).
- **Internet** for the first sync (Gradle wrapper + dependencies).

### One-time setup

```bash
cd firetv/
# Open in Android Studio:
#   File → Open → select this `firetv/` folder.
# Click "Trust Project", then "Sync Now" when prompted.
# Studio fetches the Gradle wrapper, AGP, AndroidX deps automatically.
```

### Build a debug APK (for sideload testing)

```
Build → Build Bundle(s) / APK(s) → Build APK(s)
```

Output: `firetv/app/build/outputs/apk/debug/app-debug.apk`. Install
on a Fire TV via `adb install app-debug.apk` after enabling
**Settings → My Fire TV → Developer Options → ADB Debugging**.

### Sign for release (required for Amazon Appstore)

1. Create a release keystore (one-time, **never commit it**):
   ```bash
   keytool -genkey -v \
     -keystore ~/dinerobook-release.jks \
     -alias dinerobook-tv \
     -keyalg RSA -keysize 2048 -validity 36500
   ```
2. Save passwords + alias somewhere durable (1Password,
   Render-side env vars, etc.). **If you lose the keystore you
   lose the ability to ship updates** — Amazon will require the
   same signing key for every future version.
3. In Android Studio:
   `Build → Generate Signed Bundle / APK → APK → next →`
   browse to `~/dinerobook-release.jks`, enter the alias and
   passwords → select `release` → finish.
4. Output: `app/build/outputs/apk/release/app-release.apk`. This
   is what you upload to Amazon.

### Pointing at staging

Default `BASE_URL` is `https://dinerobook.onrender.com`. To build
against a staging environment:

```bash
cd firetv/
./gradlew :app:assembleDebug -PBASE_URL=https://staging.example.com
```

(Or set `BASE_URL=...` in `firetv/local.properties`.)

## Amazon Appstore submission

You'll need a paid [Amazon Developer
Console](https://developer.amazon.com/) account (free for individual
publishers).

### Required listing assets

| Asset | Spec | Where to put it |
|-------|------|-----------------|
| Application APK | signed release APK from above | App File(s) tab |
| App icon | **512 × 512** PNG, 32-bit | App Information |
| Application banner | **1280 × 720** PNG, 16:9 | Images & Multimedia |
| Screenshots | **3–10** images, 1280×720 PNG | Images & Multimedia |
| Short description | ≤ 80 chars | App Information |
| Long description | ≤ 4000 chars | App Information |
| Content rating | Questionnaire (no objectionable content) | Content Rating |

### Suggested listing copy

**Short description**
> Live exchange-rate board for money-transfer stores, powered by
> DineroBook.

**Long description**
> DineroBook TV turns your Fire TV into a live money-transfer
> exchange-rate board for your storefront. Display real-time rates
> across countries (Mexico, Guatemala, Honduras…) and money-transfer
> companies (Intermex, Maxi, Barri…), updated from your DineroBook
> admin console with a 30-second refresh.
>
> Open the app on your Fire TV — it shows a 6-character code. Type
> the code into the TV Display page in your DineroBook admin to
> link your shop's rates to the TV. Each Fire TV is tied to one
> paid subscription.
>
> Requires an active DineroBook subscription with the TV Display
> add-on enabled. Sign up at https://dinerobook.onrender.com/signup.

**Permissions explanation**
> Internet access is required to fetch live rates from the
> DineroBook backend. No personal data is collected or transmitted.

### Replacing the placeholder banner / icon

The in-APK banner (`firetv/app/src/main/res/drawable/app_banner.xml`)
is a vector placeholder. For Amazon's listing you need:

1. A **1280×720 PNG** banner (Amazon scrutinizes this more than the
   in-app drawable). Drop it into
   `firetv/app/src/main/res/drawable-nodpi/app_banner.png` and
   delete `app_banner.xml`. Rebuild + re-upload.
2. A **512×512 PNG** small icon. Replace
   `firetv/app/src/main/res/drawable/ic_launcher.xml` with
   `firetv/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png` (and
   ideally fan out to mipmap-hdpi, -xhdpi, -xxhdpi, -xxxhdpi using
   Android Studio's **Image Asset Studio**: `New → Image Asset`).

### Submission checklist

- [ ] Built signed release APK (debug builds are rejected).
- [ ] Banner + icon are PNG, not vector (Amazon vendor team will
      ask).
- [ ] At least 3 screenshots showing the TV view in action with
      real-looking rates.
- [ ] Long description mentions the subscription requirement.
- [ ] Content rating: "Everyone" / "All Ages."
- [ ] Pricing: **Free** (the $5/mo is billed via Stripe in the web
      app, not Amazon IAP — never set a price here, and never enable
      Amazon IAP for this app).
- [ ] Distribution: Amazon devices only for now (we'll add
      Google TV / Play Store as a separate listing later).

Amazon's review takes 1–3 business days. Reviewers will install the
app; if pairing fails (e.g. the test reviewer doesn't have a
subscription), they'll reject. Either:

- Comp the addon on a dedicated `amazon-review@dinerobook.com` test
  account before submitting (preferred), or
- Add a small "demo mode" flag to the app that skips pairing and
  loads a fixed marketing-demo URL (only enable when reviewer enters
  a test code like `DEMO00`).

If you want me to add the demo-mode flag, open an issue and I'll
ship it as a follow-up.

## Re-pairing in the field

Operators occasionally need to switch a Fire TV from one store to
another (acquisition, relocation). Three ways to re-pair:

1. **From the admin web UI**: tap "Unpair this Fire TV" on the
   target store's `/tv-display` page. The Fire TV's WebView will
   404 on its next refresh and auto-route back to pairing.
2. **From the Fire TV remote**: long-press **MENU** on the remote
   while the rate board is showing. Wipes local state and shows the
   pairing screen.
3. **From a different store admin**: open the app on the Fire TV
   to get a fresh code, sign into the new store's admin, type the
   code into `/tv-display`. The new pairing automatically revokes
   the old one (server-side enforcement — see `tv_display_claim`
   in `app.py`).

## Updating the app

Ship a new APK by:

1. Bumping `versionCode` (must monotonically increase) and
   `versionName` in `firetv/app/build.gradle.kts`.
2. Building + signing a release APK with the **same** keystore.
3. Uploading via the Amazon Developer Console as a new version.

Existing paired Fire TVs auto-update when Amazon pushes the new
version. The pairing state survives — the new APK reads the same
SharedPreferences file (`dinerobook_tv_prefs`).

## Backend contract reference

If you change the backend contract, search this directory for the
matching string and update both sides at once:

| Backend symbol | App-side reference |
|----------------|--------------------|
| `POST /api/tv-pair/init` request body `device_label` | `PairApi.kt` `init()` |
| `POST /api/tv-pair/init` response keys (`code`, `device_token`, `expires_at`, `ttl_seconds`) | `PairApi.kt` `InitResult.Success` |
| `GET /api/tv-pair/status` query param `token` | `PairApi.kt` `pollStatus()` |
| `/status` response variants (`pending`, `claimed`, `expired`) | `PairApi.kt` `StatusResult` sealed class |
| `/status` claimed payload keys (`display_url`, `store_name`, `title`) | `PairApi.kt` `StatusResult.Claimed` |
| `POST /tv-display/claim` form field `code` | admin-side template; not directly called by the app |
| `GET /tv/device/<device_token>` | `DisplayActivity.kt` (URL is opaque to the app — comes from `/status` Claimed) |
