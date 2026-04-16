import asyncio
from dataclasses import dataclass
from typing import Dict, List

import discord
from discord import app_commands
from discord.ext import commands

from onboarding_config import (
    CLIENT_ID,
    COMPLETION_ROLE_ID,
    MAIN_BOT_KEY,
    GUILD_ID,
    ONBOARDING_CHANNEL_ID,
    ONBOARDING_QUESTIONS,
)


@dataclass
class PendingOnboarding:
    member_id: int
    question_index: int


intents = discord.Intents.default()
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)
state: Dict[int, PendingOnboarding] = {}


def get_channel_id() -> int:
    if not ONBOARDING_CHANNEL_ID:
        raise RuntimeError('Set ONBOARDING_CHANNEL_ID in onboarding_config.py')
    return int(ONBOARDING_CHANNEL_ID)


def get_guild_id() -> int:
    if not GUILD_ID:
        raise RuntimeError('Set ONBOARDING_GUILD_ID in onboarding_config.py')
    return int(GUILD_ID)


def get_client_id() -> int:
    if not CLIENT_ID:
        raise RuntimeError('Set ONBOARDING_CLIENT_ID in onboarding_config.py')
    return int(CLIENT_ID)


class OnboardingView(discord.ui.View):
    def __init__(self, member_id: int, question_index: int, options: List[dict], placeholder: str):
        super().__init__(timeout=600)
        self.member_id = member_id
        self.question_index = question_index
        select_options = [
            discord.SelectOption(
                label=opt['label'],
                value=opt['value'],
                description=opt.get('description') or None,
            )
            for opt in options
        ]
        self.add_item(OnboardingSelect(select_options, placeholder))


class OnboardingSelect(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption], placeholder: str):
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        message_id = interaction.message.id if interaction.message else None
        pending = state.get(message_id)
        if not pending:
            await interaction.response.send_message('This onboarding session expired. Ask a staff member to run /start-onboarding again.', ephemeral=True)
            return
        if interaction.user.id != pending.member_id:
            await interaction.response.send_message('Only the tagged member can answer this.', ephemeral=True)
            return

        question = ONBOARDING_QUESTIONS[pending.question_index]
        selected_value = self.values[0]
        selected_option = next((opt for opt in question['options'] if opt['value'] == selected_value), None)
        if not selected_option:
            await interaction.response.send_message('That option is no longer available.', ephemeral=True)
            return

        role_id = selected_option.get('role_id')
        if role_id:
            role = interaction.guild.get_role(int(role_id)) if interaction.guild else None
            if role:
                try:
                    await interaction.user.add_roles(role, reason='Onboarding selection')
                except discord.Forbidden:
                    pass

        next_index = pending.question_index + 1
        if next_index >= len(ONBOARDING_QUESTIONS):
            if COMPLETION_ROLE_ID:
                role = interaction.guild.get_role(int(COMPLETION_ROLE_ID)) if interaction.guild else None
                if role:
                    try:
                        await interaction.user.add_roles(role, reason='Onboarding completion')
                    except discord.Forbidden:
                        pass
            await interaction.response.send_message('Onboarding complete. Welcome!', ephemeral=True)
            state.pop(message_id, None)
            return

        await interaction.response.send_message('Saved! Please answer the next question below.', ephemeral=True)
        await send_question(interaction.guild, interaction.user, next_index)
        state.pop(message_id, None)


async def send_question(guild: discord.Guild, member: discord.Member, question_index: int):
    channel = guild.get_channel(get_channel_id())
    if not channel:
        return

    question = ONBOARDING_QUESTIONS[question_index]
    embed = discord.Embed(
        title='Onboarding',
        description=f"{member.mention}\n\n{question['prompt']}",
        color=discord.Color.blurple(),
    )

    view = OnboardingView(
        member_id=member.id,
        question_index=question_index,
        options=question['options'],
        placeholder=question.get('placeholder', 'Choose an option'),
    )

    message = await channel.send(embed=embed, view=view)
    state[message.id] = PendingOnboarding(member_id=member.id, question_index=question_index)


@bot.event
async def on_ready():
    print(f'[ONBOARDING] Logged in as {bot.user}')
    try:
        guild = discord.Object(id=get_guild_id())
        await bot.tree.sync(guild=guild)
        print('[ONBOARDING] Synced slash commands')
    except Exception as exc:
        print(f'[ONBOARDING] Slash sync error: {exc}')


@bot.event
async def on_member_join(member: discord.Member):
    await asyncio.sleep(1)
    await send_question(member.guild, member, 0)


@bot.tree.command(name='start-onboarding', description='Send onboarding questions to a member.')
@app_commands.describe(member='Member to start onboarding for')
async def start_onboarding(interaction: discord.Interaction, member: discord.Member):
    await send_question(interaction.guild, member, 0)
    await interaction.response.send_message(f'Onboarding started for {member.mention}.', ephemeral=True)


if __name__ == '__main__':
    if not MAIN_BOT_KEY:
        raise RuntimeError('Set ONBOARDING_MAIN_BOT_KEY in onboarding_config.py')
    bot.run(MAIN_BOT_KEY)

