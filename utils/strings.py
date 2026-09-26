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

    # General. The placeholder of ping_reply is {latency}.
    bot_channel_only: str = ""
    command_failed: str = ""
    ping_reply: str = ""

    # Voice. Placeholders are {user} and {channel}.
    not_in_voice: str = ""
    bot_not_in_voice: str = ""
    already_same_channel: str = ""
    joined_voice: str = ""
    moved_voice: str = ""
    left_voice: str = ""
    skipped: str = ""
    nothing_playing: str = ""

    # Media. Placeholders are {user}, {count}, {title}, and {channel}.
    queued_one: str = ""
    queued_many: str = ""
    now_playing: str = ""
    load_error: str = ""
    stopped: str = ""
    paused: str = ""
    resumed: str = ""

    # Help. A section_<cog> field names the section of that cog.
    # A cog without a section field falls back to its own name.
    help_title: str = ""
    help_footer: str = ""
    help_empty: str = ""
    section_admin: str = ""
    section_help: str = ""
    section_media: str = ""
    section_moderation: str = ""
    section_template: str = ""
    section_voice: str = ""

    # Admin. Placeholders are {channel}, {role}, {count}, {action}, {autorole}, and {threshold}.
    admin_channel_set: str = ""
    admin_channel_cleared: str = ""
    admin_autorole_set: str = ""
    admin_autorole_cleared: str = ""
    admin_threshold_set: str = ""
    admin_action_set: str = ""
    admin_status: str = ""
    status_any_channel: str = ""
    status_none: str = ""
    action_kick: str = ""
    action_ban: str = ""

    # Moderation. The placeholders are {user}, {count}, {threshold}, and {error}.
    # Warning lists also use {id}, {reason}, and {date}.
    warn_issued: str = ""
    warn_threshold_kick: str = ""
    warn_threshold_ban: str = ""
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
        "ping_reply": "Pong! {latency} ms.",
        "not_in_voice": "You are not in a voice channel, `{user}`.",
        "bot_not_in_voice": "I am not in a voice channel.",
        "already_same_channel": "I am already in your voice channel, `{user}`.",
        "joined_voice": "Joined `{channel}`.",
        "moved_voice": "Moved to `{channel}`.",
        "left_voice": "Left `{channel}`.",
        "skipped": "Skipped.",
        "nothing_playing": "Nothing is playing.",
        "queued_one": "Added to the queue, `{user}`.",
        "queued_many": "Added {count} tracks to the queue, `{user}`.",
        "now_playing": "Now playing `{title}` in `{channel}`.",
        "load_error": "Could not load the audio. Try again, `{user}`.",
        "stopped": "Stopped and cleared the queue.",
        "paused": "Paused.",
        "resumed": "Resumed.",
        "help_title": "Commands",
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
        "admin_threshold_set": "Warning threshold set to {count}.",
        "admin_action_set": "Warning action set to **{action}**.",
        "admin_status": (
            "**Bot settings**\nChannel: {channel}\nAuto-role: {autorole}\n"
            "Warning threshold: {threshold}\nWarning action: {action}"
        ),
        "status_any_channel": "any channel",
        "status_none": "none",
        "action_kick": "kick",
        "action_ban": "ban",
        "warn_issued": "⚠️ **{user}** was warned ({count}/{threshold}).",
        "warn_threshold_kick": "🚨 The warning limit was reached, so **{user}** will be kicked.",
        "warn_threshold_ban": "🚨 The warning limit was reached, so **{user}** will be banned.",
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
        "mod_target_self": "You cannot moderate yourself.",
        "mod_target_protected": "**{user}** cannot be moderated.",
        "mod_target_higher": "**{user}** has a role equal to or higher than yours.",
        "mod_bot_too_low": "My highest role must be above the highest role of **{user}**.",
        "member_join_welcome": "Welcome, {member}! 👋",
    },
    "fi": {
        "bot_channel_only": "Tätä komentoa voi käyttää vain bottikanavalla.",
        "command_failed": "Jokin meni pieleen. Yritä myöhemmin uudelleen.",
        "ping_reply": "Pong! {latency} ms.",
        "not_in_voice": "Et ole äänikanavalla, `{user}`.",
        "bot_not_in_voice": "En ole äänikanavalla.",
        "already_same_channel": "Olen jo samalla äänikanavalla, `{user}`.",
        "joined_voice": "Liityin kanavalle `{channel}`.",
        "moved_voice": "Siirryin kanavalle `{channel}`.",
        "left_voice": "Poistuin kanavalta `{channel}`.",
        "skipped": "Ohitettu.",
        "nothing_playing": "Mitään ei soi.",
        "queued_one": "Lisätty jonoon, `{user}`.",
        "queued_many": "Lisätty jonoon {count} kappaletta, `{user}`.",
        "now_playing": "Nyt soi `{title}` kanavalla `{channel}`.",
        "load_error": "Äänen lataaminen epäonnistui. Yritä uudelleen, `{user}`.",
        "stopped": "Toisto pysäytetty ja jono tyhjennetty.",
        "paused": "Tauotettu.",
        "resumed": "Jatkettu.",
        "help_title": "Komennot",
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
        "admin_autorole_cleared": "Automaattinen rooli poistettiin.",
        "admin_threshold_set": "Varoitusrajaksi asetettiin {count}.",
        "admin_action_set": "Varoitusrajan seuraukseksi asetettiin **{action}**.",
        "admin_status": (
            "**Botin asetukset**\nKanava: {channel}\nAutomaattinen rooli: {autorole}\n"
            "Varoitusraja: {threshold}\nSeuraus: {action}"
        ),
        "status_any_channel": "mikä tahansa kanava",
        "status_none": "ei asetettu",
        "action_kick": "potku",
        "action_ban": "porttikielto",
        "warn_issued": "⚠️ **{user}** sai varoituksen ({count}/{threshold}).",
        "warn_threshold_kick": "🚨 Varoitusraja täyttyi, joten **{user}** potkitaan palvelimelta.",
        "warn_threshold_ban": "🚨 Varoitusraja täyttyi, joten **{user}** saa porttikiellon.",
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
        "Set or clear the role that new members get automatically.": "Aseta tai poista rooli, jonka uudet jäsenet saavat automaattisesti.",
        "The role to give. Leave it empty to give no role.": "Annettava rooli. Jätä tyhjäksi, jos roolia ei anneta.",
        "Set how many warnings trigger the warning action.": "Aseta, montako varoitusta johtaa seuraukseen.",
        "How many warnings trigger the action, from 1 to 20.": "Montako varoitusta johtaa seuraukseen, 1–20.",
        "Set what happens when a member reaches the warning limit.": "Aseta, mitä tapahtuu, kun jäsen saavuttaa varoitusrajan.",
        "What happens at the warning limit.": "Mitä varoitusrajalla tapahtuu.",
        "Kick": "Potku",
        "Ban": "Porttikielto",
        "Show this server's bot settings.": "Näytä tämän palvelimen botin asetukset.",
        "Show the commands you can use here.": "Näytä komennot, joita voit käyttää täällä.",
        "Play a link or search result, or add it to the queue.": "Soita linkki tai hakutulos, tai lisää se jonoon.",
        "A YouTube, SoundCloud, or Spotify link, or text to search for.": "YouTube-, SoundCloud- tai Spotify-linkki tai hakuteksti.",
        "Stop playing and clear the queue.": "Pysäytä toisto ja tyhjennä jono.",
        "Pause or resume the audio that is playing now.": "Tauota tai jatka nyt soivaa ääntä.",
        "Warn a member. Reaching the warning limit kicks or bans them.": "Varoita jäsentä. Varoitusrajan täyttyessä jäsen potkitaan tai saa porttikiellon.",
        "The member to warn.": "Varoitettava jäsen.",
        "Why the member is warned.": "Varoituksen syy.",
        "List a member's warnings in this server.": "Näytä jäsenen varoitukset tällä palvelimella.",
        "The member whose warnings to list.": "Jäsen, jonka varoitukset näytetään.",
        "Remove one warning by its number.": "Poista yksi varoitus sen numeron perusteella.",
        "The warning number shown by /warnings.": "Komennon /warnings näyttämä varoituksen numero.",
        "Remove every warning of a member in this server.": "Poista jäsenen kaikki varoitukset tällä palvelimella.",
        "The member whose warnings to remove.": "Jäsen, jonka varoitukset poistetaan.",
        "Kick a member from this server.": "Potkaise jäsen tältä palvelimelta.",
        "The member to kick.": "Potkaistava jäsen.",
        "Why the member is kicked. It appears in the audit log.": "Potkun syy. Se näkyy tarkastuslokissa.",
        "Ban a member from this server.": "Anna jäsenelle porttikielto tälle palvelimelle.",
        "The member to ban.": "Jäsen, joka saa porttikiellon.",
        "Why the member is banned. It appears in the audit log.": "Porttikiellon syy. Se näkyy tarkastuslokissa.",
        "Show how long the bot takes to reach Discord.": "Näytä, kuinka nopeasti botti tavoittaa Discordin.",
        "Join your voice channel.": "Liity äänikanavallesi.",
        "Leave the voice channel and stop playing.": "Poistu äänikanavalta ja lopeta toisto.",
        "Skip the audio that is playing now.": "Ohita nyt soiva ääni.",
    },
}
