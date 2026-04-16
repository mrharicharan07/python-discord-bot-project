"""Standalone payment bot for ZORO X CHEATS."""

from __future__ import annotations

import io
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

import discord
import qrcode
from discord import app_commands
from discord.ext import commands

from config import (
    PAYMENT_ALLOWED_USER_IDS,
    PAYMENT_BUSINESS_NAME,
    PAYMENT_COLOR,
    PAYMENT_MAIN_BOT_KEY,
    PAYMENT_GUILD_ID,
    PAYMENT_NOTE,
    PAYMENT_PAID_COLOR,
    PAYMENT_PREFIX,
    PAYMENT_RECEIPT_FOOTER,
    PAYMENT_UPI_ID,
)

ALLOWED_USER_IDS = {
    user_id.strip()
    for user_id in PAYMENT_ALLOWED_USER_IDS.split(',')
    if user_id.strip()
}
PAYMENT_COLOR_VALUE = int(PAYMENT_COLOR, 16)
PAYMENT_PAID_COLOR_VALUE = int(PAYMENT_PAID_COLOR, 16)
AMOUNT_RE = re.compile(r'INR\s+([0-9][0-9,]*\.?[0-9]*)')


@dataclass
class PaymentCard:
    amount: float
    payer_label: str
    requested_by: str
    order_note: str | None


class MarkPaidView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label='Mark Paid', style=discord.ButtonStyle.success, custom_id='payment_mark_paid')
    async def mark_paid(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not is_allowed_user(interaction.user.id):
            await interaction.response.send_message('You are not allowed to use this payment bot.', ephemeral=True)
            return

        card = parse_payment_card(interaction.message)
        if card is None:
            await interaction.response.send_message('Could not read this payment card. Create a new one.', ephemeral=True)
            return

        receipt_id = create_receipt_id()
        paid_at = datetime.now(timezone.utc)
        receipt_embed = build_receipt_embed(
            amount=card.amount,
            payer=card.payer_label,
            receipt_id=receipt_id,
            note=card.order_note or 'Auto receipt created from payment request.',
            requested_by=interaction.user.display_name,
            paid_at=paid_at,
        )

        await interaction.response.send_message(embed=receipt_embed, allowed_mentions=discord.AllowedMentions(users=True))
        try:
            await interaction.message.delete()
        except discord.HTTPException:
            pass


intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.dm_messages = True

bot = commands.Bot(command_prefix=PAYMENT_PREFIX, intents=intents, help_command=None)


@bot.event
async def on_ready() -> None:
    bot.add_view(MarkPaidView())
    print(f'[PAYMENT BOT] Logged in as {bot.user}')

    try:
        if PAYMENT_GUILD_ID:
            guild = discord.Object(id=int(PAYMENT_GUILD_ID))
            await bot.tree.sync(guild=guild)
            print(f'[PAYMENT BOT] Synced slash commands to guild {PAYMENT_GUILD_ID}')
        else:
            await bot.tree.sync()
            print('[PAYMENT BOT] Synced global slash commands')
    except Exception as exc:
        print(f'[PAYMENT BOT] Slash sync error: {exc}')


@bot.command(name='pay')
async def pay(ctx: commands.Context, amount: str | None = None, target: discord.User | None = None, *, note: str | None = None) -> None:
    if not is_allowed_user(ctx.author.id):
        await ctx.send('You are not allowed to use this payment bot.')
        return

    parsed_amount = parse_amount(amount)
    if parsed_amount is None or parsed_amount <= 0:
        await ctx.send(f'Usage: `{PAYMENT_PREFIX}pay <amount> [@user] [note]`')
        return

    payer_name = target.display_name if target else ctx.author.display_name
    payer_label = target.mention if target else ctx.author.display_name
    payment_embed = build_payment_embed(parsed_amount, payer_label, ctx.author.display_name, note)
    qr_file = build_qr_file(parsed_amount, payer_name, note)

    await ctx.send(
        content=f'Payment request created for {payer_label}. Amount: **INR {format_amount(parsed_amount)}**.',
        embed=payment_embed,
        file=qr_file,
        view=MarkPaidView(),
        allowed_mentions=discord.AllowedMentions(users=True),
    )


@bot.command(name='receipt')
async def receipt(ctx: commands.Context, amount: str | None = None, payer: str | None = None, receipt_id: str | None = None, *, note: str | None = None) -> None:
    if not is_allowed_user(ctx.author.id):
        await ctx.send('You are not allowed to use this payment bot.')
        return

    parsed_amount = parse_amount(amount)
    if parsed_amount is None or not payer or not receipt_id:
        await ctx.send(f'Usage: `{PAYMENT_PREFIX}receipt <amount> <payer> <receipt_id> [note]`')
        return

    embed = build_receipt_embed(
        amount=parsed_amount,
        payer=payer,
        receipt_id=receipt_id,
        note=note,
        requested_by=ctx.author.display_name,
        paid_at=datetime.now(timezone.utc),
    )
    await ctx.send(embed=embed)


@bot.command(name='payhelp')
async def payhelp(ctx: commands.Context) -> None:
    if not is_allowed_user(ctx.author.id):
        await ctx.send('You are not allowed to use this payment bot.')
        return

    embed = discord.Embed(title='Payment Bot Help', color=PAYMENT_COLOR_VALUE)
    embed.add_field(name='Create QR', value=f'`{PAYMENT_PREFIX}pay 600 @user`', inline=False)
    embed.add_field(name='Manual receipt', value=f'`{PAYMENT_PREFIX}receipt 600 payer RECEIPT123 paid`', inline=False)
    embed.add_field(name='Auto receipt', value='Use `Mark Paid` under the QR card.', inline=False)
    await ctx.send(embed=embed)


@bot.command(name='sync')
async def sync(ctx: commands.Context) -> None:
    if not is_allowed_user(ctx.author.id):
        await ctx.send('You are not allowed to use this payment bot.')
        return
    try:
        if PAYMENT_GUILD_ID:
            guild = discord.Object(id=int(PAYMENT_GUILD_ID))
            await bot.tree.sync(guild=guild)
            await ctx.send(f'Slash commands synced to guild {PAYMENT_GUILD_ID}.')
        else:
            await bot.tree.sync()
            await ctx.send('Slash commands synced globally.')
    except Exception as exc:
        await ctx.send(f'Slash sync error: {exc}')


@bot.tree.command(name='pay', description='Generate a UPI payment QR with an amount.')
@app_commands.describe(amount='Amount in INR', user='User who should pay', note='Optional order note')
async def slash_pay(interaction: discord.Interaction, amount: float, user: discord.User | None = None, note: str | None = None) -> None:
    if not is_allowed_user(interaction.user.id):
        await interaction.response.send_message('You are not allowed to use this payment bot.', ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message('Enter a valid amount.', ephemeral=True)
        return

    payer_name = user.display_name if user else interaction.user.display_name
    payer_label = user.mention if user else interaction.user.display_name
    payment_embed = build_payment_embed(amount, payer_label, interaction.user.display_name, note)
    qr_file = build_qr_file(amount, payer_name, note)

    await interaction.response.send_message(
        content=f'Payment request created for {payer_label}. Amount: **INR {format_amount(amount)}**.',
        embed=payment_embed,
        file=qr_file,
        view=MarkPaidView(),
        allowed_mentions=discord.AllowedMentions(users=True),
    )


@bot.tree.command(name='receipt', description='Post a payment receipt embed.')
@app_commands.describe(amount='Amount in INR', payer='Payer name', receipt_id='Receipt ID', note='Optional note')
async def slash_receipt(
    interaction: discord.Interaction,
    amount: float,
    payer: str,
    receipt_id: str,
    note: str | None = None,
) -> None:
    if not is_allowed_user(interaction.user.id):
        await interaction.response.send_message('You are not allowed to use this payment bot.', ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message('Enter a valid amount.', ephemeral=True)
        return

    embed = build_receipt_embed(
        amount=amount,
        payer=payer,
        receipt_id=receipt_id,
        note=note,
        requested_by=interaction.user.display_name,
        paid_at=datetime.now(timezone.utc),
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name='payhelp', description='Show payment bot commands.')
async def slash_payhelp(interaction: discord.Interaction) -> None:
    if not is_allowed_user(interaction.user.id):
        await interaction.response.send_message('You are not allowed to use this payment bot.', ephemeral=True)
        return

    embed = discord.Embed(title='Payment Bot Help', color=PAYMENT_COLOR_VALUE)
    embed.add_field(name='Create QR', value='`/pay amount:600 user:@member`', inline=False)
    embed.add_field(name='Manual receipt', value='`/receipt amount:600 payer:member receipt_id:ABC123`', inline=False)
    embed.add_field(name='Auto receipt', value='Use `Mark Paid` under the QR card.', inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


def is_allowed_user(user_id: int) -> bool:
    return str(user_id) in ALLOWED_USER_IDS


def parse_amount(raw: str | None) -> float | None:
    if raw is None:
        return None
    cleaned = raw.replace(',', '').strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def format_amount(amount: float) -> str:
    if amount.is_integer():
        return f'{int(amount):,}'
    return f'{amount:,.2f}'


def build_upi_uri(amount: float, payer_name: str, note: str | None) -> str:
    transaction_note = note or f'{PAYMENT_BUSINESS_NAME} payment by {payer_name}'
    return (
        'upi://pay?'
        f'pa={quote(PAYMENT_UPI_ID)}&'
        f'pn={quote(PAYMENT_BUSINESS_NAME)}&'
        f'am={amount:.2f}&'
        'cu=INR&'
        f'tn={quote(transaction_note)}'
    )


def build_qr_file(amount: float, payer_name: str, note: str | None) -> discord.File:
    image = qrcode.make(build_upi_uri(amount, payer_name, note))
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)
    return discord.File(buffer, filename='upi-payment-qr.png')


def build_payment_embed(amount: float, payer_label: str, requested_by: str, note: str | None) -> discord.Embed:
    embed = discord.Embed(title='UPI Payment QR', color=PAYMENT_COLOR_VALUE)
    embed.set_author(name=PAYMENT_BUSINESS_NAME)
    embed.description = (
        f'Pay INR {format_amount(amount)} to {PAYMENT_BUSINESS_NAME}\n'
        f'{PAYMENT_UPI_ID}\n\n'
        f'Note: {PAYMENT_NOTE}'
    )
    embed.add_field(name='Payer', value=payer_label, inline=True)
    embed.add_field(name='Amount', value=f'INR {format_amount(amount)}', inline=True)
    embed.add_field(name='Status', value='Pending', inline=True)
    if note:
        embed.add_field(name='Order Note', value=note, inline=False)
    embed.set_image(url='attachment://upi-payment-qr.png')
    embed.set_footer(text=f'{PAYMENT_RECEIPT_FOOTER} {requested_by}')
    embed.timestamp = datetime.now(timezone.utc)
    return embed


def build_receipt_embed(*, amount: float, payer: str, receipt_id: str, note: str | None, requested_by: str, paid_at: datetime) -> discord.Embed:
    embed = discord.Embed(title='Payment Receipt', description='Payment has been marked as received.', color=PAYMENT_PAID_COLOR_VALUE)
    embed.set_author(name=PAYMENT_BUSINESS_NAME)
    embed.add_field(name='Amount', value=f'INR {format_amount(amount)}', inline=True)
    embed.add_field(name='Payer', value=payer, inline=True)
    embed.add_field(name='Receipt ID', value=receipt_id, inline=False)
    embed.add_field(name='Status', value='Paid', inline=True)
    embed.add_field(name='Paid At', value=discord.utils.format_dt(paid_at, style='f'), inline=True)
    if note:
        embed.add_field(name='Note', value=note, inline=False)
    embed.set_footer(text=f'{PAYMENT_RECEIPT_FOOTER} {requested_by}')
    embed.timestamp = paid_at
    return embed


def create_receipt_id() -> str:
    return f'ZXC-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}'


def parse_payment_card(message: discord.Message | None) -> PaymentCard | None:
    if message is None or not message.embeds:
        return None

    embed = message.embeds[0]
    if embed.title != 'UPI Payment QR':
        return None

    amount = None
    payer_label = None
    order_note = None
    for field in embed.fields:
        if field.name == 'Amount':
            match = AMOUNT_RE.search(field.value)
            if match:
                amount = parse_amount(match.group(1))
        elif field.name == 'Payer':
            payer_label = field.value
        elif field.name == 'Order Note':
            order_note = field.value

    if amount is None or payer_label is None:
        return None

    requested_by = embed.footer.text.replace(f'{PAYMENT_RECEIPT_FOOTER} ', '', 1) if embed.footer.text else 'Unknown'
    return PaymentCard(
        amount=amount,
        payer_label=payer_label,
        requested_by=requested_by,
        order_note=order_note,
    )


if __name__ == '__main__':
    if not PAYMENT_MAIN_BOT_KEY:
        raise RuntimeError('Set PAYMENT_MAIN_BOT_KEY in payment_bot/config.py before starting.')
    bot.run(PAYMENT_MAIN_BOT_KEY)


