import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import sqlite3
import random
import yt_dlp
import datetime
import feedparser
import os
from PIL import Image, ImageDraw, ImageFont
import io
import aiohttp
from mcstatus import JavaServer

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("DISCORD_TOKEN")
ADMINS = ["defaultpeople", "anyachkaaaaa"] 
FUNTIME_IP = "play.funtime.su"

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
    youtube_channel_url TEXT,
    youtube_last_video_id TEXT,
    notification_channel_id INTEGER,
    welcome_channel_id INTEGER,
    leave_channel_id INTEGER,
    market_ft_channel_id INTEGER,
    market_hw_channel_id INTEGER,
    stats_channel_id INTEGER,
    pvoice_category_id INTEGER
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

# --- ФУНКЦИИ БД ---
def get_config(guild_id):
    cursor.execute("SELECT * FROM configs WHERE guild_id = ?", (guild_id,))
    return cursor.fetchone()

def update_config(guild_id, column, value):
    cursor.execute("SELECT guild_id FROM configs WHERE guild_id = ?", (guild_id,))
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO configs (guild_id) VALUES (?)", (guild_id,))
    query = f"UPDATE configs SET {column} = ? WHERE guild_id = ?"
    cursor.execute(query, (value, guild_id))
    conn.commit()

# --- ГЕНЕРАТОР КАРТИНОК ---
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

# --- МУЗЫКА ---
yt_dlp.utils.bug_reports_message = lambda: ''
ytdl_format_options = {'format': 'bestaudio/best', 'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s', 'restrictfilenames': True, 'noplaylist': True, 'nocheckcertificate': True, 'ignoreerrors': False, 'logtostderr': False, 'quiet': True, 'no_warnings': True, 'default_search': 'auto', 'source_address': '0.0.0.0'}
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

# --- 1. ПРИВАТНЫЕ ВОЙСЫ ---
class PrivateVoiceControl(discord.ui.View):
    def __init__(self, voice_channel):
        super().__init__(timeout=None)
        self.voice_channel = voice_channel

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="➕ Добавить людей", min_values=1, max_values=10, row=0)
    async def whitelist_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        cursor.execute("SELECT owner_id FROM voice_channels WHERE voice_id = ?", (self.voice_channel.id,))
        res = cursor.fetchone()
        if not res or res[0] != interaction.user.id: return await interaction.response.send_message("❌ Вы не владелец.", ephemeral=True)
        for user in select.values: await self.voice_channel.set_permissions(user, connect=True, view_channel=True)
        await interaction.response.send_message(f"✅ Доступ выдан.", ephemeral=True)

    @discord.ui.button(label="🔒 Закрыть", style=discord.ButtonStyle.red, row=1)
    async def lock_room(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.voice_channel.set_permissions(interaction.guild.default_role, connect=False, view_channel=True)
        await interaction.response.send_message("🔒 Комната закрыта.", ephemeral=True)

    @discord.ui.button(label="🔓 Открыть", style=discord.ButtonStyle.green, row=1)
    async def unlock_room(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.voice_channel.set_permissions(interaction.guild.default_role, connect=True, view_channel=True)
        await interaction.response.send_message("🔓 Комната открыта.", ephemeral=True)

class PrivateVoiceCreateModal(discord.ui.Modal, title='Создать комнату'):
    v_name = discord.ui.TextInput(label='Название', max_length=20)
    v_limit = discord.ui.TextInput(label='Лимит (число)', placeholder='0 = безлимит', max_length=2, required=False)
    async def on_submit(self, interaction: discord.Interaction):
        conf = get_config(interaction.guild.id)
        if not conf or not conf[14]: return await interaction.response.send_message("❌ Категория не настроена.", ephemeral=True)
        category = interaction.guild.get_channel(conf[14])
        try: limit = int(self.v_limit.value) if self.v_limit.value else 0
        except: limit = 0
        overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True), interaction.user: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, move_members=True)}
        vc = await interaction.guild.create_voice_channel(name=self.v_name.value, category=category, user_limit=limit, overwrites=overwrites)
        cursor.execute("INSERT INTO voice_channels (voice_id, owner_id) VALUES (?, ?)", (vc.id, interaction.user.id)); conn.commit()
        if interaction.user.voice: await interaction.user.move_to(vc)
        await interaction.response.send_message(embed=discord.Embed(title=f"⚙️ {self.v_name.value}", color=discord.Color.gold()), view=PrivateVoiceControl(vc), ephemeral=True)

class PrivateVoiceView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="➕ Создать комнату", style=discord.ButtonStyle.blurple, custom_id="create_pvoice_btn")
    async def create_voice(self, interaction: discord.Interaction, button: discord.ui.Button): await interaction.response.send_modal(PrivateVoiceCreateModal())

# --- 2. СТАТИСТИКА ---
@tasks.loop(minutes=10)
async def update_stats():
    cursor.execute("SELECT guild_id, stats_channel_id FROM configs")
    for row in cursor.fetchall():
        try:
            guild = bot.get_guild(row[0])
            ch = guild.get_channel(row[1])
            if ch: await ch.edit(name=f"👥 Участников: {guild.member_count}")
        except: pass

# --- 3. РЫНОК ---
class MarketModal(discord.ui.Modal, title='Продажа'):
    item_name = discord.ui.TextInput(label='Товар', max_length=50)
    item_price = discord.ui.TextInput(label='Цена', max_length=20)
    item_desc = discord.ui.TextInput(label='Описание', style=discord.TextStyle.paragraph)
    item_photo = discord.ui.TextInput(label='Ссылка на фото (или пусто)', required=False)
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
    async def ft(self, i, b): 
        c=get_config(i.guild.id)
        if c and c[11]: await i.response.send_modal(MarketModal("FunTime", c[11]))
        else: await i.response.send_message("Не настроено (админ панель)", ephemeral=True)
    @discord.ui.button(label="HolyWorld", style=discord.ButtonStyle.primary, emoji="💙", custom_id="m_hw")
    async def hw(self, i, b): 
        c=get_config(i.guild.id)
        if c and c[12]: await i.response.send_modal(MarketModal("HolyWorld", c[12]))
        else: await i.response.send_message("Не настроено (админ панель)", ephemeral=True)

# --- АДМИН ПАНЕЛЬ (ИСПРАВЛЕННАЯ РАЗМЕТКА) ---
class AdminSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    # ROW 0: Только выпадающее меню FT (занимает всю строку)
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="1. Выберите канал РЫНКА FunTime", channel_types=[discord.ChannelType.text], row=0)
    async def s_ft(self, i, s): update_config(i.guild.id, "market_ft_channel_id", s.values[0].id); await i.response.send_message("✅ Рынок FT настроен", ephemeral=True)
    
    # ROW 1: Только выпадающее меню HW (занимает всю строку)
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="2. Выберите канал РЫНКА HolyWorld", channel_types=[discord.ChannelType.text], row=1)
    async def s_hw(self, i, s): update_config(i.guild.id, "market_hw_channel_id", s.values[0].id); await i.response.send_message("✅ Рынок HW настроен", ephemeral=True)

    # ROW 2: Только выпадающее меню Музыки (занимает всю строку)
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="3. Выберите канал МУЗЫКИ", channel_types=[discord.ChannelType.text], row=2)
    async def s_mus(self, i, s): update_config(i.guild.id, "music_channel_id", s.values[0].id); await i.response.send_message("✅ Музыкальный канал настроен", ephemeral=True)

    # ROW 3: Кнопки действий
    @discord.ui.button(label="📈 Статистика", style=discord.ButtonStyle.gray, row=3)
    async def btn_stat(self, i, b):
        overwrites = {i.guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True)}
        ch = await i.guild.create_voice_channel(f"👥 Участников: {i.guild.member_count}", overwrites=overwrites, position=0)
        update_config(i.guild.id, "stats_channel_id", ch.id)
        await i.response.send_message(f"✅ Стат-канал создан: {ch.name}", ephemeral=True)

    @discord.ui.button(label="🔊 Приватки", style=discord.ButtonStyle.blurple, row=3)
    async def btn_pv(self, i, b):
        cat = await i.guild.create_category("Приватные Комнаты")
        update_config(i.guild.id, "pvoice_category_id", cat.id)
        ch = await i.guild.create_text_channel("create-room")
        await ch.send(embed=discord.Embed(title="🔊 Личный Войс", description="Создайте свою комнату и управляйте ею.", color=discord.Color.fuchsia()), view=PrivateVoiceView())
        await i.response.send_message(f"✅ Меню приваток создано: {ch.mention}", ephemeral=True)

    @discord.ui.button(label="🏪 Меню Рынка", style=discord.ButtonStyle.danger, row=3)
    async def btn_m(self, i, b): 
        ch=await i.guild.create_text_channel("create-ad")
        await ch.send(embed=discord.Embed(title="🏪 Рынок", description="Выберите сервер для продажи:", color=discord.Color.orange()), view=MarketSelectView())
        await i.response.send_message(f"✅ Меню рынка создано: {ch.mention}", ephemeral=True)

    # ROW 4: Кнопки Верификации и Тикетов
    @discord.ui.button(label="🛠 Верификация", style=discord.ButtonStyle.green, row=4)
    async def btn_v(self, i, b):
        role=await i.guild.create_role(name="Verified", color=discord.Color.green())
        update_config(i.guild.id, "verify_role_id", role.id)
        ow={i.guild.default_role:discord.PermissionOverwrite(read_messages=True, send_messages=False), role:discord.PermissionOverwrite(read_messages=False), i.guild.me:discord.PermissionOverwrite(read_messages=True)}
        ch=await i.guild.create_text_channel("verify", overwrites=ow)
        await ch.send(embed=discord.Embed(title="Верификация"), view=VerifyView())
        try: await i.guild.default_role.edit(permissions=discord.Permissions(read_messages=False)); await i.response.send_message("✅ Верификация создана", ephemeral=True)
        except: await i.response.send_message("✅ Верификация создана (Скройте каналы вручную)", ephemeral=True)

    @discord.ui.button(label="🎫 Тикеты", style=discord.ButtonStyle.gray, row=4)
    async def btn_t(self, i, b): 
        c=await i.guild.create_category("Support")
        update_config(i.guild.id, "ticket_category_id", c.id)
        ch=await i.guild.create_text_channel("tickets", category=c)
        await ch.send(embed=discord.Embed(title="Тикеты"), view=TicketStartView())
        await i.response.send_message("✅ Тикеты созданы", ephemeral=True)

# --- VIEWS (Verify, Tickets) ---
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
@bot.tree.command(name="play", description="Включить музыку")
async def slash_play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    if not interaction.user.voice: return await interaction.followup.send("Зайдите в ГК!")
    if not interaction.guild.voice_client: await interaction.user.voice.channel.connect()
    try:
        player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
        if interaction.guild.voice_client.is_playing(): interaction.guild.voice_client.stop()
        interaction.guild.voice_client.play(player)
        await interaction.followup.send(f'🎶 Играет: **{player.title}**')
    except: await interaction.followup.send("Ошибка.")

@bot.tree.command(name="sell", description="Продать товар (можно с фото)")
async def slash_sell(interaction: discord.Interaction, market: str, price: str, item: str, photo: discord.Attachment = None):
    conf = get_config(interaction.guild.id)
    if not conf: return await interaction.response.send_message("Бот не настроен.", ephemeral=True)
    if market.lower() in ['ft', 'funtime']: ch_id = conf[11]; col = discord.Color.orange(); m_name="FunTime"
    elif market.lower() in ['hw', 'holyworld']: ch_id = conf[12]; col = discord.Color.blue(); m_name="HolyWorld"
    else: return await interaction.response.send_message("Выберите ft или hw", ephemeral=True)
    ch = interaction.guild.get_channel(ch_id)
    emb = discord.Embed(title=f"🛒 {m_name}", color=col)
    emb.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    emb.add_field(name="📦", value=item); emb.add_field(name="💰", value=price)
    emb.set_footer(text=f"Продавец: {interaction.user.name}")
    if photo: emb.set_image(url=photo.url)
    await ch.send(embed=emb); await interaction.response.send_message(f"✅", ephemeral=True)

@bot.tree.command(name="online", description="Онлайн FunTime")
async def slash_online(interaction: discord.Interaction):
    try: s = await JavaServer.async_lookup(FUNTIME_IP); st = await s.async_status(); await interaction.response.send_message(embed=discord.Embed(title="FunTime", description=f"Онлайн: {st.players.online}", color=discord.Color.orange()))
    except: await interaction.response.send_message("Сервер оффлайн")

# --- СИСТЕМА ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
    update_stats.start()
    bot.add_view(VerifyView()); bot.add_view(TicketStartView()); bot.add_view(TicketControlView()); bot.add_view(AdminSelect()); bot.add_view(MarketSelectView()); bot.add_view(PrivateVoiceView())

@bot.event
async def on_guild_join(guild):
    print(f"Joined {guild.name}")
    try:
        ow = {guild.default_role: discord.PermissionOverwrite(read_messages=False), guild.me: discord.PermissionOverwrite(read_messages=True)}
        if guild.owner: ow[guild.owner] = discord.PermissionOverwrite(read_messages=True)
        cat = await guild.create_category("BOT SETTINGS", overwrites=ow)
        ch = await guild.create_text_channel("admin-panel", category=cat)
        await ch.send(embed=discord.Embed(title="⚙️ Админ Панель"), view=AdminSelect())
    except Exception as e: print(e)

@bot.command()
async def setup(ctx):
    try:
        ow = {ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False), ctx.guild.me: discord.PermissionOverwrite(read_messages=True), ctx.author: discord.PermissionOverwrite(read_messages=True)}
        cat = await ctx.guild.create_category("BOT SETTINGS", overwrites=ow)
        ch = await ctx.guild.create_text_channel("admin-panel", category=cat)
        await ch.send(embed=discord.Embed(title="⚙️ Админ Панель"), view=AdminSelect())
        await ctx.send(f"✅ {ch.mention}")
    except Exception as e: await ctx.send(f"Ошибка: {e}")

@bot.command()
async def admin(ctx):
    if ctx.author.guild_permissions.administrator: await ctx.send(embed=discord.Embed(title="⚙️ Админ Панель"), view=AdminSelect())

@bot.command()
async def reset(ctx):
    if ctx.author.guild_permissions.administrator: cursor.execute("DELETE FROM configs WHERE guild_id=?", (ctx.guild.id,)); conn.commit(); await ctx.send("✅ Сброс")

# --- КОМАНДЫ ДЛЯ НАСТРОЙКИ КАРТИНОК ---
@bot.command()
async def set_welcome(ctx):
    """Установить этот канал для приветствий"""
    if ctx.author.guild_permissions.administrator:
        update_config(ctx.guild.id, "welcome_channel_id", ctx.channel.id)
        await ctx.send(f"✅ Приветствия будут здесь: {ctx.channel.mention}")

@bot.command()
async def set_leave(ctx):
    """Установить этот канал для прощаний"""
    if ctx.author.guild_permissions.administrator:
        update_config(ctx.guild.id, "leave_channel_id", ctx.channel.id)
        await ctx.send(f"✅ Прощания будут здесь: {ctx.channel.mention}")

# --- ОСТАЛЬНОЕ ---
@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel:
        cursor.execute("SELECT voice_id FROM voice_channels WHERE voice_id = ?", (before.channel.id,))
        if cursor.fetchone() and len(before.channel.members) == 0:
            await before.channel.delete(); cursor.execute("DELETE FROM voice_channels WHERE voice_id = ?", (before.channel.id,)); conn.commit()

@bot.event
async def on_member_join(member):
    c=get_config(member.guild.id)
    if c and c[9]: 
        ch=member.guild.get_channel(c[9])
        if ch: await ch.send(f"Привет {member.mention}", file=await create_banner(member, "WELCOME", "welcome_bg.png"))

@bot.event
async def on_member_remove(member):
    c=get_config(member.guild.id)
    if c and c[10]: 
        ch=member.guild.get_channel(c[10])
        if ch: await ch.send(f"Пока...", file=await create_banner(member, "GOODBYE", "goodbye_bg.png"))

bot.run(TOKEN)
