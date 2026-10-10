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
    command_unavailable: str = ""
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

    # Media. Placeholders are {user}, {count}, {title}, {channel}, and {position}.
    queued_one: str = ""
    queued_many: str = ""
    now_playing: str = ""
    load_error: str = ""
    stopped: str = ""
    paused: str = ""
    resumed: str = ""
    queue_empty: str = ""
    queue_now_playing: str = ""
    queue_next: str = ""
    queue_line: str = ""
    queue_more: str = ""

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
    # admin_timeout_set uses {minutes}.
    # admin_status also uses {timeout}, {escalation}, {alert}, {keywords}, and {presets}.
    admin_channel_set: str = ""
    admin_channel_cleared: str = ""
    admin_autorole_set: str = ""
    admin_autorole_cleared: str = ""
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
        "command_unavailable": "This command is no longer available. Discord removes it from the menu shortly.",
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
        "queue_empty": "Nothing is playing, and the queue is empty.",
        "queue_now_playing": "Now playing: `{title}`",
        "queue_next": "Up next:",
        "queue_line": "{position}. {title}, queued by `{user}`",
        "queue_more": "...and {count} more.",
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
        "admin_timeout_set": "Timeout length set to {minutes} minutes.",
        "admin_status": (
            "**Bot settings**\nChannel: {channel}\nAuto-role: {autorole}\n"
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
        "mod_target_self": "You cannot moderate yourself.",
        "mod_target_protected": "**{user}** cannot be moderated.",
        "mod_target_higher": "**{user}** has a role equal to or higher than yours.",
        "mod_bot_too_low": "My highest role must be above the highest role of **{user}**.",
        "member_join_welcome": "Welcome, {member}! 👋",
    },
    "fi": {
        "bot_channel_only": "Tätä komentoa voi käyttää vain bottikanavalla.",
        "command_failed": "Jokin meni pieleen. Yritä myöhemmin uudelleen.",
        "command_unavailable": "Tätä komentoa ei ole enää käytössä. Discord poistaa sen valikosta pian.",
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
        "queue_empty": "Mitään ei soi, ja jono on tyhjä.",
        "queue_now_playing": "Nyt soi: `{title}`",
        "queue_next": "Seuraavaksi:",
        "queue_line": "{position}. {title}, jonoon lisännyt `{user}`",
        "queue_more": "...ja {count} muuta.",
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
        "admin_timeout_set": "Aikalisän pituudeksi asetettiin {minutes} minuuttia.",
        "admin_status": (
            "**Botin asetukset**\nKanava: {channel}\nAutomaattinen rooli: {autorole}\n"
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
        "Show the commands you can use here.": "Näytä komennot, joita voit käyttää täällä.",
        "Play a link or search result, or add it to the queue.": "Soita linkki tai hakutulos, tai lisää se jonoon.",
        "A YouTube, SoundCloud, or Spotify link, or text to search for.": "YouTube-, SoundCloud- tai Spotify-linkki tai hakuteksti.",
        "Stop playing and clear the queue.": "Pysäytä toisto ja tyhjennä jono.",
        "Pause or resume the audio that is playing now.": "Tauota tai jatka nyt soivaa ääntä.",
        "Show the song playing now and the songs in the queue.": "Näytä nyt soiva kappale ja jonossa olevat kappaleet.",
        "Warn a member. At the warning limit they are kicked, banned, or timed out.": "Varoita jäsentä. Varoitusrajalla jäsen potkitaan, saa porttikiellon tai aikalisän.",
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
