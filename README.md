# discord-bot-template

This is a clean and modular Python Discord bot template built with [discord.py](https://discordpy.readthedocs.io/). This repository is designed to be used as a starting point for custom bot projects. It provides a structured foundation that can be adapted to a wide range of use cases.

## Features

* The template uses a cog-based architecture. Each feature group is implemented as an isolated and reloadable module.
* All configuration is handled through environment variables. No tokens or IDs are hardcoded in the source code.
* FFmpeg is resolved automatically from the system PATH or from a configurable environment variable.
* The `media` cog plays music from YouTube, SoundCloud, and Spotify, with a shared queue and a now-playing panel with buttons. [Music](#music) describes it.
* Commands that start work, such as `/play` and the queue commands, have per-member cooldowns, so one member cannot flood a channel. A member who is too fast gets a private message that says when to try again.
* Local development is supported through a `.env` file using `python-dotenv`.
* Audio, image, and video assets are stored as regular files that Git marks as binary.
* A `Strings` dataclass defines all user-facing messages as named format strings, in English and Finnish. Replies follow each user's Discord language, and `LOCALE` picks the fallback language. The default, `LOCALE=silent`, mutes public replies to commands but still sends private ones such as `/help` and admin replies. The music panel, the welcome, and the goodbye post under every setting, because someone turned them on.
* The `events` cog gives new members the role set with `/admin autorole`, and welcomes them in the bot channel set with `/admin channel`. With `/admin goodbye`, it also says goodbye there when a member leaves, but not when a member was banned.
* Moderation builds on Discord's own AutoMod. `/admin automod` manages keyword and preset rules, and blocked messages can count as warnings.
* The `/help` command is a short guide to the bot, in a reply that only you see. It says what the bot is for, and explains each loaded feature that you may use, with its commands and a tip or two. Members see only the features they can use, so only admins see how to set the bot up. The guide reflects whichever cogs are active at runtime, and a feature without a guide text lists its commands instead. A message that only mentions the bot, such as `@Bot`, gets a short reply with a button that opens the same guide for whoever presses it. The reply deletes itself after a minute, and a mention with other words gets no answer. `/about` is named at the bottom of the guide.
* The `/about` command shows the bot's version, how long it has been online, its response time, and a link to its source code. The bot's status reads "/help shows what I can do", or "🎵 Playing music" while music plays in any server, in the bot's own language. A bot made from the template gives itself a status of its own with `status_idle` in its `localization.py`.
* Dependencies are managed with [uv](https://docs.astral.sh/uv/) and pinned in `uv.lock`, so every machine and container installs the same versions.
* Setup scripts for Windows and Unix are included. Running `setup.bat` or `setup.sh` installs the dependencies and creates the initial `.env` file in a single step.
* Tests, linting, and formatting run in CI on every push to `main` and on every pull request, through the shared [dev-standards](https://github.com/Lempki/dev-standards) workflow.

## Music

The `media` cog plays music in voice channels through api-media, which downloads each song with yt-dlp, so YouTube cannot cut a song off partway.

### Playing

* `/play` takes a link or words to search for, on YouTube or, with its `source` option, on SoundCloud, and suggests search results while you type.
* Its reply links the track it found and names its source and its place in the queue, with an estimate of when it plays.
* Its `when` option plays the song next or now. Now puts the interrupted song right after it, and a playlist sends only its first track ahead, so the waiting songs keep their place.
* Each track of a playlist or album waits in the queue on its own. A Spotify album starts at once, because each track finds its YouTube match when its turn comes.
* Since February 2026, Spotify shares the tracks of a playlist only with its owners and collaborators, so `/play` explains that it cannot read most Spotify playlists. Albums and songs still work.

### The now-playing panel

* Every song shows on a panel in the channel where it was requested: the song, its artist and album when the site names them, the playlist or album it came from, who added it, a progress bar that moves every 10 seconds, the next songs, and who last changed the music, by a button or a command.
* Its buttons shuffle, go back, pause, skip, repeat, and stop. Only members in the bot's voice channel can press those, and Stop asks the presser privately before it removes waiting songs.
* Its other buttons show anyone the queue or the lyrics privately, and 📩 sends the presser the playing song with its artist, album, and length in a direct message, or privately in the channel when their direct messages are closed.
* The panel moves to the bottom of the chat when a new song starts after others wrote.
* When the music ends, or when the bot restarts while music plays, the panel keeps the last song without buttons. A stopped panel says so, with who stopped the song and where, how many waiting songs the stop removed, and when.
* After several songs, the finished panel sums the session up instead: how many songs played and for how long, who added them, the album or playlist that most came from, and the last song. Its Played songs button shows anyone the session's songs privately, a page at a time, and each server keeps the lists of its last 20 sessions.
* While a song plays, the voice channel's status shows it.

### The queue

* The queue holds at most 500 waiting songs, which `MAX_QUEUE_LENGTH` in `.env` changes. A playlist that does not fit adds the songs that fit and says how many were left out.
* `/queue show` shows you the whole queue a page at a time, and `/queue remove`, `move`, `shuffle`, `clear`, and `skipto` change it by the numbers it shows.
* With `/admin fairqueue`, the queue takes turns between the members who add songs, so one member's long album no longer holds everyone else's songs back. `/play`'s `when` option still jumps the line, and repeating the whole queue keeps the order it played in.
* With `/admin leavecleanup`, a member who leaves voice for two minutes takes their waiting songs out of the queue with them.
* The queue survives a restart, such as a nightly update. When the bot is back within 30 minutes and someone still waits in the voice channel, it rejoins and plays the song that was playing from where it was, then the rest of the queue.

### Controls

* `/music skip` skips the song, or votes to skip it, `/music previous` goes back to the song before, `/music loop` repeats the current song or the whole queue, and `/music pause` and `/music stop` pause and stop.
* `/music seek` jumps to a point in the playing song, such as `1:30`. A late point in a long mix takes a moment, because the song's audio is read from its start again. Anyone may move around in their own song, while another member's song needs the same control as stopping it.
* `/music volume` sets the server's music volume, which stays after restarts, and `/music lyrics` shows you a song's lyrics from LRCLIB.
* An admin can pick a DJ role with `/admin djrole`. While others listen, only members with that role, admins, and a lone listener can then stop, clear, shuffle, repeat, change the volume, skip to a song, play something now, or change other members' songs. Anyone can still add songs, pause, go back, and change their own songs.
* With a DJ role, a skip of someone else's song needs votes from half of the listeners, unless at most two listen. Without a DJ role, everyone controls the music.

### Sound

* Songs play at an even loudness, so the next song is about as loud as the last one, which `/admin loudness` turns off.
* The parts of a YouTube music video that SponsorBlock's community marks as not music, such as a skit before the song, are left out, and the panel counts the song's length without them.

## Commands

Commands are grouped by feature, so each name says what it acts on, and Discord's `/` menu lists each group together.
`/help` explains the features in the bot's own words.

| Command | What it does |
|---|---|
| `/play` | Plays a link or search result, or adds it to the queue. |
| `/music pause`, `stop`, `skip`, `previous`, `seek`, `loop`, `volume`, `lyrics` | Controls the music that plays now. |
| `/queue show`, `remove`, `move`, `shuffle`, `clear`, `skipto` | Shows and changes the songs waiting in the queue. |
| `/voice join`, `leave`, `stop` | Brings the bot into a voice channel, sends it out, or stops what it plays. |
| `/warn`, `/timeout`, `/untimeout`, `/kick`, `/ban` | Moderates a member. A timeout lasts from 60 seconds to a week, as Discord's own menu offers. |
| `/purge` | Deletes up to 100 recent messages in the channel, optionally only one member's. Discord deletes only messages younger than 14 days this way. |
| Right-click a member, then **Apps**, then **Warn** | Warns the member after asking for a reason. |
| Right-click a message, then **Apps**, then **Report to moderators** | Sends the message privately to the moderators' AutoMod alert channel. Anyone can use it, once a minute. |
| `/warnings list`, `remove`, `clear` | Shows and removes the warnings of members. |
| `/admin …` | Sets the bot up for the server, including AutoMod under `/admin automod`. |
| `/info server`, `member`, `avatar` | Shows the server's age, size, and boosts, a member's join date and roles, or an avatar in full size, only to you. |
| `/help`, `/about` | Shows a short guide to the bot, and its version and response time. |
| `/example hello` | The template cog's example command, the starting point for new features. |

## Prerequisites

The setup scripts under [Setup](#setup) install uv and offer Docker and FFmpeg, so these steps are only needed for a manual setup.

* Python 3.14, which uv installs when it is missing.
* [Docker](https://docs.docker.com/get-started/get-docker/), for running the bot in containers, which is how a downloaded release runs.
* [uv](https://docs.astral.sh/uv/). On Windows, run `winget install --id astral-sh.uv`. On macOS or Linux, follow the uv installation guide.
* [FFmpeg](https://ffmpeg.org/) on your system PATH, for running the bot without Docker. You may alternatively define a custom path using the `FFMPEG_PATH` environment variable.

  * On Windows, install FFmpeg with the following command:

    ```
    winget install ffmpeg
    ```

  * On macOS, install FFmpeg with the following command:

    ```
    brew install ffmpeg
    ```

  * On Debian or Ubuntu, install FFmpeg with the following command:

    ```
    sudo apt install ffmpeg
    ```

## Privileged intents

The bot asks Discord for one privileged intent, and only when `COGS_TO_LOAD` includes `events`.
Then enable it in your application's **Bot** page in the [Discord Developer Portal](https://discord.com/developers/applications) under **Privileged Gateway Intents** before starting the bot.
Without `events`, leave it disabled. A verified bot needs Discord's approval for every privileged intent it asks for, so asking only for what it uses keeps verification simple.

| Intent | Portal label | Required for |
|---|---|---|
| `members` | Server Members Intent | The `events` cog's `on_member_join` events, which give new members the auto-role and post the welcome message, and its `on_member_remove` events, which post the goodbye message. |

Turn the intent off in the portal only after the bot runs a version that no longer asks for it, or the bot cannot connect until you turn it back on.

The **Presence Intent** and the **Message Content Intent** are not used and should stay disabled.
Discord gives a bot the text of a message that mentions it without the Message Content Intent, which is all that the reply to a mention needs.
The bot turns off the direct messages intent, so Discord never sends it the text of a direct message. Slash commands and buttons still work in direct messages, because they are interactions.
AutoMod reads messages on Discord's side, so the bot never needs message content.
The bot also uses the Auto Moderation Execution intent, which is not privileged and needs no portal setting.

## Bot permissions

Use the **OAuth2 → URL Generator** in the Developer Portal to build the invite URL. Select both `bot` and `applications.commands` as the OAuth2 scopes, then select the required permissions from the list that appears below the scope selector.

The **Requires OAuth2 Code Grant** toggle in the Bot page is not applicable to standard bot invites and should remain disabled.

| Permission | Required for |
|---|---|
| View Channels | Reading channel state. |
| Send Messages | Posting the welcome and goodbye messages, media track updates, and AutoMod reports. |
| Embed Links | The now-playing panel, session summaries, and moderator reports, which are embeds. Without it, Discord strips them. |
| Connect | Joining voice channels. |
| Speak | Playing audio in voice channels. |
| Set Voice Channel Status | Showing the playing song under the voice channel's name. Without it, the song still plays. |
| Manage Roles | Auto-role assignment on member join. |
| Kick Members | `/kick` and the `kick` warning action. |
| Ban Members | `/ban` and the `ban` warning action. It also tells a ban from leaving, so that a banned member gets no goodbye. |
| Moderate Members | `/timeout`, `/untimeout`, and the `timeout` warning action. |
| Manage Messages | Deleting messages with `/purge`. |
| Read Message History | `/purge`, which reads the channel's recent messages to find the ones to delete, and replying to a mention. Without it, the bot answers a mention in the channel instead. |
| Manage Server | Managing AutoMod rules and receiving AutoMod executions. |

None of the core cogs send files. Add **Attach Files** if one of your own cogs does.
Discord's role settings call Moderate Members **Timeout Members**.

## Moderation and AutoMod

Discord's own AutoMod does the filtering, so blocked messages never reach the channel.
The bot manages its rules through the API and never reads message content.

* `/admin automod add` and `/admin automod remove` edit the bot's keyword rule. Keywords are separated by commas, and `*` works as a wildcard.
* `/admin automod list` shows the keywords, up to Discord's limit of 1000.
* `/admin automod preset` turns Discord's word lists for profanity, sexual content, and slurs on or off.
* `/admin automod alert` sets the channel where AutoMod posts alerts and the bot posts warning reports.
* `/admin automod escalation` decides whether each blocked message also adds a warning. A member gets at most one AutoMod warning in 10 seconds.
* `/admin warnaction` and `/admin warnthreshold` decide what happens at the warning limit: a kick, a ban, or a timeout. `/admin warntimeout` sets the timeout length.

The bot only changes rules it created itself.
Rules made in **Server Settings > AutoMod** stay untouched, but their blocked messages also count as warnings when escalation is on.
An admin can also add a timeout or an allow list to the bot's rules there, and the bot keeps them.

Two features need no bot code.
Discord's audit log already records every kick, ban, and timeout with the reason the bot passes.
**Server Settings > Integrations** lets admins choose which roles may use each command.

## Setup

The setup script prepares the project in a single run, and it is safe to run again at any time.

On Windows, double-click `setup.bat` or run it from a terminal:

```
setup.bat
```

On macOS or Linux, run the following commands:

```
chmod +x setup.sh
./setup.sh
```

The script asks before it installs or starts anything, and it does the following:

1. It installs [uv](https://docs.astral.sh/uv/) when uv is missing. uv also provides Python 3.14 when the machine lacks it.
2. It offers to install Docker, and in a Git clone also the tools that the Docker image includes for running outside Docker, such as FFmpeg. It uses winget on Windows, Homebrew on macOS, and the system package manager on Linux. On Windows it also turns on WSL, which Docker Desktop needs, and says when Windows needs a restart or virtualization is turned off in the firmware. It shows the computer's RAM and offers to cap the memory of Docker Desktop's virtual machine, at a suggested or your own size.
3. In a Git clone, it runs `uv sync`, which installs the locked dependencies into `.venv`.
4. It copies `.env.template` to `.env` on the first run and asks for the bot token, which it reads without showing it. When `LOCALE` is not set, it explains that the default mutes public replies and asks for the bot's language.
5. It prepares `compose.stack.yml`. It fills each API secret that the stack needs and reuses the service's own `API_SECRET` when that service is already set up. A downloaded release runs the images that GitHub publishes, so it needs no other repository. In a Git clone, when an api-* repository that the stack builds is missing, it looks for a downloaded release of it, also inside the extra folder that Windows' Extract All creates, and moves it into place. Otherwise it clones the repository. It then starts Docker Desktop when it is not running, and offers to start the bot and its services in Docker.
6. In a downloaded release, it offers to install new releases automatically every night.

A step that fails says what went wrong, why it matters, and what to do next, and the summary at the end lists it again.
The steps live in `scripts/bootstrap.py`, which needs only the Python standard library.

If you prefer to perform the setup manually, follow these steps:

```bash
git clone https://github.com/Lempki/discord-bot-template.git my-bot
cd my-bot
uv sync
cp .env.template .env
# Edit .env and set DISCORD_TOKEN and other values as needed.
uv run python bot.py
```

### Running

After setup has run once, the run script starts the bot.
Double-click `run.bat` on Windows, or run `./run.sh` on macOS and Linux.
It starts the bot and the api-* services in `compose.stack.yml` in Docker in the background.
It then waits until every service is ready and shows their status.
The containers then start again whenever Docker starts.

The script also takes an action, such as `run.bat stop` on Windows or `./run.sh stop` elsewhere:

| Action | What it does |
|---|---|
| `start` | Starts everything in Docker and waits until it is ready. It is the default. |
| `stop` | Stops the containers. They stay stopped until the next start. |
| `status` | Shows whether each container runs and is healthy, its version, and whether updates are automatic. |
| `logs` | Follows the logs. Press Ctrl+C to stop following. |
| `update` | Installs the newest release. In a Git clone, it pulls the latest code, rebuilds on fresh base images, and restarts, then deletes the build cache that no build used for a week. |
| `schedule` | Installs new releases automatically every night at 04:00. |
| `unschedule` | Stops installing new releases automatically. |
| `backup` | Copies the bot's database into the `backups` folder, and into `BACKUP_COPY_FOLDER` when it is set. The update of a downloaded release does it too. |
| `restore` | Puts a backup of the bot's database back. It asks which one and backs up the current database first. |
| `local` | Runs the project in the terminal without Docker. Press Ctrl+C to stop it. |

When a service crashes right after it starts, the script shows the end of its log and stops it, so it does not restart over and over.
In a Git clone, the `update` action also pulls the api-* repositories that the stack builds.
The `local` action runs only the bot, which reaches its services at the URLs in `.env`.

### Updates

A downloaded release runs the Docker images that GitHub publishes for every release, such as `ghcr.io/lempki/api-media`.
A Git clone builds the images from its own files instead.

In a downloaded release, the `update` action takes these steps:

1. It backs up the bot's database, as the `backup` action does.
2. It downloads the newest image of the bot and of each service in `compose.stack.yml`.
3. When the bot's image is new, it replaces the run, setup, and compose files with the ones from the new release. `.env` and the other settings stay as they are.
4. It restarts everything and waits until every service is ready.
5. When the new release fails to start, it puts the previous images and files back and starts them again. Later updates skip that release until a newer one appears.
6. It deletes the images that nothing uses anymore, such as the versions that the new release replaced.

The `schedule` action runs this update every night at 04:00.
On Windows it adds a task to the Task Scheduler, which runs as soon as the computer is on again when it was off or asleep at that time.
On macOS and Linux it adds a line to your crontab.
Each scheduled update writes what it did into `update.log` in the project folder. With `UPDATE_WEBHOOK_URL` in `.env` set to a Discord webhook, an update that installs a new release or fails also posts a short message to that webhook's channel, naming the new versions or the problem. A night without a new release posts nothing. To get a webhook, open a channel's settings in Discord, choose Integrations, then Webhooks, then New Webhook, and copy its URL.

A private image needs a GitHub sign-in.
The first download asks for a [token with the `read:packages` scope](https://github.com/settings/tokens/new?scopes=read:packages&description=Docker+updates), which Docker then remembers.

### Backups

The bot keeps its settings and moderation warnings in a SQLite database on a Docker volume.
The update of a downloaded release copies it into the `backups` folder first, and the `backup` action does the same at any time.
The folder keeps the last 7 copies, named after the time they were taken, such as `bot-2026-10-11-040000.db`.

The `backups` folder sits on the same disk as the database, so a broken disk or a lost computer would take both.
Set `BACKUP_COPY_FOLDER` in `.env` to a folder that syncs to the cloud, such as one in OneDrive or Google Drive, and each backup is copied there as well, into a subfolder named after the bot.
That folder keeps the last 7 copies too, so several bots can share it.
A copy that fails leaves the backup in place, and the update's Discord message names the problem.

The `restore` action lists the copies in both folders and asks which one to put back.
It backs up the current database before it replaces it, so a restore can be undone with another restore.
To move the bot to another computer, copy the `backups` folder along with `.env` and run `restore` there.
With `BACKUP_COPY_FOLDER` set in the copied `.env`, the new computer finds the copies in that folder, so the `backups` folder can stay behind.

### Offline alerts

A heartbeat service can tell you when the bot goes offline, whether it crashed, lost its connection, or the computer shut down.
The bot reports to the service every 5 minutes while it is connected to Discord.
When the reports stop, the service sends you an email or a Discord message.
These steps use [healthchecks.io](https://healthchecks.io), which is free for a few bots.

1. Sign up at healthchecks.io and open your project.
2. Click **Add Check**. Name it after the bot, set **Period** to 5 minutes and **Grace Time** to 10 minutes, and save.
3. Copy the check's ping URL, such as `https://hc-ping.com/1f2e3d4c-...`. It works like a password, so keep it private.
4. Add it to `.env` as `HEARTBEAT_URL=` followed by the URL.
5. Run `run.bat` on Windows or `./run.sh` elsewhere, so the bot restarts with the setting.
6. On healthchecks.io, open **Integrations** to add a Discord channel or other ways to be told, next to the email that is on by default.

The check turns green within 5 minutes.
The service also alerts while the computer sleeps, because the bot is offline then too.

### Health check

While the bot is connected to Discord, it refreshes a small file every 30 seconds, and the Docker image's health check reads its age.
A bot that is stuck or lost its connection therefore shows as unhealthy in `run.bat status` and in Docker Desktop, not only one that crashed.
A new release that starts but never connects fails the update's check, so the update puts the previous version back.

### Development

Run the tests with `uv run pytest`.
Run every lint and format check with `uvx pre-commit run --all-files`, or install the hooks once with `uvx pre-commit install` so they run on each commit.
The coding, prose, and commit conventions are documented in [dev-standards](https://github.com/Lempki/dev-standards).

### Docker

Alternatively, you can run the bot as a Docker container.

1. Copy `.env.template` to `.env` and set `DISCORD_TOKEN`.
2. Build and start the container:

   ```
   docker compose up -d --build
   ```

The container restarts automatically unless you stop it.
The database lives on the `bot-data` volume, so settings and warnings survive rebuilds and `docker compose down`.
Only `docker compose down -v` deletes it.

To run the bot together with the api-* services it uses, clone those repositories next to this one and use the stack file instead:

```
docker compose -f compose.stack.yml up -d --build
```

The stack builds each service from its sibling folder and connects them on a private network.
It also names each service's published image, which a downloaded release runs instead of building it.
It passes `API_MEDIA_SECRET` from this repository's `.env` to the media service, so the two always agree.

api-media reads its own settings, such as `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPONSORBLOCK`, and `YDL_COOKIES_FILE`, from an optional `api-media.env` next to the stack file.
A Git clone can keep them in `../api-media/.env` instead, and `api-media.env` wins where both set the same setting.
Neither file is needed unless you change one of api-media's defaults, and api-media's README lists every setting.
For a YouTube cookies file, put it in a `cookies` folder next to the stack file, set `MEDIA_COOKIES_DIR=./cookies` in `.env`, and set `YDL_COOKIES_FILE=cookies/youtube.txt` in `api-media.env`.

Docker keeps at most two log files of 5 MB per container and overwrites the oldest.
The bot's container may use at most 512 MB of memory, and each api-* service in the stack 1 GB.
That is several times their normal use, so only a leak reaches it, and the container that leaks restarts on its own.

## Configuration

All configuration is read from environment variables or from a `.env` file located in the project root directory.

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_TOKEN` | Yes | None | The Discord bot token used to authenticate with the API. |
| `COGS_TO_LOAD` | No | `help` | A comma-separated list of cog module names to load at startup. Set it to `help,template,voice,media,info,admin,moderation,events` for the full feature set. |
| `LOCALE` | No | `silent` | The fallback language for users whose Discord language the bot does not speak. Built-in values are `en` and `fi`. `silent` mutes public replies to commands. Private replies, such as `/help`, admin and moderator replies, and error messages, are still sent because only the person who ran the command sees them. The music panel, the welcome, and the goodbye are not replies, so they post as well. |
| `DATABASE_PATH` | No | `data/bot.db` | The SQLite file for per-guild settings and moderation data. The directory is created if needed. The Docker image uses `/app/data/bot.db`. |
| `FFMPEG_PATH` | No | `ffmpeg` | The FFmpeg executable. Leave it unset to use FFmpeg from the system PATH. |
| `DEV_GUILD_ID` | No | None | A server ID for development. Commands sync to that server instantly instead of globally. |
| `HEARTBEAT_URL` | No | None | The ping URL of a heartbeat service, such as healthchecks.io, which alerts you when the bot stops reporting that it is online. See [Offline alerts](#offline-alerts). |
| `MEDIA_COOKIES_DIR` | No | `../api-media/cookies` | The folder that the stack mounts as api-media's `cookies` folder, for a YouTube cookies file. A downloaded release uses `./cookies`. |
| `MAX_QUEUE_LENGTH` | No | `500` | How many songs may wait in a server's music queue. A playlist that does not fit adds the songs that fit. |
| `BACKUP_COPY_FOLDER` | No | None | A folder that receives a copy of each backup, such as one that syncs to the cloud. See [Backups](#backups). |
| `UPDATE_WEBHOOK_URL` | No | None | A Discord webhook that hears when a nightly update installs a new release or fails. See [Updates](#updates). It works like a password. |
| `API_<NAME>_URL` | No | None | The base URL of an api-* service, for example `API_MEDIA_URL`. |
| `API_<NAME>_SECRET` | No | None | The bearer token of that service. It must match `API_SECRET` in the service's own configuration. |

A cog that needs a service asks for it by name. If the URL or the secret is missing, the bot stops at startup with an error that names both variables.
The `media` cog needs `API_MEDIA_URL` and `API_MEDIA_SECRET`.

Commands are synced to Discord once each time the bot starts.
With `DEV_GUILD_ID` set, they appear in that server immediately.
Commands synced globally earlier stay visible there as well, so a development server may show each command twice until the global ones are removed.

## Project structure

```
discord-bot-template/
├── bot.py                  # Entry point.
├── config.py               # Reads settings and api-* service URLs from the environment.
├── localization.py         # This bot's own messages and translations, layered on the core ones.
├── cogs/
│   ├── help.py             # /help, a short guide to the bot's features, and /about.
│   ├── template.py         # Template cog. Use this as a starting point for new features.
│   ├── voice.py            # /voice join, leave, and stop. The bot leaves on its own when alone or idle.
│   ├── media.py            # /play, /music, and /queue, with a per-server queue and the now-playing panel.
│   ├── info.py             # /info server, member, and avatar.
│   ├── admin.py            # /admin command group, including /admin automod.
│   ├── moderation.py       # /warn, /warnings, /timeout, /untimeout, /kick, /ban, /purge, the right-click Warn and Report, and AutoMod escalation.
│   └── events.py           # The auto-role and welcome message on join, and the goodbye message on leave.
├── utils/
│   ├── audio.py            # MediaAPIClient, URL helpers, and audio sources for files, bytes, and streams.
│   ├── about.py            # Reads the bot's name, version, and repository link from pyproject.toml.
│   ├── automod.py          # Creates and edits the AutoMod rules that the bot owns.
│   ├── checks.py           # Command checks such as in_bot_channel(), and guild_of().
│   ├── database.py         # Versioned SQLite schema, per-guild settings, and warnings.
│   ├── heartbeat.py        # Reports to a heartbeat service while the bot is online.
│   ├── i18n.py             # Picks each user's language and translates command descriptions.
│   ├── moderation.py       # issue_warning(), shared by /warn and AutoMod escalation.
│   ├── replies.py          # respond() and finish(), which never leave a command "thinking".
│   ├── strings.py          # Every core message and command translation, in English and Finnish.
│   └── voice.py            # Joins, plays in, and leaves voice channels for every cog.
├── assets/
│   ├── audio/              # Audio files.
│   ├── images/             # Image files.
│   └── videos/             # Video files.
├── tests/                  # Pytest suite, including the setup and run scripts' tests.
├── .env.template           # Template for environment variables.
├── .template-manifest.toml # Core files that derived bots keep identical to this template.
├── pyproject.toml          # Project metadata and dependencies.
├── uv.lock                 # Locked dependency versions.
├── ruff.toml               # Lint and format settings on top of the shared baseline.
├── setup.bat               # Windows setup script.
├── setup.sh                # macOS and Linux setup script.
├── scripts/
│   ├── bootstrap.py        # The steps that both setup scripts run.
│   └── run.py              # The actions that both run scripts take.
├── run.bat                 # Windows run script.
├── run.sh                  # macOS and Linux run script.
├── Dockerfile
├── docker-compose.yml      # Runs the bot alone, with its database on a volume.
├── compose.stack.yml       # Runs the bot together with the api-* services it uses.
├── .dockerignore
└── .github/                # CI and release workflows, Dependabot, and the Idea issue form.
```

## Adding a new cog

1. Copy `cogs/template.py` to a new file such as `cogs/my_feature.py`.
2. Rename the class, the cog's name, and the command group, such as `/example`, so the copy does not clash with the template cog.
3. Implement your commands or event listeners. Add every message to `Strings` in `localization.py` with text in every language, and a `guide_<cog>` text that `/help` shows.
4. Add each command and option description, exactly as written in English, to `BOT_COMMAND_TEXT` in `localization.py`, with its translation in every other language.
5. Add the module name to the `COGS_TO_LOAD` variable in your `.env` file.
6. Run `uv run pytest`, which fails while a language misses a message or a translation.

## Localization

Replies follow the Discord language of the user who ran the command.
A user whose language the bot does not speak gets the `LOCALE` language, and English after that.
With the default `LOCALE=silent`, public replies to commands stay muted for everyone, so set `LOCALE` to turn them on.
The music panel, the welcome, and the goodbye post in the server's preferred language either way.
Messages without an interaction, such as the join welcome and the goodbye, use the server's preferred language.

Command descriptions, option descriptions, and choice names are localized natively, so each user's Discord client shows them in their own language.
Command and option names always stay English, so everyone types the same commands.

The core cogs' messages and command translations live in `utils/strings.py`, in English and Finnish.
A bot adds its own messages in `localization.py`, and it may override any core text to give itself a personality.
To add a language, add its Discord locale code, such as `de` or `sv-SE`, to `BOT_TEXT` and `BOT_COMMAND_TEXT` in `localization.py`.
The core texts exist only in English and Finnish, so a new language also needs every core message in `BOT_TEXT` and every core command text in `BOT_COMMAND_TEXT`.

The tests list every message or command text a language is missing, and they fail on command texts longer than Discord's 100-character limit.

## API services

The media cog plays music through a separate HTTP API service, which `API_MEDIA_URL` and `API_MEDIA_SECRET` point to.
Its client, `MediaAPIClient` in `utils/audio.py`, shows the endpoints that the cog calls, so a service of your own can implement them, starting from [api-template](https://github.com/Lempki/api-template).
A cog of your own reads any such service the same way, with `bot.config.service("<name>")`.

## Making a bot from this template

Use the GitHub template button to create a new repository based on this project.

The template includes generic cogs, in English and Finnish, that can be modified or replaced. A typical customization workflow includes the following steps:

* Add new bot-specific cogs in the `cogs/` directory.
* Connect a new api-* service by setting `API_<NAME>_URL` and `API_<NAME>_SECRET`, then read it in a cog with `bot.config.service("<name>")`. No change to `config.py` is needed.
* Add the bot's own messages to `Strings` and `BOT_TEXT` in `localization.py`, and set the fallback `LOCALE` in your `.env` file.
* Add audio files to `assets/audio/`, images to `assets/images/`, and videos to `assets/videos/`. Keep each file under 1 MB, because a pre-commit hook rejects larger ones.
* Send images and videos to Discord as `discord.File` attachments. `utils/audio.py` and `VoicePresence.play()` are audio-only and are not used for other asset types.
* Replace or remove `cogs/template.py` once it is no longer needed.

A bot made from the template keeps no Git link to it.
Instead, `.template-manifest.toml` lists the core files that every bot keeps identical to the template.
With both repositories cloned side by side, run this from the bot's directory to see which core files have drifted:

```bash
uvx --from git+https://github.com/Lempki/dev-standards@v0.5.0 dev-standards template-check --template ../discord-bot-template --diff
```

Add `--apply` to copy the template's version over every drifted file, then review the result with `git diff` before committing.
Keep bot-specific changes in files outside the manifest, such as `localization.py`, `compose.stack.yml`, and the bot's own cogs.

## License

This project is licensed under the [MIT License](LICENSE).
You may use, change, and share it, as long as every copy keeps the copyright notice and the license text.
