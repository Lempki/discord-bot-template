"""Messages used by the core cogs, in every language the template ships.

Each bot's localization.py extends CoreStrings with its own messages and can override any core text.
Placeholders in braces are filled with str.format().
An empty string means the bot sends nothing for that event.
"""

from dataclasses import dataclass

__all__ = ["CORE_COMMAND_TEXT", "CORE_TEXT", "CoreStrings"]


@dataclass(frozen=True)
class CoreStrings:
    """Every user-facing message the core cogs send. All fields default to silence."""

    # General.
    bot_channel_only: str = ""
    command_failed: str = ""
    # The placeholder of cooldown is {seconds}, the wait before the command works again.
    cooldown: str = ""
    command_unavailable: str = ""
    # The template cog's example command.
    example_hello: str = ""

    # Voice. Placeholders are {user} and {channel}.
    # A reply leaves out {user}, because Discord shows who ran the command above it.
    not_in_voice: str = ""
    bot_not_in_voice: str = ""
    already_same_channel: str = ""
    joined_voice: str = ""
    moved_voice: str = ""
    left_voice: str = ""
    skipped: str = ""
    nothing_playing: str = ""

    # Media. Placeholders are {user}, {count}, {title}, {channel}, {position}, {source}, {minutes}.
    # {source} names the site, such as YouTube, and {minutes} is the wait.
    # Replies to /play leave out {user}, as above.
    # The player's own lines name who added the track, without a ping.
    queued_now: str = ""
    queued_one: str = ""
    queued_one_wait: str = ""
    queued_many: str = ""
    # queued_many_now also uses {more}, the tracks added after the one that starts.
    queued_many_now: str = ""
    # A playlist with when=Next. {position} is where the rest of its tracks start.
    queued_many_next: str = ""
    # The queue's limit. Placeholders are {limit} and {left}, the tracks that did not fit.
    queue_full: str = ""
    queue_cut: str = ""
    # A Spotify playlist whose songs Spotify does not share with the bot.
    playlist_unavailable: str = ""
    # The DJ role and vote skipping. Placeholders are {votes} and {needed}.
    dj_only: str = ""
    skip_voted: str = ""
    skip_already_voted: str = ""
    # A playlist's or album's name with its site, which fills {source}.
    # The placeholders are {collection} and {source}.
    collection_on: str = ""
    load_error: str = ""
    play_failed: str = ""
    stopped: str = ""
    paused: str = ""
    resumed: str = ""
    # /queue. Placeholders are {title}, {position}, {user}, {page}, {pages}, {count}, and {length}.
    queue_empty: str = ""
    queue_title: str = ""
    queue_now_playing: str = ""
    queue_next: str = ""
    queue_line: str = ""
    queue_footer: str = ""
    # Queue control. Placeholders are {title}, {position}, and {count}.
    queue_removed: str = ""
    queue_moved: str = ""
    queue_shuffled: str = ""
    queue_cleared: str = ""
    queue_skipping_to: str = ""
    queue_no_position: str = ""
    queue_nothing_waiting: str = ""
    # Volume. The placeholder is {volume}, in percent.
    volume_now: str = ""
    volume_set: str = ""
    # History and repeat. The placeholder is {title}.
    previous_playing: str = ""
    previous_none: str = ""
    loop_off: str = ""
    loop_track: str = ""
    loop_queue: str = ""
    # /music lyrics. The placeholder is {title}.
    lyrics_nothing: str = ""
    lyrics_none: str = ""
    lyrics_unavailable: str = ""
    lyrics_footer: str = ""
    # The now-playing panel. Placeholders are {source}, {user}, {count}, {loop}, and {volume}.
    # An empty panel_playing posts no panel.
    panel_playing: str = ""
    panel_paused: str = ""
    panel_ended: str = ""
    panel_details: str = ""
    panel_next: str = ""
    panel_next_none: str = ""
    panel_more: str = ""
    panel_footer: str = ""
    panel_loop_off: str = ""
    panel_loop_track: str = ""
    panel_loop_queue: str = ""
    panel_stop: str = ""
    panel_queue: str = ""
    panel_lyrics: str = ""
    panel_not_listening: str = ""
    # The summary of a finished session.
    # Placeholders are {count}, {length}, {hours}, {minutes}, {users}, and {source}.
    # The names_ texts join names with {first}, {second}, and {last}, and session_last uses {title}.
    session_title: str = ""
    session_hours: str = ""
    session_minutes: str = ""
    session_added_by: str = ""
    session_mostly: str = ""
    session_last: str = ""
    names_two: str = ""
    names_last: str = ""
    names_others: str = ""
    panel_played: str = ""
    played_title: str = ""
    played_gone: str = ""
    # The question that the stop button asks while songs wait. The placeholder is {count}.
    stop_confirm: str = ""
    stop_confirm_yes: str = ""
    stop_confirm_no: str = ""
    stop_kept: str = ""
    # The panel's line about who last changed the music, by a button or a command.
    # Placeholders are {user}, {title}, {loop}, and {volume}.
    action_skipped: str = ""
    action_skipto: str = ""
    action_previous: str = ""
    action_now: str = ""
    action_paused: str = ""
    action_resumed: str = ""
    action_loop: str = ""
    action_shuffled: str = ""
    action_cleared: str = ""
    action_volume: str = ""
    action_stopped: str = ""
    action_skipvote: str = ""
    action_skipped_vote: str = ""

    # Help. A section_<cog> field names the section of that cog.
    # A cog without a section field falls back to its own name.
    # A guide_<cog> field explains that feature, and a cog without one lists its commands.
    # help_commands uses {commands}, and help_bot_channel uses {channel}.
    help_title: str = ""
    help_intro: str = ""
    help_commands: str = ""
    help_bot_channel: str = ""
    guide_media: str = ""
    guide_voice: str = ""
    guide_moderation: str = ""
    guide_admin: str = ""
    guide_template: str = ""
    guide_help: str = ""
    guide_info: str = ""
    section_info: str = ""
    # /info. info_channel_counts uses {text} and {voice}, info_boost_level {level} and {count}.
    # info_more uses {count}, and info_avatar_title {user}.
    info_created: str = ""
    info_owner: str = ""
    info_members: str = ""
    info_channels: str = ""
    info_channel_counts: str = ""
    info_roles: str = ""
    info_boosts: str = ""
    info_boost_level: str = ""
    info_account_created: str = ""
    info_joined: str = ""
    info_boosting: str = ""
    info_more: str = ""
    info_avatar_title: str = ""
    # The placeholders of about_text are {name}, {version}, {since}, {latency}, and {servers}.
    # {since} is a Discord timestamp, which each reader's app shows in their own language.
    about_text: str = ""
    about_link: str = ""
    help_footer: str = ""
    # The bot's status, which is the same in every server and so names no song.
    status_idle: str = ""
    status_playing: str = ""
    help_empty: str = ""
    section_admin: str = ""
    section_help: str = ""
    section_media: str = ""
    section_moderation: str = ""
    section_template: str = ""
    section_voice: str = ""

    # Admin. Placeholders are {channel}, {role}, {count}, {action}, {autorole}, and {threshold}.
    # admin_timeout_set uses {minutes}.
    # admin_status also uses {timeout}, {escalation}, {alert}, {keywords}, and {presets}.
    admin_channel_set: str = ""
    admin_channel_cleared: str = ""
    admin_autorole_set: str = ""
    admin_autorole_cleared: str = ""
    admin_dj_set: str = ""
    admin_dj_cleared: str = ""
    admin_threshold_set: str = ""
    admin_action_set: str = ""
    admin_timeout_set: str = ""
    admin_status: str = ""
    status_any_channel: str = ""
    status_none: str = ""
    status_unavailable: str = ""
    action_kick: str = ""
    action_ban: str = ""
    action_timeout: str = ""

    # AutoMod. Placeholders are {keywords}, {length}, {limit}, {count}, {preset}, and {channel}.
    # automod_warned uses {user}, {count}, and {threshold}.
    automod_keywords_invalid: str = ""
    automod_keywords_limit: str = ""
    automod_keywords_saved: str = ""
    automod_keywords_none: str = ""
    automod_keywords_header: str = ""
    automod_preset_on: str = ""
    automod_preset_off: str = ""
    automod_alert_set: str = ""
    automod_alert_cleared: str = ""
    automod_escalation_warn: str = ""
    automod_escalation_none: str = ""
    automod_no_permission: str = ""
    automod_failed: str = ""
    automod_warned: str = ""
    escalation_warn: str = ""
    escalation_none: str = ""
    preset_profanity: str = ""
    preset_sexual_content: str = ""
    preset_slurs: str = ""

    # Moderation. The placeholders are {user}, {count}, {threshold}, {minutes}, and {error}.
    # Warning lists also use {id}, {reason}, and {date}.
    warn_issued: str = ""
    warn_threshold_kick: str = ""
    warn_threshold_ban: str = ""
    warn_threshold_timeout: str = ""
    warnings_list_header: str = ""
    warnings_list_entry: str = ""
    warnings_no_reason: str = ""
    warnings_none: str = ""
    warnings_cleared: str = ""
    warning_removed: str = ""
    warning_not_found: str = ""
    kick_success: str = ""
    kick_failed: str = ""
    ban_success: str = ""
    ban_failed: str = ""
    timeout_failed: str = ""
    # /timeout and /untimeout use {user}, {until}, and {error}. /purge uses {count} and {error}.
    timeout_success: str = ""
    untimeout_success: str = ""
    untimeout_none: str = ""
    untimeout_failed: str = ""
    purge_done: str = ""
    purge_none: str = ""
    purge_failed: str = ""
    # The right-click Warn and Report. warn_modal_title uses {user}.
    warn_modal_title: str = ""
    warn_modal_reason: str = ""
    report_no_channel: str = ""
    report_sent: str = ""
    report_failed: str = ""
    report_title: str = ""
    report_no_text: str = ""
    report_author: str = ""
    report_channel: str = ""
    report_by: str = ""
    report_files: str = ""
    mod_target_self: str = ""
    mod_target_protected: str = ""
    mod_target_higher: str = ""
    mod_bot_too_low: str = ""

    # Events. The placeholder is {member}.
    member_join_welcome: str = ""


CORE_TEXT: dict[str, dict[str, str]] = {
    "en": {
        "bot_channel_only": "This command can only be used in the bot channel.",
        "command_failed": "Something went wrong. Try again later.",
        "cooldown": "Slow down a little. Try again in {seconds} s.",
        "command_unavailable": "This command is no longer available. Discord removes it from the menu shortly.",
        "example_hello": "Hello! This command comes from the template cog, the starting point for new features.",
        "not_in_voice": "You are not in a voice channel.",
        "bot_not_in_voice": "I am not in a voice channel.",
        "already_same_channel": "I am already in your voice channel.",
        "joined_voice": "Joined `{channel}`.",
        "moved_voice": "Moved to `{channel}`.",
        "left_voice": "Left `{channel}`.",
        "skipped": "Skipped.",
        "nothing_playing": "Nothing is playing.",
        "queued_now": "Playing **{title}** from {source}.",
        "queued_one": "Added **{title}** from {source} to the queue at #{position}.",
        "queued_one_wait": "Added **{title}** from {source} to the queue at #{position}. It plays in about {minutes} min.",
        "queued_many": "Added {count} tracks from {source} to the queue, starting at #{position}.",
        "queued_many_now": "Playing **{title}** from {source}, and added {more} more tracks to the queue.",
        "queued_many_next": "Added {count} tracks from {source}. **{title}** plays next, and the rest start at #{position}.",
        "queue_full": "The queue is full, because it holds at most {limit} songs. /queue clear or /queue remove makes room.",
        "queue_cut": "{left} tracks were left out, because the queue holds at most {limit} songs.",
        "playlist_unavailable": "Spotify does not let the bot read this playlist. Albums, single songs, and YouTube playlists still work.",
        "dj_only": "Only members with the DJ role can do that while others listen.",
        "skip_voted": "Your vote to skip counts: {votes} of {needed} needed.",
        "skip_already_voted": "You already voted to skip this song: {votes} of {needed} needed.",
        "collection_on": "{collection} on {source}",
        "load_error": "Could not load the audio. Try again.",
        "play_failed": "Could not play **{title}**, added by {user}. Moving on to the next track.",
        "stopped": "Stopped and cleared the queue.",
        "paused": "Paused.",
        "resumed": "Resumed.",
        "queue_empty": "Nothing is playing, and the queue is empty.",
        "queue_title": "Queue",
        "queue_now_playing": "**Now playing:** {title}",
        "queue_next": "**Up next:**",
        "queue_line": "`{position}.` {title} · {user}",
        "queue_footer": "Page {page} of {pages} · {count} tracks · {length}",
        "queue_removed": "Removed **{title}** from the queue.",
        "queue_moved": "Moved **{title}** to #{position}.",
        "queue_shuffled": "Shuffled {count} tracks.",
        "queue_cleared": "Removed {count} tracks from the queue. The current track keeps playing.",
        "queue_skipping_to": "Skipping to **{title}**.",
        "queue_no_position": "There is no track at #{position}. /queue show shows the numbers.",
        "queue_nothing_waiting": "No tracks are waiting in the queue.",
        "volume_now": "The volume is {volume}%.",
        "volume_set": "Volume set to {volume}%.",
        "previous_playing": "Going back to **{title}**.",
        "previous_none": "There is no earlier song to go back to.",
        "loop_off": "Repeat is off.",
        "loop_track": "Repeating the current song.",
        "loop_queue": "Repeating the whole queue.",
        "lyrics_nothing": "Nothing is playing. Name a song to look up.",
        "lyrics_none": "No lyrics were found for **{title}**.",
        "lyrics_unavailable": "The lyrics service could not be reached. Try again later.",
        "lyrics_footer": "Lyrics from LRCLIB",
        "status_idle": "/help shows the commands",
        "status_playing": "🎵 Playing music",
        "panel_playing": "Now playing",
        "panel_paused": "Paused",
        "panel_ended": "Finished playing",
        "panel_details": "From {source}, added by {user}",
        "panel_next": "Up next",
        "panel_next_none": "Nothing yet. /play adds more.",
        "panel_more": "…and {count} more",
        "panel_footer": "Repeat: {loop} · Volume: {volume}%",
        "panel_loop_off": "off",
        "panel_loop_track": "this song",
        "panel_loop_queue": "the whole queue",
        "panel_stop": "Stop",
        "panel_queue": "Queue",
        "panel_lyrics": "Lyrics",
        "panel_not_listening": "Join the bot's voice channel to control the music.",
        "session_title": "{count} songs · {length}",
        "session_hours": "{hours} h {minutes} min",
        "session_minutes": "{minutes} min",
        "session_added_by": "Added by {users}",
        "session_mostly": "Mostly from {source}",
        "session_last": "**Last song:** {title}",
        "names_two": "{first} and {second}",
        "names_last": ", and {last}",
        "names_others": "{count} others",
        "panel_played": "Played songs",
        "played_title": "Played songs",
        "played_gone": "This list is no longer kept. The bot keeps the songs of the last 20 sessions.",
        "stop_confirm": "This stops the music and removes the {count} waiting songs.",
        "stop_confirm_yes": "Stop and clear",
        "stop_confirm_no": "Cancel",
        "stop_kept": "The music goes on, and the queue stays as it was.",
        "action_skipped": "⏭️ {user} skipped **{title}**",
        "action_skipto": "⏭️ {user} skipped ahead in the queue",
        "action_previous": "⏮️ {user} went back a song",
        "action_now": "▶️ {user} interrupted **{title}**, which plays next",
        "action_paused": "⏸️ {user} paused",
        "action_resumed": "▶️ {user} resumed",
        "action_loop": "🔁 {user} set repeat to {loop}",
        "action_shuffled": "🔀 {user} shuffled the queue",
        "action_cleared": "🧹 {user} cleared the queue",
        "action_volume": "🔊 {user} set the volume to {volume}%",
        "action_stopped": "⏹️ {user} stopped the music",
        "action_skipvote": "🗳️ {user} voted to skip: {votes} of {needed} votes",
        "action_skipped_vote": "⏭️ The listeners voted to skip **{title}**",
        "help_title": "How to use the bot",
        "help_intro": "Each part below explains one of the bot's features and the commands that belong to it. Discord's / menu shows every command with its options.",
        "help_commands": "Commands: {commands}",
        "help_bot_channel": "In this server, the bot takes commands only in {channel}.",
        "guide_media": "Join a voice channel, then use `/play` with a YouTube, SoundCloud, or Spotify link, or with words to search for. Each song shows on a panel whose buttons pause, skip, go back, and repeat, and `/queue show` lists what waits. `/music` and `/queue` hold the other controls. Spotify albums and songs work, but Spotify keeps most playlists from bots. When the server has a DJ role, some controls belong to DJs while others listen, and skips go by vote.",
        "guide_voice": "The bot joins your voice channel when a feature needs it, and leaves on its own when everyone else has left or nothing has played for a while. `/voice join` brings it to your channel, `/voice leave` sends it out, and `/voice stop` stops the sound that plays now.",
        "guide_moderation": "`/warn` gives a member a warning, and at the server's limit the bot kicks, bans, or times them out. `/warnings` lists and removes warnings, and `/timeout`, `/kick`, and `/ban` act at once. `/purge` deletes recent messages. Right-click a member and choose Apps, then Warn, to warn them quickly. Anyone can right-click a message and choose Report to moderators, which sends it to the AutoMod alert channel.",
        "guide_admin": "`/admin` sets the bot up for this server. `/admin channel` limits commands to one channel, `/admin autorole` gives new members a role and welcomes them, `/admin djrole` picks who controls the music, and `/admin automod` manages Discord's AutoMod filters. `/admin status` shows every setting.",
        "guide_template": "`/example hello` shows how a command of a new feature works. A new feature starts as a copy of cogs/template.py.",
        "guide_help": "`/help` shows this guide, and `/about` shows the bot's version, how long it has been online, and its response time.",
        "guide_info": "`/info server` shows the server's age, size, and boosts, `/info member` shows when a member joined and their roles, and `/info avatar` shows an avatar in full size. Only you see the answers.",
        "section_info": "Info",
        "info_created": "Created",
        "info_owner": "Owner",
        "info_members": "Members",
        "info_channels": "Channels",
        "info_channel_counts": "{text} text, {voice} voice",
        "info_roles": "Roles",
        "info_boosts": "Boosts",
        "info_boost_level": "Level {level}, {count} boosts",
        "info_account_created": "Account created",
        "info_joined": "Joined the server",
        "info_boosting": "Boosting since",
        "info_more": "and {count} more",
        "info_avatar_title": "Avatar of {user}",
        "about_text": "**{name}** {version}\nOnline since {since}\nResponse time: {latency} ms\nServers: {servers}",
        "about_link": "Source code: <{url}>",
        "help_empty": "No commands are available to you here.",
        "section_admin": "Admin",
        "section_help": "Help",
        "section_media": "Media",
        "section_moderation": "Moderation",
        "section_template": "Template",
        "section_voice": "Voice",
        "admin_channel_set": "Bot channel set to {channel}.",
        "admin_channel_cleared": "Bot channel restriction removed.",
        "admin_autorole_set": "Auto-role set to {role}.",
        "admin_autorole_cleared": "Auto-role cleared.",
        "admin_dj_set": "DJ role set to {role}. While others listen, only it, admins, and a lone listener control the music, and other skips go by vote.",
        "admin_dj_cleared": "DJ role cleared. Everyone controls the music again.",
        "admin_threshold_set": "Warning threshold set to {count}.",
        "admin_action_set": "Warning action set to **{action}**.",
        "admin_timeout_set": "Timeout length set to {minutes} minutes.",
        "admin_status": (
            "**Bot settings**\nChannel: {channel}\nAuto-role: {autorole}\nDJ role: {dj}\n"
            "Warning threshold: {threshold}\nWarning action: {action}\n"
            "Timeout length: {timeout} minutes\nAutoMod escalation: {escalation}\n"
            "AutoMod alerts: {alert}\nAutoMod keywords: {keywords}\n"
            "AutoMod presets: {presets}"
        ),
        "status_any_channel": "any channel",
        "status_none": "none",
        "status_unavailable": "unavailable",
        "action_kick": "kick",
        "action_ban": "ban",
        "action_timeout": "timeout",
        "automod_keywords_invalid": (
            "Give keywords separated by commas, each at most {length} characters long. "
            "Too long: {keywords}"
        ),
        "automod_keywords_limit": "The keyword filter can hold at most {limit} keywords.",
        "automod_keywords_saved": "The keyword filter now has {count} keyword(s).",
        "automod_keywords_none": "The keyword filter is empty.",
        "automod_keywords_header": "**Keyword filter** ({count} in total)",
        "automod_preset_on": "The {preset} filter is now on.",
        "automod_preset_off": "The {preset} filter is now off.",
        "automod_alert_set": "AutoMod alerts now go to {channel}.",
        "automod_alert_cleared": "AutoMod alerts are off.",
        "automod_escalation_warn": "Every message that AutoMod blocks now counts as a warning.",
        "automod_escalation_none": "Messages that AutoMod blocks no longer count as warnings.",
        "automod_no_permission": "I need the Manage Server permission to manage AutoMod rules.",
        "automod_failed": "Discord refused the AutoMod change. Reason: {error}",
        "automod_warned": (
            "🛡️ AutoMod blocked a message from **{user}**, "
            "who now has {count}/{threshold} warnings."
        ),
        "escalation_warn": "a warning",
        "escalation_none": "nothing more",
        "preset_profanity": "profanity",
        "preset_sexual_content": "sexual content",
        "preset_slurs": "slurs",
        "warn_issued": "⚠️ **{user}** was warned ({count}/{threshold}).",
        "warn_threshold_kick": "🚨 The warning limit was reached, so **{user}** will be kicked.",
        "warn_threshold_ban": "🚨 The warning limit was reached, so **{user}** will be banned.",
        "warn_threshold_timeout": (
            "🚨 The warning limit was reached, so **{user}** will be timed out "
            "for {minutes} minutes."
        ),
        "warnings_list_header": "**Warnings for {user}** ({count} in total)",
        "warnings_list_entry": "`#{id}` {reason} _({date})_",
        "warnings_no_reason": "No reason given.",
        "warnings_none": "**{user}** has no warnings.",
        "warnings_cleared": "Cleared {count} warning(s) from **{user}**.",
        "warning_removed": "Warning `#{id}` was removed.",
        "warning_not_found": "Warning `#{id}` was not found in this server.",
        "kick_success": "**{user}** was kicked.",
        "kick_failed": "Could not kick **{user}**. Reason: {error}",
        "ban_success": "**{user}** was banned.",
        "ban_failed": "Could not ban **{user}**. Reason: {error}",
        "timeout_failed": "Could not time out **{user}**. Reason: {error}",
        "timeout_success": "**{user}** is timed out until {until}.",
        "untimeout_success": "The timeout of **{user}** was lifted.",
        "untimeout_none": "**{user}** has no timeout.",
        "untimeout_failed": "Could not lift the timeout of **{user}**. Reason: {error}",
        "purge_done": "Deleted {count} messages.",
        "purge_none": "No messages to delete were found among the messages of the last 14 days.",
        "purge_failed": "Could not delete the messages. Reason: {error}",
        "warn_modal_title": "Warn {user}",
        "warn_modal_reason": "Reason (optional)",
        "report_no_channel": "This server has no moderator channel for reports. An admin can set one with /admin automod alert.",
        "report_sent": "Thanks. The moderators got your report.",
        "report_failed": "The report did not reach the moderators. Try again later.",
        "report_title": "Reported message",
        "report_no_text": "(no text)",
        "report_author": "Author",
        "report_channel": "Channel",
        "report_by": "Reported by",
        "report_files": "Files",
        "mod_target_self": "You cannot moderate yourself.",
        "mod_target_protected": "**{user}** cannot be moderated.",
        "mod_target_higher": "**{user}** has a role equal to or higher than yours.",
        "mod_bot_too_low": "My highest role must be above the highest role of **{user}**.",
        "member_join_welcome": "Welcome, {member}! 👋",
    },
    "fi": {
        "bot_channel_only": "Tätä komentoa voi käyttää vain bottikanavalla.",
        "command_failed": "Jokin meni pieleen. Yritä myöhemmin uudelleen.",
        "cooldown": "Hiljennä hieman tahtia. Yritä uudelleen {seconds} s päästä.",
        "command_unavailable": "Tätä komentoa ei ole enää käytössä. Discord poistaa sen valikosta pian.",
        "example_hello": "Hei! Tämä komento tulee mallipohjan esimerkkiosasta, josta uudet ominaisuudet alkavat.",
        "not_in_voice": "Et ole äänikanavalla.",
        "bot_not_in_voice": "En ole äänikanavalla.",
        "already_same_channel": "Olen jo samalla äänikanavalla.",
        "joined_voice": "Liityin kanavalle `{channel}`.",
        "moved_voice": "Siirryin kanavalle `{channel}`.",
        "left_voice": "Poistuin kanavalta `{channel}`.",
        "skipped": "Ohitettu.",
        "nothing_playing": "Mitään ei soi.",
        "queued_now": "Soitetaan **{title}** ({source}).",
        "queued_one": "Lisätty **{title}** ({source}) jonoon sijalle {position}.",
        "queued_one_wait": "Lisätty **{title}** ({source}) jonoon sijalle {position}. Se soi noin {minutes} min päästä.",
        "queued_many": "Lisätty jonoon {count} kappaletta ({source}) sijalta {position} alkaen.",
        "queued_many_now": "Soitetaan **{title}** ({source}), ja jonoon lisätty {more} muuta kappaletta.",
        "queued_many_next": "Lisätty {count} kappaletta ({source}). **{title}** soi seuraavaksi, ja loput alkavat sijalta {position}.",
        "queue_full": "Jono on täynnä, koska siihen mahtuu enintään {limit} kappaletta. /queue clear tai /queue remove tekee tilaa.",
        "queue_cut": "{left} kappaletta jäi pois, koska jonoon mahtuu enintään {limit} kappaletta.",
        "playlist_unavailable": "Spotify ei anna botin lukea tätä soittolistaa. Albumit, yksittäiset kappaleet ja YouTube-soittolistat toimivat yhä.",
        "dj_only": "Vain DJ-roolin jäsenet voivat tehdä tämän, kun muut kuuntelevat.",
        "skip_voted": "Äänesi ohittamisen puolesta laskettiin: {votes}/{needed} tarvitaan.",
        "skip_already_voted": "Äänestit jo tämän kappaleen ohittamista: {votes}/{needed} tarvitaan.",
        "collection_on": "{collection} – {source}",
        "load_error": "Äänen lataaminen epäonnistui. Yritä uudelleen.",
        "play_failed": "Kappaletta **{title}** ei voitu soittaa, lisännyt {user}. Siirrytään seuraavaan.",
        "stopped": "Toisto pysäytetty ja jono tyhjennetty.",
        "paused": "Tauotettu.",
        "resumed": "Jatkettu.",
        "queue_empty": "Mitään ei soi, ja jono on tyhjä.",
        "queue_title": "Jono",
        "queue_now_playing": "**Nyt soi:** {title}",
        "queue_next": "**Seuraavaksi:**",
        "queue_line": "`{position}.` {title} · {user}",
        "queue_footer": "Sivu {page}/{pages} · {count} kappaletta · {length}",
        "queue_removed": "Poistettu **{title}** jonosta.",
        "queue_moved": "Siirretty **{title}** sijalle {position}.",
        "queue_shuffled": "Sekoitettu {count} kappaletta.",
        "queue_cleared": "Jonosta poistettu {count} kappaletta. Nykyinen kappale soi loppuun.",
        "queue_skipping_to": "Hypätään kappaleeseen **{title}**.",
        "queue_no_position": "Sijalla {position} ei ole kappaletta. /queue show näyttää numerot.",
        "queue_nothing_waiting": "Jonossa ei odota kappaleita.",
        "volume_now": "Äänenvoimakkuus on {volume} %.",
        "volume_set": "Äänenvoimakkuudeksi asetettu {volume} %.",
        "previous_playing": "Palataan kappaleeseen **{title}**.",
        "previous_none": "Aiempaa kappaletta ei ole.",
        "loop_off": "Toisto on pois päältä.",
        "loop_track": "Toistetaan nykyistä kappaletta.",
        "loop_queue": "Toistetaan koko jonoa.",
        "lyrics_nothing": "Mitään ei soi. Kerro haettava kappale.",
        "lyrics_none": "Kappaleelle **{title}** ei löytynyt sanoja.",
        "lyrics_unavailable": "Sanapalveluun ei saatu yhteyttä. Yritä myöhemmin uudelleen.",
        "lyrics_footer": "Sanat: LRCLIB",
        "status_idle": "/help näyttää komennot",
        "status_playing": "🎵 Soittaa musiikkia",
        "panel_playing": "Nyt soi",
        "panel_paused": "Tauolla",
        "panel_ended": "Soitto päättyi",
        "panel_details": "Lähde: {source}, lisännyt {user}",
        "panel_next": "Seuraavaksi",
        "panel_next_none": "Ei vielä mitään. /play lisää kappaleita.",
        "panel_more": "…ja {count} muuta",
        "panel_footer": "Toisto: {loop} · Äänenvoimakkuus: {volume} %",
        "panel_loop_off": "pois",
        "panel_loop_track": "tämä kappale",
        "panel_loop_queue": "koko jono",
        "panel_stop": "Pysäytä",
        "panel_queue": "Jono",
        "panel_lyrics": "Sanat",
        "panel_not_listening": "Liity botin äänikanavalle ohjataksesi musiikkia.",
        "session_title": "{count} kappaletta · {length}",
        "session_hours": "{hours} h {minutes} min",
        "session_minutes": "{minutes} min",
        "session_added_by": "Lisänneet {users}",
        "session_mostly": "Enimmäkseen: {source}",
        "session_last": "**Viimeinen kappale:** {title}",
        "names_two": "{first} ja {second}",
        "names_last": " ja {last}",
        "names_others": "{count} muuta",
        "panel_played": "Soitetut kappaleet",
        "played_title": "Soitetut kappaleet",
        "played_gone": "Tätä listaa ei enää säilytetä. Botti säilyttää 20 viimeisen kerran kappaleet.",
        "stop_confirm": "Tämä pysäyttää musiikin ja poistaa {count} jonossa odottavaa kappaletta.",
        "stop_confirm_yes": "Pysäytä ja tyhjennä",
        "stop_confirm_no": "Peruuta",
        "stop_kept": "Musiikki jatkuu, ja jono pysyy ennallaan.",
        "action_skipped": "⏭️ {user} ohitti kappaleen **{title}**",
        "action_skipto": "⏭️ {user} hyppäsi jonossa eteenpäin",
        "action_previous": "⏮️ {user} palasi edelliseen kappaleeseen",
        "action_now": "▶️ {user} keskeytti kappaleen **{title}**, joka soi seuraavaksi",
        "action_paused": "⏸️ {user} tauotti soiton",
        "action_resumed": "▶️ {user} jatkoi soittoa",
        "action_loop": "🔁 {user} asetti toiston: {loop}",
        "action_shuffled": "🔀 {user} sekoitti jonon",
        "action_cleared": "🧹 {user} tyhjensi jonon",
        "action_volume": "🔊 {user} asetti äänenvoimakkuudeksi {volume} %",
        "action_stopped": "⏹️ {user} pysäytti musiikin",
        "action_skipvote": "🗳️ {user} äänesti ohittamisen puolesta: {votes}/{needed} ääntä",
        "action_skipped_vote": "⏭️ Kuuntelijat äänestivät kappaleen **{title}** ohitetuksi",
        "help_title": "Botin käyttöohje",
        "help_intro": "Jokainen alla oleva osa kertoo yhdestä botin ominaisuudesta ja sen komennoista. Discordin /-valikko näyttää kaikki komennot vaihtoehtoineen.",
        "help_commands": "Komennot: {commands}",
        "help_bot_channel": "Tällä palvelimella botti ottaa komentoja vastaan vain kanavalla {channel}.",
        "guide_media": "Liity äänikanavalle ja käytä `/play`-komentoa YouTube-, SoundCloud- tai Spotify-linkin tai hakusanojen kanssa. Jokainen kappale näkyy paneelissa, jonka painikkeilla voi tauottaa, ohittaa, palata ja toistaa, ja `/queue show` näyttää jonon. `/music` ja `/queue` sisältävät muut säätimet. Spotifyn albumit ja kappaleet toimivat, mutta useimpia soittolistoja Spotify ei jaa boteille. Jos palvelimella on DJ-rooli, osa säätimistä kuuluu DJ:lle muiden kuunnellessa, ja ohitukset äänestetään.",
        "guide_voice": "Botti liittyy äänikanavallesi, kun jokin ominaisuus tarvitsee sitä, ja poistuu itse, kun muut ovat lähteneet tai mitään ei ole soinut hetkeen. `/voice join` tuo sen kanavallesi, `/voice leave` lähettää sen pois, ja `/voice stop` pysäyttää nyt soivan äänen.",
        "guide_moderation": "`/warn` antaa jäsenelle varoituksen, ja palvelimen rajalla botti potkaisee jäsenen, antaa porttikiellon tai aikalisän. `/warnings` näyttää ja poistaa varoituksia, ja `/timeout`, `/kick` ja `/ban` toimivat heti. `/purge` poistaa viimeisimmät viestit. Napsauta jäsentä hiiren oikealla ja valitse Sovellukset ja Varoita, niin varoitat nopeasti. Kuka tahansa voi napsauttaa viestiä hiiren oikealla ja valita Ilmoita moderaattoreille, jolloin viesti menee AutoMod-hälytyskanavalle.",
        "guide_admin": "`/admin` määrittää botin tälle palvelimelle. `/admin channel` rajaa komennot yhdelle kanavalle, `/admin autorole` antaa uusille jäsenille roolin ja toivottaa heidät tervetulleiksi, `/admin djrole` valitsee, kuka ohjaa musiikkia, ja `/admin automod` hallitsee Discordin AutoMod-suodattimia. `/admin status` näyttää kaikki asetukset.",
        "guide_template": "`/example hello` näyttää, miten uuden ominaisuuden komento toimii. Uusi ominaisuus alkaa kopiona tiedostosta cogs/template.py.",
        "guide_help": "`/help` näyttää tämän ohjeen, ja `/about` näyttää botin version, kuinka kauan se on ollut päällä ja sen vasteajan.",
        "guide_info": "`/info server` näyttää palvelimen iän, koon ja tehostukset, `/info member` näyttää, milloin jäsen liittyi ja hänen roolinsa, ja `/info avatar` näyttää profiilikuvan täysikokoisena. Vain sinä näet vastaukset.",
        "section_info": "Tiedot",
        "info_created": "Luotu",
        "info_owner": "Omistaja",
        "info_members": "Jäseniä",
        "info_channels": "Kanavia",
        "info_channel_counts": "{text} teksti, {voice} ääni",
        "info_roles": "Roolit",
        "info_boosts": "Tehostukset",
        "info_boost_level": "Taso {level}, {count} tehostusta",
        "info_account_created": "Tili luotu",
        "info_joined": "Liittyi palvelimelle",
        "info_boosting": "Tehostanut alkaen",
        "info_more": "ja {count} muuta",
        "info_avatar_title": "Käyttäjän {user} profiilikuva",
        "about_text": "**{name}** {version}\nPäällä {since} alkaen\nVasteaika: {latency} ms\nPalvelimia: {servers}",
        "about_link": "Lähdekoodi: <{url}>",
        "help_empty": "Sinulla ei ole täällä käytettävissä komentoja.",
        "section_admin": "Ylläpito",
        "section_help": "Ohje",
        "section_media": "Media",
        "section_moderation": "Moderointi",
        "section_template": "Malli",
        "section_voice": "Ääni",
        "admin_channel_set": "Bottikanavaksi asetettiin {channel}.",
        "admin_channel_cleared": "Bottikanavan rajoitus poistettiin.",
        "admin_autorole_set": "Automaattiseksi rooliksi asetettiin {role}.",
        "admin_dj_set": "DJ-rooliksi asetettiin {role}. Kun muut kuuntelevat, vain se, ylläpitäjät ja yksin kuunteleva ohjaavat musiikkia, ja muut ohitukset äänestetään.",
        "admin_dj_cleared": "DJ-rooli poistettiin. Kaikki ohjaavat musiikkia taas.",
        "admin_autorole_cleared": "Automaattinen rooli poistettiin.",
        "admin_threshold_set": "Varoitusrajaksi asetettiin {count}.",
        "admin_action_set": "Varoitusrajan seuraukseksi asetettiin **{action}**.",
        "admin_timeout_set": "Aikalisän pituudeksi asetettiin {minutes} minuuttia.",
        "admin_status": (
            "**Botin asetukset**\nKanava: {channel}\nAutomaattinen rooli: {autorole}\nDJ-rooli: {dj}\n"
            "Varoitusraja: {threshold}\nSeuraus: {action}\n"
            "Aikalisän pituus: {timeout} minuuttia\nAutoMod-seuraus: {escalation}\n"
            "AutoMod-hälytykset: {alert}\nAutoMod-avainsanat: {keywords}\n"
            "AutoMod-esiasetukset: {presets}"
        ),
        "status_any_channel": "mikä tahansa kanava",
        "status_none": "ei asetettu",
        "status_unavailable": "ei saatavilla",
        "action_kick": "potku",
        "action_ban": "porttikielto",
        "action_timeout": "aikalisä",
        "automod_keywords_invalid": (
            "Anna avainsanat pilkuilla eroteltuina. "
            "Kukin saa olla enintään {length} merkkiä pitkä. Liian pitkät: {keywords}"
        ),
        "automod_keywords_limit": "Avainsanasuodattimessa voi olla enintään {limit} avainsanaa.",
        "automod_keywords_saved": "Avainsanasuodattimessa on nyt {count} avainsana(a).",
        "automod_keywords_none": "Avainsanasuodatin on tyhjä.",
        "automod_keywords_header": "**Avainsanasuodatin** ({count} yhteensä)",
        "automod_preset_on": "Suodatus luokalle {preset} on nyt käytössä.",
        "automod_preset_off": "Suodatus luokalle {preset} on nyt pois käytöstä.",
        "automod_alert_set": "AutoMod-hälytykset ohjataan nyt kanavalle {channel}.",
        "automod_alert_cleared": "AutoMod-hälytykset on poistettu käytöstä.",
        "automod_escalation_warn": "Jokainen AutoModin estämä viesti lasketaan nyt varoitukseksi.",
        "automod_escalation_none": "AutoModin estämiä viestejä ei enää lasketa varoituksiksi.",
        "automod_no_permission": (
            "Tarvitsen Hallitse palvelinta -oikeuden AutoMod-sääntöjen hallintaan."
        ),
        "automod_failed": "Discord hylkäsi AutoMod-muutoksen. Syy: {error}",
        "automod_warned": (
            "🛡️ AutoMod esti käyttäjän **{user}** viestin. "
            "Hänellä on nyt {count}/{threshold} varoitusta."
        ),
        "escalation_warn": "varoitus",
        "escalation_none": "ei muuta",
        "preset_profanity": "kiroilu",
        "preset_sexual_content": "seksuaalinen sisältö",
        "preset_slurs": "herjaukset",
        "warn_issued": "⚠️ **{user}** sai varoituksen ({count}/{threshold}).",
        "warn_threshold_kick": "🚨 Varoitusraja täyttyi, joten **{user}** potkitaan palvelimelta.",
        "warn_threshold_ban": "🚨 Varoitusraja täyttyi, joten **{user}** saa porttikiellon.",
        "warn_threshold_timeout": (
            "🚨 Varoitusraja täyttyi, joten **{user}** saa {minutes} minuutin aikalisän."
        ),
        "warnings_list_header": "**Käyttäjän {user} varoitukset** ({count} yhteensä)",
        "warnings_list_entry": "`#{id}` {reason} _({date})_",
        "warnings_no_reason": "Syytä ei annettu.",
        "warnings_none": "Käyttäjällä **{user}** ei ole varoituksia.",
        "warnings_cleared": "Käyttäjältä **{user}** poistettiin {count} varoitus(ta).",
        "warning_removed": "Varoitus `#{id}` poistettiin.",
        "warning_not_found": "Varoitusta `#{id}` ei löytynyt tältä palvelimelta.",
        "kick_success": "**{user}** potkaistiin palvelimelta.",
        "kick_failed": "Käyttäjän **{user}** potkaiseminen epäonnistui. Syy: {error}",
        "ban_success": "**{user}** sai porttikiellon.",
        "ban_failed": "Porttikiellon antaminen käyttäjälle **{user}** epäonnistui. Syy: {error}",
        "timeout_failed": "Aikalisän antaminen käyttäjälle **{user}** epäonnistui. Syy: {error}",
        "timeout_success": "**{user}** sai aikalisän, joka päättyy {until}.",
        "untimeout_success": "Käyttäjän **{user}** aikalisä poistettiin.",
        "untimeout_none": "Käyttäjällä **{user}** ei ole aikalisää.",
        "untimeout_failed": "Käyttäjän **{user}** aikalisän poistaminen epäonnistui. Syy: {error}",
        "purge_done": "Poistettiin {count} viestiä.",
        "purge_none": "Poistettavia viestejä ei löytynyt viimeisen 14 päivän viesteistä.",
        "purge_failed": "Viestien poistaminen epäonnistui. Syy: {error}",
        "warn_modal_title": "Varoita: {user}",
        "warn_modal_reason": "Syy (valinnainen)",
        "report_no_channel": "Tällä palvelimella ei ole moderaattorikanavaa ilmoituksille. Ylläpitäjä voi asettaa sen komennolla /admin automod alert.",
        "report_sent": "Kiitos. Moderaattorit saivat ilmoituksesi.",
        "report_failed": "Ilmoitus ei päässyt moderaattoreille. Yritä myöhemmin uudelleen.",
        "report_title": "Ilmoitettu viesti",
        "report_no_text": "(ei tekstiä)",
        "report_author": "Kirjoittaja",
        "report_channel": "Kanava",
        "report_by": "Ilmoittaja",
        "report_files": "Tiedostot",
        "mod_target_self": "Et voi moderoida itseäsi.",
        "mod_target_protected": "Käyttäjää **{user}** ei voi moderoida.",
        "mod_target_higher": (
            "Käyttäjällä **{user}** on yhtä korkea tai korkeampi rooli kuin sinulla."
        ),
        "mod_bot_too_low": (
            "Korkeimman roolini täytyy olla käyttäjän **{user}** korkeinta roolia ylempänä."
        ),
        "member_join_welcome": "Tervetuloa, {member}! 👋",
    },
}

# Translations of the core commands' descriptions, option descriptions, and choice names.
# Keys are the English texts exactly as the cogs define them.
# Command and option names are never translated.
CORE_COMMAND_TEXT: dict[str, dict[str, str]] = {
    "fi": {
        "Configure the bot for this server.": "Määritä botin asetukset tälle palvelimelle.",
        "Set or clear the only channel where the bot accepts commands.": "Aseta tai poista kanava, jolla botti ainoastaan ottaa komentoja vastaan.",
        "The channel to allow. Leave it empty to allow every channel.": "Sallittu kanava. Jätä tyhjäksi salliaksesi kaikki kanavat.",
        "Set or clear the DJ role, which controls the music while others listen.": "Aseta tai poista DJ-rooli, joka ohjaa musiikkia muiden kuunnellessa.",
        "The DJ role. Leave it empty to let everyone control the music.": "DJ-rooli. Jätä tyhjäksi, niin kaikki ohjaavat musiikkia.",
        "Set or clear the role that new members get automatically.": "Aseta tai poista rooli, jonka uudet jäsenet saavat automaattisesti.",
        "The role to give. Leave it empty to give no role.": "Annettava rooli. Jätä tyhjäksi, jos roolia ei anneta.",
        "Set how many warnings trigger the warning action.": "Aseta, montako varoitusta johtaa seuraukseen.",
        "How many warnings trigger the action, from 1 to 20.": "Montako varoitusta johtaa seuraukseen, 1–20.",
        "Set what happens when a member reaches the warning limit.": "Aseta, mitä tapahtuu, kun jäsen saavuttaa varoitusrajan.",
        "What happens at the warning limit.": "Mitä varoitusrajalla tapahtuu.",
        "Kick": "Potku",
        "Ban": "Porttikielto",
        "Timeout": "Aikalisä",
        "Set how long the timeout warning action lasts.": "Aseta, kuinka kauan aikalisä kestää.",
        "How long the timeout lasts, from 1 minute to 28 days (40320 minutes).": "Aikalisän pituus 1 minuutista 28 päivään (40320 minuuttia).",
        "Manage the Discord AutoMod rules that this bot owns.": "Hallitse botin omistamia Discordin AutoMod-sääntöjä.",
        "Add keywords to the bot's AutoMod keyword filter.": "Lisää avainsanoja botin AutoMod-avainsanasuodattimeen.",
        "Words or phrases separated by commas. Use * as a wildcard, as in spam*.": "Sanat tai fraasit pilkuilla eroteltuina. Käytä *-merkkiä jokerina, kuten spam*.",
        "Remove keywords from the bot's AutoMod keyword filter.": "Poista avainsanoja botin AutoMod-avainsanasuodattimesta.",
        "The keywords to remove, separated by commas.": "Poistettavat avainsanat pilkuilla eroteltuina.",
        "List the keywords in the bot's AutoMod keyword filter.": "Näytä botin AutoMod-avainsanasuodattimen avainsanat.",
        "Turn one of Discord's preset word filters on or off.": "Ota Discordin valmis sanasuodatin käyttöön tai pois käytöstä.",
        "The kind of language that Discord's own word list filters.": "Kielenkäytön laji, jota Discordin oma sanalista suodattaa.",
        "Whether to filter this category.": "Suodatetaanko tämä luokka.",
        "Profanity": "Kiroilu",
        "Sexual content": "Seksuaalinen sisältö",
        "Slurs": "Herjaukset",
        "Set or clear the channel for AutoMod alerts and warning reports.": "Aseta tai poista AutoMod-hälytysten ja varoitusilmoitusten kanava.",
        "The channel for alerts. Leave it empty to turn alerts off.": "Hälytysten kanava. Jätä tyhjäksi poistaaksesi hälytykset käytöstä.",
        "Choose whether messages that AutoMod blocks count as warnings.": "Valitse, lasketaanko AutoModin estämät viestit varoituksiksi.",
        "What happens to a member whose message AutoMod blocks.": "Mitä tapahtuu jäsenelle, jonka viestin AutoMod estää.",
        "Nothing more": "Ei muuta",
        "Add a warning": "Lisää varoitus",
        "Show this server's bot settings.": "Näytä tämän palvelimen botin asetukset.",
        "Show a short guide to the bot and the commands you can use here.": "Näytä lyhyt ohje bottiin ja komennot, joita voit käyttää täällä.",
        "Show the bot's version, how long it has been online, and its response time.": "Näytä botin versio, käynnissäoloaika ja vasteaika.",
        "When it plays. Leave it out to add it to the end of the queue.": "Milloin se soi. Jätä pois, niin se lisätään jonon loppuun.",
        "Next": "Seuraavaksi",
        "Now": "Heti",
        "Play a link or search result, or add it to the queue.": "Soita linkki tai hakutulos, tai lisää se jonoon.",
        "A YouTube, SoundCloud, or Spotify link, or words to search for.": "YouTube-, SoundCloud- tai Spotify-linkki tai hakusanat.",
        "Where a search looks. A link plays from its own site.": "Mistä haku etsii. Linkki soi omalta sivustoltaan.",
        # Brand names stay as they are in every language.
        "YouTube": "YouTube",
        "SoundCloud": "SoundCloud",
        "Remove a track from the queue.": "Poista kappale jonosta.",
        "The track's number in /queue show.": "Kappaleen numero /queue show -listassa.",
        "Move a track to another place in the queue.": "Siirrä kappale toiseen kohtaan jonossa.",
        "The track's new number.": "Kappaleen uusi numero.",
        "Shuffle the tracks waiting in the queue.": "Sekoita jonossa odottavat kappaleet.",
        "Remove every waiting track. The current track keeps playing.": "Poista kaikki odottavat kappaleet. Nykyinen kappale soi loppuun.",
        "Skip to a track in the queue, dropping the tracks before it.": "Hyppää jonon kappaleeseen ja ohita sitä edeltävät.",
        "Show or change the music volume, from 0 to 100 percent.": "Näytä tai muuta musiikin äänenvoimakkuutta 0–100 prosenttiin.",
        "The new volume. Leave it out to see the current one.": "Uusi äänenvoimakkuus. Jätä pois nähdäksesi nykyisen.",
        "Go back to the song that played before.": "Palaa edelliseen kappaleeseen.",
        "Repeat the current song or the whole queue.": "Toista nykyistä kappaletta tai koko jonoa.",
        "What to repeat.": "Mitä toistetaan.",
        "Off": "Pois",
        "This song": "Tämä kappale",
        "The whole queue": "Koko jono",
        "Show the lyrics of the playing song, or of a song you name.": "Näytä soivan tai nimeämäsi kappaleen sanat.",
        "A song to look up. Leave it out for the playing song.": "Haettava kappale. Jätä pois, niin haetaan soiva kappale.",
        "Stop playing and clear the queue.": "Pysäytä toisto ja tyhjennä jono.",
        "Pause or resume the audio that is playing now.": "Tauota tai jatka nyt soivaa ääntä.",
        "Show the playing song and the queue, only to you.": "Näytä soiva kappale ja jono vain sinulle.",
        "Warn a member. At the warning limit they are kicked, banned, or timed out.": "Varoita jäsentä. Varoitusrajalla jäsen potkitaan, saa porttikiellon tai aikalisän.",
        "The member to warn.": "Varoitettava jäsen.",
        "Why the member is warned.": "Varoituksen syy.",
        "List a member's warnings in this server.": "Näytä jäsenen varoitukset tällä palvelimella.",
        "The member whose warnings to list.": "Jäsen, jonka varoitukset näytetään.",
        "Remove one warning by its number.": "Poista yksi varoitus sen numeron perusteella.",
        "The warning number shown by /warnings list.": "Komennon /warnings list näyttämä varoituksen numero.",
        "Remove every warning of a member in this server.": "Poista jäsenen kaikki varoitukset tällä palvelimella.",
        "The member whose warnings to remove.": "Jäsen, jonka varoitukset poistetaan.",
        "Time out a member, so they cannot write or speak for a while.": "Anna jäsenelle aikalisä, jolloin hän ei voi kirjoittaa tai puhua hetkeen.",
        "The member to time out.": "Jäsen, joka saa aikalisän.",
        "How long the timeout lasts.": "Kuinka kauan aikalisä kestää.",
        "Why the member is timed out. It appears in the audit log.": "Aikalisän syy. Se näkyy tarkastuslokissa.",
        "60 seconds": "60 sekuntia",
        "5 minutes": "5 minuuttia",
        "10 minutes": "10 minuuttia",
        "1 hour": "1 tunti",
        "1 day": "1 päivä",
        "1 week": "1 viikko",
        "Lift a member's timeout.": "Poista jäsenen aikalisä.",
        "The member whose timeout to lift.": "Jäsen, jonka aikalisä poistetaan.",
        "Delete recent messages in this channel, optionally only from one member.": "Poista tämän kanavan viimeisimmät viestit, halutessasi vain yhdeltä jäseneltä.",
        "How many messages to delete, from 1 to 100.": "Kuinka monta viestiä poistetaan, 1–100.",
        "Only delete this member's messages.": "Poista vain tämän jäsenen viestit.",
        "Warn": "Varoita",
        "Report to moderators": "Ilmoita moderaattoreille",
        "Show facts about this server or one of its members.": "Näytä tietoja tästä palvelimesta tai sen jäsenestä.",
        "Show this server's age, size, and boosts, only to you.": "Näytä palvelimen ikä, koko ja tehostukset vain sinulle.",
        "Show when a member joined and which roles they have, only to you.": "Näytä, milloin jäsen liittyi ja mitkä roolit hänellä on, vain sinulle.",
        "Show a member's avatar in full size, only to you.": "Näytä jäsenen profiilikuva täysikokoisena vain sinulle.",
        "The member to show. Leave it empty to show yourself.": "Näytettävä jäsen. Jätä tyhjäksi, niin näet itsesi.",
        "Kick a member from this server.": "Potkaise jäsen tältä palvelimelta.",
        "The member to kick.": "Potkaistava jäsen.",
        "Why the member is kicked. It appears in the audit log.": "Potkun syy. Se näkyy tarkastuslokissa.",
        "Ban a member from this server.": "Anna jäsenelle porttikielto tälle palvelimelle.",
        "The member to ban.": "Jäsen, joka saa porttikiellon.",
        "Why the member is banned. It appears in the audit log.": "Porttikiellon syy. Se näkyy tarkastuslokissa.",
        "Try the example commands of the template cog.": "Kokeile mallipohjan esimerkkiosan komentoja.",
        "Say hello, to show how a command of a new feature works.": "Sano hei ja näytä, miten uuden ominaisuuden komento toimii.",
        "Join your voice channel.": "Liity äänikanavallesi.",
        "Leave the voice channel and stop playing.": "Poistu äänikanavalta ja lopeta toisto.",
        "Stop the sound that plays now, such as a clip, speech, or the current song.": "Pysäytä nyt soiva ääni, kuten klippi, puhe tai nykyinen kappale.",
        "Bring the bot into a voice channel, send it out, or stop what it plays.": "Tuo botti äänikanavalle, lähetä se pois tai pysäytä sen soittama ääni.",
        "Control the music that plays now.": "Ohjaa nyt soivaa musiikkia.",
        "See and change the songs waiting in the queue.": "Katso ja muuta jonossa odottavia kappaleita.",
        "Skip the song that plays now, or vote to skip it while others listen.": "Ohita nyt soiva kappale tai äänestä sen ohittamisesta muiden kuunnellessa.",
        "See and remove the warnings of members in this server.": "Katso ja poista jäsenten varoituksia tällä palvelimella.",
    },
}
