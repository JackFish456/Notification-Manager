# Graph Teams notify bridge

Small **Windows tray app** that signs into your **Microsoft work account**, reads **Teams chats** via **Microsoft Graph** (`Chat.Read`), and shows **alerts** for new chat messages. You can show either **built-in Windows toasts** (so tools like **TopNotify** can reposition them) or a **custom top-of-screen card** that animates **down into place** and **up off the screen** (Windows does not expose swipe direction for real shell toasts, so this is the way to get vertical motion).

This is **not** an official Kiewit or Microsoft product. Use only if your **IT and security policies** allow it.

## Prerequisites

- Windows 10/11
- Python **3.12** (or adjust `run.ps1` to your installed version)
- An **Azure AD app registration** in your tenant (see below) with admin-approved consent for `Chat.Read` (delegated) if required by policy

## One-time: Azure AD app registration

1. In [Azure Portal](https://portal.azure.com/) go **Microsoft Entra ID** → **App registrations** → **New registration**.
2. Name it (for example) `Notification Manager`, account type **Single tenant** (or multitenant if you know you need it).
3. Under **Authentication** → **Platform configurations** → **Add a platform** → **Mobile and desktop applications**:
   - Enable the MSAL redirect URI **`https://login.microsoftonline.com/common/oauth2/nativeclient`** (and/or **`http://localhost`** as used by MSAL’s loopback listener—your tenant may require both to be checked).
4. Under **API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated**:
   - `Chat.Read`
   - `User.Read`
5. Click **Grant admin consent** if your organization requires it (common for `Chat.Read`).

Copy the **Application (client) ID** into `config.json`.

## Configure

1. Copy `config.example.json` to `config.json` (the first run of `run.ps1` copies it if missing).
2. Edit `config.json`:
   - **`client_id`**: Application (client) ID from Azure.
   - **`tenant_id`**: Your directory tenant ID, or use **`organizations`** for any work/school account in the commercial cloud (adjust if you use GCC/GCCH).
   - **`poll_interval_seconds`**: How often to poll Graph (minimum 15; default 60).
   - **`toast_app_id`**: Label shown for toasts (default `NotificationManager`); keep it stable so Windows groups them consistently.
   - **`use_top_overlay`**: `true` = draw our own **top-centered** notification (~toast-sized) with **slide-down enter** and **slide-up exit**; `false` = use **Windows-Toasts** (shell toasts).
   - **`overlay_width`**, **`overlay_height`**, **`overlay_top_margin`**: layout for the overlay card (pixels).
   - **`overlay_dwell_seconds`**: how long the card stays before sliding away (1.5–120 s; also adjustable in **Customize**).
   - **`overlay_opacity`**: window alpha for the custom banner (0.35–1.0; **Customize** uses percent).
   - **`overlay_enter_ms`**, **`overlay_exit_ms`**: animation duration for enter/exit.

Overlay mode uses **Tkinter** on the **main UI thread** (required on Windows) while the tray icon runs on a background thread. Cards are centered on the **primary** monitor’s width.

## Run

From this folder:

```powershell
.\run.ps1
```

On first launch a **browser window** opens for Microsoft sign-in. Tokens are cached under:

`%LOCALAPPDATA%\GraphTeamsNotifyBridge\`

Logs: `%LOCALAPPDATA%\GraphTeamsNotifyBridge\bridge.log`

Tray:

- **Left-click** the icon — **Customize** (opacity slider + dwell-time dropdown); settings are saved to `config.json`  
- **Right-click** — full menu  

Menu items:

- **Mini CLI…** — small command window (`help`, `status`, `poll`, `auth`, `log`, `config`, `data`, `clear`, `exit`)  
- **Open data folder** — token cache, state, logs  
- **Edit config.json**  
- **Sign out** — removes token cache and chat state  

## Initialize a Git repo (optional)

```powershell
cd $env:USERPROFILE\OneDrive*\Desktop\Notifications   # or your Desktop path
git init
git add .
git commit -m "Add Graph Teams notify bridge"
```

Create an empty repo on GitHub, then:

```powershell
git remote add origin https://github.com/<you>/<repo>.git
git branch -M main
git push -u origin main
```

## Limitations (MVP)

- Polls **Graph chat** threads (`/me/chats`), not **Teams channel** posts (`Team.ReadBasic.All` / channel APIs are not implemented here).
- May miss bursts of messages between polls (only the latest message per chat is considered).
- Interactive sign-in may open again if refresh fails (for example policy blocks silent refresh).

## Security notes

- Minimize retention: the app stores **message IDs and timestamps**, not full message bodies, in `state.json`.
- Do **not** commit `config.json` if it ever contains secrets (for public clients the client ID is not a secret, but keep tenant-specific details policy-aligned).
