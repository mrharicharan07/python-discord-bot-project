# Zoro Bot Commands

This file explains what each command does and who should use it.

## User Commands

### Basic
- `!ping`
  Checks if the bot is online and shows latency.

- `!help`
  Shows the main command categories.

### AI / Utility
- `@BotName hi`
  If AI replies are enabled for the server, the bot replies when mentioned.

- `!avatar [@user]`
  Shows the avatar of you or the mentioned user.

- `!userinfo [@user]`
  Shows account and server info for a user.

- `!serverinfo`
  Shows server information.

### Levels
- `!rank`
  Shows your current level, XP, and progress.

- `!leaderboard`
  Shows the top users by level/XP.

### Economy
- `!balance [@user]`
  Shows coin balance.

- `!daily`
  Claims daily coins and increases streak.

- `!work`
  Earns coins with a cooldown.

- `!beg`
  Earns a small random amount of coins with a cooldown.

- `!give @user <amount>`
  Sends coins to another user.

- `!rich`
  Shows the richest users.

- `!shop`
  Shows available shop items.

- `!buy <item> [quantity]`
  Buys an item from the shop.

- `!inventory [@user]`
  Shows purchased items.

### Tickets
- `!ticket`
  Opens a support ticket channel if ticket system is configured.

### Giveaways
- `!giveaway <time> <winners> <prize>`
  Starts a giveaway if user has permission in that server.

### Welcome Preview
- `!testwelcome`
  Shows a test welcome embed in the current channel.

## Moderator / Admin Commands

### Setup
- `!setup`
  Shows quick setup steps for the server.

- `!status`
  Shows current configuration for the server.

- `!setlog #channel`
  Sets the main log channel.

- `!setprefixcmd <prefix>`
  Changes the bot prefix for this server.

### Moderation
- `!automod on/off`
  Enables or disables automod.

- `!sensitivity <20-100>`
  Sets moderation sensitivity threshold.

- `!setmute <minutes>`
  Sets timeout duration used by automod.

- `!setmaxwarn <2-10>`
  Sets the warning limit.

- `!warnings [@user]`
  Shows warnings.

- `!clearwarn @user`
  Clears warnings for a user.

- `!addword <word>`
  Adds a custom blocked word for this server.

- `!removeword <word>`
  Removes a custom blocked word.

- `!wordlist`
  Shows custom blocked words.

- `!modhistory @user`
  Shows moderation case history for a user.

- `!whywarn`
  Shows what triggered the latest moderation action when available.

- `!purge <1-100>`
  Deletes messages in the current channel.

- `!slowmode <0-21600>`
  Changes slowmode for the current channel.

### AI Replies
- `!aireplies on/off`
  Enables or disables mention-based AI replies.

### Whitelist / Staff Safety
- `!whitelist add @user`
  Protects a trusted user from automod/security actions.

- `!whitelist remove @user`
  Removes a user from whitelist.

- `!whitelist list`
  Shows whitelisted users.

### Security
- `!securitystatus`
  Shows security settings and thresholds.

- `!antiraid on/off`
  Enables or disables anti-raid.

- `!antinuke on/off`
  Enables or disables anti-nuke.

- `!antilink on/off`
  Enables or disables anti-link.

- `!securitylogs on/off`
  Enables or disables security log messages.

- `!raidlimit <2-50>`
  Sets how many joins in the window trigger anti-raid.

- `!raidwindow <3-120>`
  Sets the time window used by anti-raid and anti-nuke trackers.

- `!nukelimit <2-20>`
  Sets destructive action threshold for anti-nuke.

- `!createlimit <2-30>`
  Sets channel creation spam threshold.

- `!securityselftest status`
  Shows available security self-test modes.

- `!securityselftest raid`
  Simulates raid alert logging.

- `!securityselftest antilink`
  Simulates anti-link logging.

- `!securityselftest nuke-dry`
  Simulates anti-nuke logging without changing channels.

- `!securityselftest lockdown`
  Disabled for safety. Do not use in production servers.

- `!panic`
  Emergency-only lockdown. Hides non-admin access across roles and member overrides.

- `!unlock`
  Emergency recovery command after `!panic` or automatic lockdown.

### Levels Admin
- `!setlevelrole <level> @role`
  Gives a role automatically when users reach a level.

- `!removelevelrole <level>`
  Removes a level reward mapping.

- `!levelrewards`
  Shows configured level reward roles.

### Ticket Setup
- `!ticketsetup`
  Shows current ticket configuration.

- `!setticketcategory <category>`
  Sets the category for new tickets.

- `!setticketlog #channel`
  Sets the ticket log/transcript channel.

- `!setsupportrole @role`
  Sets the support role to ping in tickets.

- `!closeticket <reason>`
  Closes a ticket and logs transcript.

### Giveaway Admin
- `!endgiveaway <message_id>`
  Ends a giveaway early.

- `!reroll <message_id>`
  Picks a new winner.

### Welcome / Goodbye
- `!welcomesetup`
  Shows current welcome configuration.

- `!setwelcome #channel`
  Sets the welcome message channel.

- `!setgoodbye #channel`
  Sets the goodbye message channel.

- `!setautorole @role`
  Sets autorole for new members.

- `!welcome on/off`
  Enables or disables welcome messages.

- `!goodbye on/off`
  Enables or disables goodbye messages.

- `!setwelcometext <template>`
  Sets a custom welcome template.

- `!setgoodbyetext <template>`
  Sets a custom goodbye template.

- `!welcomevars`
  Shows available template variables.

### Announcements / Utility
- `!announce #channel <message>`
  Sends an announcement embed.

- `!botstats`
  Shows bot statistics.

## Voice Commands

Voice hosting depends on the server/node environment.
On your current host, voice may time out even if the rest of the bot works.

- `!join`
  Attempts to join your voice channel.

- `!leave`
  Leaves voice and disables 24/7 mode.

- `!247`
  Enables 24/7 reconnect mode for the current voice channel.

- `!stop`
  Disables 24/7 mode.

- `!vcstatus`
  Shows current 24/7 voice status.

- `!vcdebug`
  Shows voice debug information.

## Recommended Main Server Setup
- `!setlog #logs`
- `!automod on`
- `!antiraid on`
- `!antinuke on`
- `!antilink on`
- `!securitylogs on`
- `!raidlimit 5`
- `!raidwindow 10`
- `!nukelimit 2`
- `!createlimit 4`
- `!whitelist add @trustedAdmin`
- `!welcomesetup`
- `!ticketsetup`

## Important Production Notes
- Test `!securityselftest lockdown` only in a dummy server.
- For main servers, use `raid`, `antilink`, and `nuke-dry` tests only.
- Voice is the only subsystem still dependent on host support.
