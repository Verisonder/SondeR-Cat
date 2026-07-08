# SondeR cat — Microsoft Store (MSIX) build

This folder builds the **Store version** of SondeR cat. It's the *same*
`sondercat.py` / `sprites.py` / `libs` as the GitHub build — one source, two
packages. The difference:

|                     | GitHub build (installer)      | Store build (MSIX)              |
|---------------------|-------------------------------|---------------------------------|
| Python              | uses/installs system Python   | **bundles** embeddable Python   |
| Signing             | SmartScreen reputation        | **Microsoft signs it, free**    |
| Updates             | app self-updates from repo    | **Microsoft Store** pushes them |
| Channel flag        | `APP_CHANNEL = "github"`       | `APP_CHANNEL = "store"` (via the `STORE_BUILD` marker) |

The packaging drops an empty `STORE_BUILD` file next to `sondercat.py`, which
flips the app to the Store channel and disables the self-updater — no code
fork needed.

## One-time setup (only you can do these)

1. **Create a free developer account** at <https://partner.microsoft.com> /
   `storedeveloper.microsoft.com`. As of 2026 registration is free for
   individuals and companies; you verify identity with a government ID + selfie.
2. **Reserve the name** "SondeR cat": Partner Center → Apps and games →
   New product → MSIX app → check availability → reserve.
3. From the reserved app, copy three values (Product management → Product
   identity):
   - **Package/Identity/Name**  (e.g. `1234ABCD.SondeRcat`)
   - **Package/Identity/Publisher**  (e.g. `CN=xxxxxxxx-....`)
   - **Publisher display name**

## Store logos

Put PNG logos in `msix/store-assets/` (the build copies them into the package):
`StoreLogo.png` (50×50), `Square44x44Logo.png`, `Square71x71Logo.png`,
`Square150x150Logo.png`, `Square310x310Logo.png`, `Wide310x150Logo.png`.
These can be generated from the app icon with the Store's asset generator or
any icon tool.

## Build (Windows, Windows SDK + a C compiler on PATH)

```powershell
pwsh ./msix/build_msix.ps1 `
     -IdentityName  "1234ABCD.SondeRcat" `
     -Publisher     "CN=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" `
     -PublisherName "Your Name"
```

Output: `msix/out/SondeRcat.msix` — **unsigned by design**; the Store re-signs
it during certification. You can locally validate it with the Windows App
Certification Kit (`certutil` / `WACK`) before submitting.

## Submit

- **Manually:** Partner Center → your app → Packages → upload the `.msix` →
  fill the Store listing (description, screenshots, the logos above, age
  rating) → Submit. Certification is typically 1–3 business days.
- **Automatically:** see `.github/workflows/store-release.yml` (added
  separately) — on a new GitHub release it builds the MSIX and submits it via
  the Store submission API, so one release updates both channels.

## Notes / limitations of the Store build

- Runs fully self-contained; needs no system Python.
- `runFullTrust` is declared so the global keyboard/mouse hooks and
  foreground-window detection keep working inside the MSIX container.
- The install directory is read-only, so the in-app "open sprites.py to edit
  animations" flow won't persist there — that's a power-user feature that
  stays on the GitHub build. Everything else is identical.
