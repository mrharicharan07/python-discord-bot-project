import discord
from discord.ext import commands

from config import MSG_BOT_TOKEN, PANEL_CHANNEL_ID

# ---------- INTENTS ----------
intents = discord.Intents.default()
intents.message_content = True

# ---------- BOT ----------
bot = commands.Bot(command_prefix='!', intents=intents)


def is_admin(member: discord.Member) -> bool:
    return member.guild_permissions.administrator or member.guild_permissions.manage_guild


@bot.event
async def on_ready():
    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name="Panel updates | Online",
    )
    await bot.change_presence(status=discord.Status.online, activity=activity)

    print(f'✅ {bot.user} is online and active')

    channel = bot.get_channel(PANEL_CHANNEL_ID)
    if not channel:
        print('❌ Channel not found')
        return

    async for msg in channel.history(limit=10):
        if msg.author == bot.user:
            print('⚠️ Panel already exists. Skipping.')
            return

    await send_panel(channel)
    print('✅ Panel message sent!')


async def send_panel(channel: discord.TextChannel) -> None:
    panel_message = """
# Member Guide for ZORO MANAGER

**ZORO MANAGER is here to make the server more fun, more organized, and safer.
**

*What members can use:*


```
!help                 ;      Shows the main bot command categories.

```

```
!rank                 ;      Shows your current level and XP progress.
```



```
!leaderboard          ;       Shows the most active members in the server.

```


```
!balance               ;      Shows how many coins you have.
```

```
!daily                ;       Claim your daily reward coins.
```

```
!work                  ;      Earn coins after cooldown.
```


```
!beg                   ;      Try your luck and get a small random amount of coins.
```


```
!shop                  ;      Shows the available items in the shop.
```

```
!buy <item>           ;       Buy an item from the shop.
```   


```
!inventory            ;        Shows the items you own.
```


```
!ticket              ;         Open a support ticket if you need help from staff.
``` 


```
!avatar [@user]        ;       Shows your avatar or another member’s avatar.
``` 


```
!userinfo [@user]     ;         Shows basic profile and server information.
``` 



**If AI replies are enabled:
Mention the bot like this:
@ZORO MANAGER hi**

```
Why this bot is here:
It gives members levels, coins, support tickets, utility commands, and a better server experience in one place.
```

```
Important:
Do not spam commands.
Some bad or suspicious messages may be filtered automatically for server safety.
If something is not working, open a ticket or contact staff.
```

||<@&1427211355227820134>||

    """

    await channel.send(panel_message)


@bot.command(name='panel')
async def panel(ctx: commands.Context) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_admin(ctx.author):
        await ctx.send('Administrator permission required.')
        return

    await send_panel(ctx.channel)


@bot.command(name='send')
async def send(ctx: commands.Context, channel: discord.TextChannel | None = None, *, message: str | None = None) -> None:
    if not isinstance(ctx.author, discord.Member) or not is_admin(ctx.author):
        await ctx.send('Administrator permission required.')
        return
    if channel is None or message is None:
        await ctx.send('Usage: `!send #channel your message`')
        return

    await channel.send(message)
    await ctx.send('✅ Message sent.')


if __name__ == '__main__':
    if not MSG_BOT_TOKEN or MSG_BOT_TOKEN == 'PASTE_MSG_BOT_TOKEN_HERE':
        raise RuntimeError('Set MSG_BOT_TOKEN in msg_bot/config.py before starting.')
    bot.run(MSG_BOT_TOKEN)
