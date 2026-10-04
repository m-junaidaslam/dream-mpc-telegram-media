# DREAM-MPC Telegram Media Downloader

Telegram-to-Jellyfin media ingestion system for the DREAM-MPC home server.

This project allows media received through Telegram to be forwarded to a private bot and automatically imported into the appropriate Jellyfin media directory.

## Overview

Typical workflow:

```text
Friend sends media through Telegram
        |
        v
Forward file to DREAM-MPC Media bot
        |
        v
Choose media type
Shows | Movies | Music | Home
        |
        v
For Shows, choose a recent/suggested destination
or type the show/season path manually
        |
        v
Telegram Bot API downloads the file locally
        |
        v
Media Downloader validates the destination
        |
        v
Copy to Jellyfin using a temporary .part file
        |
        v
Verify completed copy
        |
        v
Atomic rename to final filename
        |
        v
Remove Telegram temporary media
        |
        v
Jellyfin sees the completed file
```

## Features

- Dedicated Telegram bot for DREAM-MPC media ingestion
- Only an explicitly configured Telegram user is authorized
- Supports large Telegram files using the local Telegram Bot API server
- One-tap media category selection
- Home, Movies, Music, and Shows destinations
- Two recently used Show destinations
- Suggested Show/Season destination derived from filenames when possible
- Manual Show/Season destination entry
- Persistent Status, History, and Cancel controls in Telegram
- Download/import queue
- Duplicate-file protection
- Strict destination/path validation
- Disk-space checks
- Low-storage warning
- Temporary `.part` files so Jellyfin never sees incomplete media
- Telegram temporary-file cleanup after successful import
- Temporary-file cleanup after cancellation or failure
- Interrupted-download recovery after Docker/Windows restart
- Persistent history and state
- Rotating application logs
- Docker health check

## Repository Structure

```text
dream-mpc-telegram-media/
├── README.md
├── .env.example
├── .gitignore
├── compose.yaml
├── Dockerfile
├── data/                     # Runtime only, ignored by Git
└── downloader/
    ├── Dockerfile
    ├── bot.py
    ├── config.py
    ├── media.py
    ├── state.py
    ├── suggestions.py
    ├── telegram_api.py
    └── ui.py
```

## Live Location

The repository is normally cloned directly to its live location on DREAM-MPC:

```text
C:\Docker\telegram-bot-api
```

There is no second deployment copy. The Git working tree is the source used by Docker to build and run the service.

## Architecture

The project contains two Docker services.

### Telegram Bot API

The local Telegram Bot API server acts as the Telegram gateway and provides local-mode file handling for large media transfers.

It is built from Telegram's upstream Bot API source and runs inside Docker.

The local API endpoint is bound to DREAM-MPC localhost rather than exposed to the LAN:

```text
http://127.0.0.1:8081
```

### Telegram Media Downloader

The downloader is a small Python application that:

1. Polls the local Bot API for Telegram updates.
2. Accepts messages only from the configured Telegram user.
3. Presents destination choices in Telegram.
4. Validates the requested destination.
5. Obtains the Telegram local file path.
6. Imports the file into Jellyfin safely.
7. Cleans temporary files.
8. Maintains persistent history, queue state, recent Show destinations, and recovery metadata.

## Jellyfin Media Layout

The DREAM-MPC Jellyfin media root is:

```text
C:\JellyFin
```

Expected directories:

```text
C:\JellyFin\
├── Home\
├── Movies\
├── Music\
└── Shows\
```

Inside the downloader container this directory is mounted as:

```text
/media
```

Examples:

```text
/media/Movies
-> C:\JellyFin\Movies

/media/Music
-> C:\JellyFin\Music

/media/Shows/The Neighborhood/Season 08
-> C:\JellyFin\Shows\The Neighborhood\Season 08
```

## Prerequisites

DREAM-MPC requires:

- Windows
- Docker Desktop
- Docker Compose
- Internet connectivity
- Jellyfin media directories under `C:\JellyFin`
- Telegram account
- Telegram bot created through BotFather
- Telegram API ID and API Hash from Telegram

Telegram API application credentials can be created at:

https://my.telegram.org

Telegram Bot API documentation:

https://core.telegram.org/bots/api

Telegram Bot API server source:

https://github.com/tdlib/telegram-bot-api

## Telegram Setup

### 1. Create the Telegram Bot

Open BotFather in Telegram:

https://t.me/BotFather

Create a new bot with:

```text
/newbot
```

Example display name:

```text
DREAM-MPC Media
```

The username must end with `bot`.

BotFather returns a bot token.

Treat this token as a password. Never commit it to Git.

### 2. Get Your Telegram User ID

Send a message to the new bot and retrieve the update through the Telegram Bot API, or use another trusted method to determine your numeric Telegram user ID.

The downloader uses this value as an authorization whitelist.

Messages from other Telegram users are ignored.

### 3. Create Telegram API Credentials

Go to:

https://my.telegram.org

Open **API development tools** and create an application.

The application provides:

```text
API ID
API Hash
```

These values are required by the local Telegram Bot API server.

## Environment Configuration

Copy:

```text
.env.example
```

to:

```text
.env
```

Example PowerShell command:

```powershell
Copy-Item .env.example .env
```

Configure:

```env
TELEGRAM_API_ID=YOUR_API_ID
TELEGRAM_API_HASH=YOUR_API_HASH
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
TELEGRAM_ALLOWED_USER_ID=YOUR_TELEGRAM_USER_ID
```

The real `.env` file is ignored by Git and must never be committed.

## Downloader Configuration

Most settings intended for future customization are centralized in:

```text
downloader/config.py
```

This is the first file to review when adapting the downloader to a different DREAM-MPC configuration.

Configuration includes items such as:

- Media directory categories
- Disk-space warning threshold
- Minimum free-space reserve
- History length
- Number of recent Show destinations
- Copy/progress behavior
- Application paths

The current media categories are:

```text
Home
Movies
Music
Shows
```

## Docker Deployment

Navigate to the repository:

```powershell
cd C:\Docker\telegram-bot-api
```

### First Build

The Telegram Bot API image is compiled from source during its initial image build and can take a significant amount of time.

Build and start the project:

```powershell
docker compose up -d --build
```

After the Telegram Bot API image has been built once, normal restarts do not rebuild it.

### Normal Startup

```powershell
docker compose up -d
```

### Check Status

```powershell
docker compose ps
```

Expected services:

```text
telegram-bot-api
telegram-media-downloader
```

### Check Downloader Logs

```powershell
docker compose logs --tail 50 media-downloader
```

### Follow Logs Live

```powershell
docker compose logs -f media-downloader
```

## Testing the Local Bot API

The local Bot API is bound to localhost on port `8081`.

Test the configured bot from DREAM-MPC:

```powershell
curl.exe "http://127.0.0.1:8081/botYOUR_BOT_TOKEN/getMe"
```

A successful result includes:

```json
{
  "ok": true
}
```

Do not paste or publish the real Bot Token.

## Bot Workflow

### Forwarding a File

Forward a media file to the DREAM-MPC Media bot.

The bot asks for the media category:

```text
Shows
Movies
Music
Home
```

### Movies, Music, and Home

Selecting one of these begins the import directly into the corresponding Jellyfin directory.

Examples:

```text
Movies
-> C:\JellyFin\Movies

Music
-> C:\JellyFin\Music

Home
-> C:\JellyFin\Home
```

### Shows

Selecting Shows opens Show-specific destination choices.

The bot can offer:

- Most recently used Show/Season destination
- Second most recently used Show/Season destination
- Suggested destination derived from the forwarded filename

Example recent destinations:

```text
The Neighborhood/Season 08
The Neighborhood/Season 05
```

Internally they map to:

```text
Shows/The Neighborhood/Season 08
Shows/The Neighborhood/Season 05
```

### Manual Show Destination

After selecting Shows, a destination may also be typed directly without the `Shows/` prefix.

Example input:

```text
The Big Bang Theory/Season 02
```

The downloader converts it to:

```text
Shows/The Big Bang Theory/Season 02
```

## Show Destination Suggestions

The downloader contains a conservative filename parser in:

```text
downloader/suggestions.py
```

For example:

```text
The.Neighborhood.S08E05.1080p.WEB-DL.mkv
```

may produce the suggestion:

```text
The Neighborhood/Season 08
```

Suggestions are never automatically selected.

The user always remains in control of the destination.

## Persistent Telegram Controls

Telegram provides persistent controls for common operations:

```text
Status
History
Cancel
```

### Status

Displays information such as:

- Current active import
- Destination
- Number of queued files
- Free disk space
- Recent/last destination state

### History

Displays recent completed, failed, or cancelled media imports.

History is intentionally limited rather than growing indefinitely.

### Cancel

Requests cancellation of the current import.

If Telegram is still obtaining the local media file, cancellation may only complete after the Telegram-side transfer finishes.

After cancellation, the downloader removes temporary Telegram media and Jellyfin `.part` files.

## Queueing

Only one import is processed at a time.

Additional files can be queued while another import is active.

Example:

```text
Active:
Episode A

Queue:
Episode B
Episode C
```

When the current import finishes, the next queued item starts automatically.

This avoids unnecessary simultaneous multi-gigabyte disk operations on DREAM-MPC.

## Duplicate Protection

The downloader never automatically overwrites an existing Jellyfin media file.

If the destination already contains the same filename, the import fails safely and the existing media remains untouched.

## Path Security

Telegram input is not allowed to write arbitrary files on DREAM-MPC.

The downloader restricts destinations to the configured Jellyfin media roots.

Examples that are rejected include:

```text
../../Windows
C:\Windows
/users/example
```

Absolute paths and traversal components such as `..` are rejected.

## Temporary File Lifecycle

The downloader is intentionally designed to avoid permanent duplicate storage.

Normal successful flow:

```text
Telegram
   |
   v
Local Telegram cache
   |
   v
Jellyfin .filename.part
   |
   v
Copy verification
   |
   v
Atomic rename to filename
   |
   v
Delete Telegram cached media
```

The final media file is therefore the only large long-term copy created by this workflow.

Telegram's small internal state files remain in the Bot API data directory.

## Cancellation Cleanup

When an import is cancelled:

```text
Jellyfin .part file
-> deleted

Telegram cached media
-> deleted

Final Jellyfin file
-> not created
```

The Telegram transfer itself may finish before cancellation cleanup becomes possible, depending on when cancellation is requested.

## Restart and Crash Recovery

The downloader persists enough state to recover an interrupted job when Docker, Windows, or the Compose project restarts.

Recovery behavior:

```text
Interrupted import detected
        |
        v
Clean known Jellyfin .part file
        |
        v
Clean known Telegram cached media
        |
        v
Clean orphaned current-bot temporary media when necessary
        |
        v
Requeue interrupted job
        |
        v
Retry import cleanly
```

During recovery, Telegram may temporarily create multiple working files. Once the recovered import completes, stale temporary media is cleaned up.

Persistent Telegram files such as internal binlogs are preserved.

## Persistent State

Downloader state is stored separately from source code.

Persistent state includes:

- Telegram update offset
- Recent Show destinations
- Pending item
- Active import metadata
- Queue
- Import history
- Recovery metadata

Docker volumes are used for persistent downloader state and logs.

These runtime files are not stored in Git.

## Disk-Space Protection

Before importing media, the downloader checks available disk space.

Two thresholds are used:

- Warning threshold
- Minimum free-space reserve

The downloader can warn through Telegram when storage becomes low and refuses imports that would violate the configured reserve.

Review these values in:

```text
downloader/config.py
```

## Logging

Application logs use rotating log files rather than one indefinitely growing file.

Logs are runtime data and are excluded from Git.

Docker logs can be inspected with:

```powershell
docker compose logs --tail 100 media-downloader
```

## Health Check

The downloader Docker image includes a health check based on a health marker maintained by the application.

Container status can be inspected using:

```powershell
docker compose ps
```

The Telegram containers are also monitored by Uptime Kuma on DREAM-MPC.

If either container fails, Uptime Kuma sends a Telegram alert.

## Updating Downloader Code

The Python downloader is much faster to rebuild than the Telegram Bot API C++ image.

After changing files under `downloader/`, rebuild only the downloader:

```powershell
cd C:\Docker\telegram-bot-api
docker compose build media-downloader
docker compose up -d
```

Do not rebuild the Telegram Bot API image unless its Dockerfile or upstream Telegram source needs to be updated.

## Updating Git

Because this repository is also the live project directory, code changes are committed directly from:

```text
C:\Docker\telegram-bot-api
```

Review changes:

```powershell
git status
git diff
```

Commit after testing:

```powershell
git add .
git commit -m "Describe the Telegram media change"
git push
```

## Security

Never commit:

- `.env`
- Telegram Bot Token
- Telegram API Hash
- Telegram API credentials
- Personal Telegram identifiers that should remain private
- Cached Telegram media
- Runtime state
- Logs
- Private keys

The `.gitignore` is configured to exclude runtime and secret files.

If a Telegram Bot Token is accidentally exposed, revoke/regenerate it through BotFather and update the local `.env` file.

## Data Directory

Telegram Bot API runtime state and caches are stored under:

```text
C:\Docker\telegram-bot-api\data
```

This directory is ignored by Git.

Do not delete it casually while the Bot API is running.

For a deliberate clean reset, stop the Compose project first before cleaning runtime data.

## Disaster Recovery

To restore the Telegram Media Downloader on a rebuilt DREAM-MPC:

1. Install Docker Desktop.
2. Restore the Jellyfin media directory structure.
3. Clone this repository to `C:\Docker\telegram-bot-api`.
4. Create `.env` from `.env.example`.
5. Restore the Telegram API ID and API Hash from secure storage.
6. Restore or regenerate the Telegram Bot Token.
7. Configure the authorized Telegram User ID.
8. Review `downloader/config.py` for current paths/settings.
9. Build the Telegram Bot API image.
10. Build the Media Downloader image.
11. Start the Compose project.
12. Verify `getMe` through the local Bot API.
13. Send `Status` to the Telegram bot.
14. Test a small media import.
15. Verify temporary media cleanup.
16. Verify Uptime Kuma monitoring.

Persistent history/queue state does not need to be restored for the media library itself to remain usable.

## Related Repositories

### DREAM-MPC Homelab

Master architecture and disaster-recovery guide:

https://github.com/m-junaidaslam/dream-mpc-homelab

### DREAM-MPC Docker Services

Glance, Uptime Kuma, and Immich deployment configuration:

https://github.com/m-junaidaslam/dream-mpc-docker-services

### DREAM-MPC Automation

Windows, Immich, and Oracle Cloud automation scripts:

https://github.com/m-junaidaslam/dream-mpc-automation
