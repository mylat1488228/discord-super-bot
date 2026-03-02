import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import sqlite3
import random
import yt_dlp
import datetime
import os
from PIL import Image, ImageDraw, ImageFont
import io
import aiohttp
from mcstatus import JavaServer

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("DISCORD_TOKEN")
ADMINS = ["defaultpeople", "anyachkaaaaa"] 
FUNTIME_IP = "play.funtime.su"
HOLYWORLD_IP = "mc.holyworld.ru"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command('help')

# --- БАЗА ДАННЫХ ---
if os.path.exists("/app/data"):
    DB_PATH = "/app/data/server_data.db"
else:
    DB_PATH = "server_data.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS configs (
    guild_id INTEGER PRIMARY KEY,
    verify_role_id INTEGER,
    support_role_id INTEGER,
    ticket_category_id INTEGER,
    ticket_log_channel_id INTEGER,
    music_channel_id INTEGER,
    music_text_channel_id INTEGER,
    notification_channel_id INTEGER,
    welcome_channel_id INTEGER,
    leave_channel_id INTEGER,
    market_ft_channel_id INTEGER,
    market_hw_channel_id INTEGER,
    stats_category_id INTEGER,
    pvoice_category_id INTEGER,
    social_yt TEXT,
    social_tg TEXT,
    social_tt TEXT,
    social_twitch TEXT,
    shop_category_id INTEGER,
    payments_enabled INTEGER DEFAULT 1
)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS tickets (
    channel_id INTEGER PRIMARY KEY,
    author_id INTEGER,
    status TEXT,
    timestamp DATETIME
)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS voice_channels (
    voice_id INTEGER PRIMARY KEY,
    owner_id INTEGER
)''')
conn.commit()

def get_config(guild_id):
    cursor.execute("SELECT * FROM configs WHERE guild_id = ?", (guild_id,))
    return cursor.fetchone()

def update_config(guild_id, column, value):
    cursor.execute("SELECT guild_id FROM configs WHERE guild_id = ?", (guild_id,))
    if cursor.fetchone() is None: cursor.execute("INSERT INTO configs (guild_id) VALUES (?)", (guild_id,))
    cursor.execute(f"UPDATE configs SET {column} = ? WHERE guild_id = ?", (value, guild_id)); conn.commit()

# --- МУЗЫКА И КАРТИНКИ ---
async def create_banner(member, title_text, bg_filename):
    try: background = Image.open(bg_filename).convert("RGBA")
    except: background = Image.new("RGBA", (1000, 400), (20, 20, 60))
    background = background.resize((1000, 400))
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(member.display_avatar.url) as resp: avatar_bytes = await resp.read()
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
    except: avatar = Image.new("RGBA", (250, 250), (100, 100, 100))
    avatar = avatar.resize((250, 250))
    mask = Image.new("L", (250, 250), 0); draw_mask = ImageDraw.Draw(mask); draw_mask.ellipse((0, 0, 250, 250), fill=255)
    stroke = Image.new("RGBA", (260, 260), (0, 0, 0, 0)); draw_stroke = ImageDraw.Draw(stroke); draw_stroke.ellipse((0, 0, 260, 260), fill=None, outline=(0, 191, 255), width=5)
    output = background.copy(); output.paste(stroke, (50, 70), stroke); output.paste(avatar, (55, 75), mask)
    draw = ImageDraw.Draw(output)
    try: font_large = ImageFont.truetype("font.ttf", 80); font_small = ImageFont.truetype("font.ttf", 50)
    except: font_large = ImageFont.load_default(); font_small = ImageFont.load_default()
    draw.text((354, 104), title_text, fill="black", font=font_large); draw.text((354, 204), str(member), fill="black", font=font_small)
    draw.text((350, 100), title_text, fill=(255, 255, 255), font=font_large); draw.text((350, 200), str(member), fill=(0, 255, 255), font=font_small)
    buffer = io.BytesIO(); output.save(buffer, format="PNG"); buffer.seek(0)
    return discord.File(buffer, filename="welcome.png")

yt_dlp.utils.bug_reports_message = lambda: ''
ytdl_format_options = {'format': 'bestaudio/best', 'restrictfilenames': True, 'noplaylist': True, 'nocheckcertificate': True, 'ignoreerrors': False, 'logtostderr': False, 'quiet': True, 'no_warnings': True, 'default_search': 'auto', 'source_address': '0.0.0.0'}
ffmpeg_options = {'options': '-vn', 'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5): super().__init__(source, volume); self.data = data; self.title = data.get('title'); self.url = data.get('url')
    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        if not url.startswith("http"): url = f"ytsearch:{url}"
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data: data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# --- ПРИВАТНЫЕ ВОЙСЫ ---
class PrivateVoiceControl(discord.ui.View):
    def __init__(self, vc): super().__init__(timeout=None); self.vc = vc
    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="➕ Добавить людей", min_values=1, max_values=5, row=0)
    async def wu(self, i, s):
        res = cursor.execute("SELECT owner_id FROM voice_channels WHERE voice_id = ?", (self.vc.id,)).fetchone()
        if not res or res[0] != i.user.id: return await i.response.send_message("❌ Не владелец.", ephemeral=True)
        for u in s.values: await self.vc.set_permissions(u, connect=True, view_channel=True)
        await i.response.send_message(f"✅ Добавлены.", ephemeral=True)
    @discord.ui.button(label="🔒", style=discord.ButtonStyle.red, row=1)
    async def l(self, i, b): await self.vc.set_permissions(i.guild.default_role, connect=False); await i.response.send_message("🔒", ephemeral=True)
    @discord.ui.button(label="🔓", style=discord.ButtonStyle.green, row=1)
    async def u(self, i, b): await self.vc.set_permissions(i.guild.default_role, connect=True); await i.response.send_message("🔓", ephemeral=True)

class PrivateVoiceCreateModal(discord.ui.Modal, title='Создать комнату'):
    v_name = discord.ui.TextInput(label='Название', max_length=20)
    v_limit = discord.ui.TextInput(label='Лимит', placeholder='0 = безлимит', max_length=2, required=False)
    async def on_submit(self, i):
        c = get_config(i.guild.id)
        if not c or not c[13]: return await i.response.send_message("❌ Не настроено.", ephemeral=True)
        cat = i.guild.get_channel(c[13])
        try: lim = int(self.v_limit.value) if self.v_limit.value else 0
        except: lim = 0
        ow = {i.guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True), i.user: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, move_members=True)}
        vc = await i.guild.create_voice_channel(name=self.v_name.value, category=cat, user_limit=lim, overwrites=ow)
        cursor.execute("INSERT INTO voice_channels (voice_id, owner_id) VALUES (?, ?)", (vc.id, i.user.id)); conn.commit()
        if i.user.voice: await i.user.move_to(vc)
        await i.response.send_message(embed=discord.Embed(title=f"⚙️ {self.v_name.value}", color=discord.Color.gold()), view=PrivateVoiceControl(vc), ephemeral=True)

class PrivateVoiceView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="➕ Создать комнату", style=discord.ButtonStyle.blurple, custom_id="cpv")
    async def cr(self, i, b): await i.response.send_modal(PrivateVoiceCreateModal())

# --- РЫНОК ---
class MarketModal(discord.ui.Modal, title='Продажа'):
    item_name = discord.ui.TextInput(label='Товар')
    item_price = discord.ui.TextInput(label='Цена')
    item_desc = discord.ui.TextInput(label='Описание', style=discord.TextStyle.paragraph)
    item_photo = discord.ui.TextInput(label='Ссылка на фото', required=False)
    def __init__(self, m_type, c_id): super().__init__(); self.m_type=m_type; self.c_id=c_id
    async def on_submit(self, i):
        ch = i.guild.get_channel(self.c_id)
        if not ch: return await i.response.send_message("Ошибка канала", ephemeral=True)
        col = discord.Color.orange() if self.m_type == "FunTime" else discord.Color.blue()
        emb = discord.Embed(title=f"🛒 {self.m_type}", color=col, timestamp=datetime.datetime.now())
        emb.set_author(name=i.user.display_name, icon_url=i.user.display_avatar.url)
        emb.add_field(name="📦", value=self.item_name.value); emb.add_field(name="💰", value=self.item_price.value); emb.add_field(name="📝", value=self.item_desc.value, inline=False); emb.set_footer(text=f"Продавец: {i.user.name}")
        if self.item_photo.value: emb.set_image(url=self.item_photo.value)
        await ch.send(embed=emb); await i.response.send_message("✅", ephemeral=True)

class MarketSelectView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="FunTime", style=discord.ButtonStyle.danger, emoji="🧡", custom_id="m_ft")
    async def ft(self, i, b): c=get_config(i.guild.id); (await i.response.send_modal(MarketModal("FunTime", c[10]))) if c and c[10] else await i.response.send_message("Не настроено", ephemeral=True)
    @discord.ui.button(label="HolyWorld", style=discord.ButtonStyle.primary, emoji="💙", custom_id="m_hw")
    async def hw(self, i, b): c=get_config(i.guild.id); (await i.response.send_modal(MarketModal("HolyWorld", c[11]))) if c and c[11] else await i.response.send_message("Не настроено", ephemeral=True)

# --- МАГАЗИН И КОНКУРСЫ (НОВОЕ) ---
class ShopControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="✅ Оплатил", style=discord.ButtonStyle.green)
    async def paid(self, i, b): await i.response.send_message(f"{i.user.mention} оплатил! Ждите админа.", allowed_mentions=discord.AllowedMentions(users=True))
    @discord.ui.button(label="🔒 Закрыть", style=discord.ButtonStyle.red)
    async def close(self, i, b): 
        if i.user.guild_permissions.administrator: await i.channel.delete()
        else: await i.response.send_message("Только админ.", ephemeral=True)

async def create_shop_ch(i, prod, price):
    c = get_config(i.guild.id)
    if c and c[19] == 0: return await i.response.send_message("⛔ Платежи выключены.", ephemeral=True)
    cat = discord.utils.get(i.guild.categories, name="🛒 Заказы")
    if not cat: cat = await i.guild.create_category("🛒 Заказы")
    ow = {i.guild.default_role: discord.PermissionOverwrite(read_messages=False), i.user: discord.PermissionOverwrite(read_messages=True)}
    ch = await i.guild.create_text_channel(f"buy-{i.user.name}"[:20], category=cat, overwrites=ow)
    emb = discord.Embed(title="🧾 СЧЕТ", color=discord.Color.green())
    emb.add_field(name="Товар", value=prod); emb.add_field(name="Цена", value=price)
    emb.add_field(name="Реквизиты", value="Карта: `0000 0000 0000 0000` (Сбер)", inline=False)
    await ch.send(f"{i.user.mention}", embed=emb, view=ShopControlView())
    await i.response.send_message(f"✅ Перейдите в {ch.mention}", ephemeral=True)

class ShopAdsView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="1 день (без пинга) - 50р", style=discord.ButtonStyle.secondary)
    async def b1(self, i, b): await create_shop_ch(i, "Реклама 1д", "50 RUB")
    @discord.ui.button(label="1 день (с пингом) - 100р", style=discord.ButtonStyle.primary)
    async def b2(self, i, b): await create_shop_ch(i, "Реклама 1д + Ping", "100 RUB")

class ShopCatSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.select(placeholder="Выберите товар", options=[discord.SelectOption(label="Реклама", emoji="📢"), discord.SelectOption(label="Бот", emoji="🤖")])
    async def sel(self, i, s):
        if s.values[0] == "Реклама": await i.response.send_message("📢 Тарифы:", view=ShopAdsView(), ephemeral=True)
        else: await create_shop_ch(i, s.values[0], "Договорная")

class ToolsView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="🛒 Создать Магазин", style=discord.ButtonStyle.success)
    async def bs(self, i, b): ch=await i.guild.create_text_channel("shop"); await ch.send(embed=discord.Embed(title="Магазин", color=discord.Color.blue()), view=ShopCatSelect()); await i.response.send_message("✅", ephemeral=True)
    @discord.ui.button(label="🛑 Платежи ВКЛ/ВЫКЛ", style=discord.ButtonStyle.danger)
    async def bt(self, i, b): 
        c = get_config(i.guild.id); nv = 0 if c and c[19] == 1 else 1
        update_config(i.guild.id, "payments_enabled", nv); await i.response.send_message(f"Платежи: {nv}", ephemeral=True)

# --- АДМИН ПАНЕЛЬ ---
class SocialsModal(discord.ui.Modal, title="Ссылки"):
    yt = discord.ui.TextInput(label="YouTube", required=False); tg = discord.ui.TextInput(label="Telegram", required=False)
    async def on_submit(self, i): cursor.execute("UPDATE configs SET social_yt=?, social_tg=? WHERE guild_id=?", (self.yt.value, self.tg.value, i.guild.id)); conn.commit(); await i.response.send_message("✅", ephemeral=True)

class AdminSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="1. ЧАТ МУЗЫКИ", channel_types=[discord.ChannelType.text], row=0)
    async def s_m(self, i, s): update_config(i.guild.id, "music_text_channel_id", s.values[0].id); await i.response.send_message("✅", ephemeral=True)
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="2. РЫНОК FT", channel_types=[discord.ChannelType.text], row=1)
    async def s_f(self, i, s): update_config(i.guild.id, "market_ft_channel_id", s.values[0].id); await i.response.send_message("✅", ephemeral=True)
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="3. РЫНОК HW", channel_types=[discord.ChannelType.text], row=2)
    async def s_h(self, i, s): update_config(i.guild.id, "market_hw_channel_id", s.values[0].id); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🔊 Меню Приваток", style=discord.ButtonStyle.blurple, row=3)
    async def b_pv(self, i, b):
        c=await i.guild.create_category("Приватки"); update_config(i.guild.id, "pvoice_category_id", c.id)
        ch=await i.guild.create_text_channel("create-room"); await ch.send(embed=discord.Embed(title="Приватки", color=discord.Color.fuchsia()), view=PrivateVoiceView()); await i.response.send_message("✅", ephemeral=True)
    @discord.ui.button(label="🏪 Меню Рынка", style=discord.ButtonStyle.danger, row=3)
    async def b_m(self, i, b): ch=await i.guild.create_text_channel("create-ad"); await ch.send(embed=discord.Embed(title="Рынок", color=discord.Color.orange()), view=MarketSelectView()); await i.response.send_message("✅", ephemeral=True)
    @discord.ui.button(label="🛠 Инструменты (Магазин)", style=discord.ButtonStyle.secondary, row=3)
    async def b_tool(self, i, b): await i.response.send_message("Инструменты:", view=ToolsView(), ephemeral=True)

    @discord.ui.button(label="📈 Статистика", style=discord.ButtonStyle.gray, row=4)
    async def b_st(self, i, b):
        ow={i.guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True)}
        c=await i.guild.create_category("📊 СТАТИСТИКА", overwrites=ow, position=0)
        await i.guild.create_voice_channel("Загрузка...", category=c); await i.guild.create_voice_channel("Загрузка...", category=c)
        update_config(i.guild.id, "stats_category_id", c.id); await i.response.send_message("✅", ephemeral=True)
    @discord.ui.button(label="🛠 Верификация", style=discord.ButtonStyle.green, row=4)
    async def b_v(self, i, b):
        r=await i.guild.create_role(name="Verified", color=discord.Color.green()); update_config(i.guild.id, "verify_role_id", r.id)
        ow={i.guild.default_role:discord.PermissionOverwrite(read_messages=True, send_messages=False), r:discord.PermissionOverwrite(read_messages=False), i.guild.me:discord.PermissionOverwrite(read_messages=True)}
        ch=await i.guild.create_text_channel("verify", overwrites=ow); await ch.send(embed=discord.Embed(title="Верификация"), view=VerifyView()); await i.response.send_message("✅", ephemeral=True)
    @discord.ui.button(label="🎫 Тикеты", style=discord.ButtonStyle.primary, row=4)
    async def b_t(self, i, b): c=await i.guild.create_category("Support"); update_config(i.guild.id, "ticket_category_id", c.id); ch=await i.guild.create_text_channel("tickets", category=c); await ch.send(embed=discord.Embed(title="Тикеты"), view=TicketStartView()); await i.response.send_message("✅", ephemeral=True)

class VerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Верификация", style=discord.ButtonStyle.green, custom_id="vp")
    async def v(self, i, b): c=get_config(i.guild.id); r=i.guild.get_role(c[1]) if c else None; (await i.user.add_roles(r)) if r else None; await i.response.send_message("✅", ephemeral=True)

class TicketStartView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Тикет", style=discord.ButtonStyle.blurple, custom_id="ct")
    async def c(self, i, b):
        c=get_config(i.guild.id); cat=i.guild.get_channel(c[3])
        ch=await i.guild.create_text_channel(f"ticket-{random.randint(1,999)}", category=cat)
        cursor.execute("INSERT INTO tickets (channel_id, author_id) VALUES (?, ?)", (ch.id, i.user.id)); conn.commit()
        await ch.send(f"{i.user.mention}", embed=discord.Embed(title="Тикет"), view=TicketControlView()); await i.response.send_message("✅", ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Закрыть", style=discord.ButtonStyle.red, custom_id="clt")
    async def cl(self, i, b): await i.channel.delete()

# --- СЛЕШ КОМАНДЫ ---
async def check_music_channel(interaction):
    conf = get_config(interaction.guild.id)
    if conf and conf[6] and interaction.channel.id != conf[6]:
        chan = interaction.guild.get_channel(conf[6])
        await interaction.response.send_message(f"🚫 Идите в: {chan.mention}", ephemeral=True); return False
    return True

@bot.tree.command(name="play", description="Музыка")
async def slash_play(i: discord.Interaction, query: str):
    if not await check_music_channel(i): return
    await i.response.defer()
    if not i.user.voice: return await i.followup.send("Войс!")
    if not i.guild.voice_client: await i.user.voice.channel.connect()
    try: p=await YTDLSource.from_url(query, loop=bot.loop, stream=True); i.guild.voice_client.play(p); await i.followup.send(f"🎶 **{p.title}**")
    except: await i.followup.send("Ошибка")

@bot.tree.command(name="top_russia", description="Топ 100")
async def top_ru(i: discord.Interaction):
    if not await check_music_channel(i): return
    await i.response.defer(); 
    if not i.guild.voice_client: await i.user.voice.channel.connect()
    try: p=await YTDLSource.from_url("Топ 100 русских песен 2024 микс", loop=bot.loop, stream=True); i.guild.voice_client.play(p); await i.followup.send(f"🇷🇺 **ТОП России**")
    except: await i.followup.send("Ошибка")

@tasks.loop(minutes=5)
async def update_stats_loop():
    cursor.execute("SELECT guild_id, stats_category_id FROM configs")
    for row in cursor.fetchall():
        try:
            g = bot.get_guild(row[0]); cat = g.get_channel(row[1])
            if not g or not cat: continue
            try: st_ft = (await (await JavaServer.async_lookup(FUNTIME_IP)).async_status()).players.online
            except: st_ft = "-"
            try: st_hw = (await (await JavaServer.async_lookup(HOLYWORLD_IP)).async_status()).players.online
            except: st_hw = "-"
            names = [f"💎 Souls Visuals", f"👥 Людей: {g.member_count}", f"🧡 FT: {st_ft}", f"💙 HW: {st_hw}"]
            for i, c in enumerate(cat.voice_channels):
                if i < 4: await c.edit(name=names[i])
        except: pass

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
    update_stats_loop.start()
    bot.add_view(VerifyView()); bot.add_view(TicketStartView()); bot.add_view(TicketControlView()); bot.add_view(AdminSelect()); bot.add_view(MarketSelectView()); bot.add_view(PrivateVoiceView()); bot.add_view(ShopCatSelect())

@bot.command()
async def setup(ctx):
    try:
        ow = {ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False), ctx.guild.me: discord.PermissionOverwrite(read_messages=True), ctx.author: discord.PermissionOverwrite(read_messages=True)}
        cat = await ctx.guild.create_category("BOT SETTINGS", overwrites=ow)
        ch = await ctx.guild.create_text_channel("admin-panel", category=cat)
        await ch.send(embed=discord.Embed(title="⚙️ Админ Панель"), view=AdminSelect())
        await ctx.send(f"✅ {ch.mention}")
    except: await ctx.send("Ошибка прав")

@bot.command()
async def reset(ctx):
    if ctx.author.guild_permissions.administrator: cursor.execute("DELETE FROM configs WHERE guild_id=?", (ctx.guild.id,)); conn.commit(); await ctx.send("✅ Сброс")

@bot.command()
async def admin(ctx):
    if ctx.author.guild_permissions.administrator: await ctx.send(embed=discord.Embed(title="⚙️ Админ Панель"), view=AdminSelect())

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel:
        cursor.execute("SELECT voice_id FROM voice_channels WHERE voice_id = ?", (before.channel.id,))
        if cursor.fetchone() and len(before.channel.members) == 0:
            await before.channel.delete(); cursor.execute("DELETE FROM voice_channels WHERE voice_id = ?", (before.channel.id,)); conn.commit()

@bot.event
async def on_member_join(member):
    c=get_config(member.guild.id)
    if c and c[8]: 
        ch=member.guild.get_channel(c[8])
        if ch: await ch.send(f"Привет {member.mention}", file=await create_banner(member, "WELCOME", "welcome_bg.png"))

@bot.event
async def on_member_remove(member):
    c=get_config(member.guild.id)
    if c and c[9]: 
        ch=member.guild.get_channel(c[9])
        if ch: await ch.send(f"Пока...", file=await create_banner(member, "GOODBYE", "goodbye_bg.png"))

bot.run(TOKEN)
