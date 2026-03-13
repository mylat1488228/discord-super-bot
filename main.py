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
import traceback
from mcstatus import JavaServer

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("DISCORD_TOKEN")
ADMINS = ["defaultpeople", "anyachkaaaaa"] 
FUNTIME_IP = "play.funtime.su"
HOLYWORLD_IP = "mc.holyworld.ru"
SERVER_NAME = "BENEZUELA"

# ЦВЕТА И СТИЛЬ
C_GOLD = 0xFFD700
IMG_MARKET = "https://i.pinimg.com/originals/e4/26/70/e426702edf874b181aced1e2fa5c6cde.gif"
IMG_VOICE = "https://i.pinimg.com/originals/2b/26/5c/2b265c37253337b32d47485773224795.gif"
IMG_VERIFY = "https://i.pinimg.com/originals/1c/54/f7/1c54f7b06d7723c21afc5035bf88a5ef.gif"

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
    market_ads_channel_id INTEGER,
    stats_category_id INTEGER,
    pvoice_category_id INTEGER,
    global_log_channel_id INTEGER,
    social_yt_id TEXT, 
    contest_channel_id INTEGER,
    media_channel_id INTEGER,
    clan_channel_id INTEGER
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

# --- УМНЫЙ ПОИСК КАНАЛОВ ---
async def get_or_create_channel(guild, name, category=None, overwrites=None, channel_type="text"):
    if channel_type == "text":
        ch = discord.utils.get(guild.text_channels, name=name)
        if not ch: ch = await guild.create_text_channel(name, category=category, overwrites=overwrites)
        else: 
            if category: await ch.edit(category=category)
            if overwrites: await ch.edit(overwrites=overwrites)
    else:
        ch = discord.utils.get(guild.categories, name=name)
        if not ch: ch = await guild.create_category(name, overwrites=overwrites)
    return ch

# --- ПРАВА ---
def get_public_perms(guild):
    return {
        guild.default_role: discord.PermissionOverwrite(view_channel=True, read_messages=True, read_message_history=True, send_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True)
    }
def get_write_perms(guild):
    c=get_config(guild.id); ver=guild.get_role(c[1]) if c and c[1] else None
    ow={guild.default_role: discord.PermissionOverwrite(view_channel=False), guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True)}
    if ver: ow[ver] = discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True, read_message_history=True, attach_files=True)
    return ow

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
    
    # КРУГЛАЯ АВАТАРКА
    mask = Image.new("L", (250, 250), 0); draw_mask = ImageDraw.Draw(mask); draw_mask.ellipse((0, 0, 250, 250), fill=255)
    
    W, H = background.size
    avatar_x = (W - 250) // 2
    avatar_y = (H - 250) // 2 - 40 
    
    output = background.copy()
    output.paste(avatar, (avatar_x, avatar_y), mask)
    draw = ImageDraw.Draw(output)
    
    try: font = ImageFont.truetype("font.ttf", 70)
    except: font = ImageFont.load_default()
    
    text = f"{title_text}\n{member.name}"
    _, _, w, h = draw.textbbox((0, 0), text, font=font)
    
    text_x = (W - w) // 2
    text_y = avatar_y + 260
    
    draw.multiline_text((text_x+4, text_y+4), text, fill="black", font=font, align="center")
    draw.multiline_text((text_x, text_y), text, fill="white", font=font, align="center")

    buffer = io.BytesIO(); output.save(buffer, format="PNG"); buffer.seek(0)
    return discord.File(buffer, filename="banner.png")

# --- МУЗЫКА ---
yt_dlp.utils.bug_reports_message = lambda: ''
ytdl_format_options = {'format': 'bestaudio/best', 'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s', 'restrictfilenames': True, 'noplaylist': True, 'nocheckcertificate': True, 'ignoreerrors': False, 'logtostderr': False, 'quiet': True, 'no_warnings': True, 'default_search': 'auto', 'source_address': '0.0.0.0', 'http_headers': {'User-Agent': 'Mozilla/5.0'}}
ffmpeg_options = {'options': '-vn', 'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5): super().__init__(source, volume); self.data = data; self.title = data.get('title'); self.url = data.get('url')
    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        if not url.startswith("http"): url = f"scsearch:{url}"
        data = await asyncio.wait_for(loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream)), timeout=12.0)
        if 'entries' in data: data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# --- ПРИВАТНЫЕ ВОЙСЫ ---
class PrivateVoiceControl(discord.ui.View):
    def __init__(self, vc): super().__init__(timeout=None); self.vc = vc
    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="➕ Добавить людей", min_values=1, max_values=10, row=0)
    async def wu(self, i, s):
        res = cursor.execute("SELECT owner_id FROM voice_channels WHERE voice_id = ?", (self.vc.id,)).fetchone()
        if not res or res[0] != i.user.id: return await i.response.send_message("❌ Не владелец.", ephemeral=True)
        for u in s.values: await self.vc.set_permissions(u, connect=True, view_channel=True)
        await i.response.send_message(f"✅ Добавлены.", ephemeral=True)
    @discord.ui.button(label="🔒 Закрыть", style=discord.ButtonStyle.red, row=1)
    async def l(self, i, b): await self.vc.set_permissions(i.guild.default_role, connect=False); await i.response.send_message("🔒", ephemeral=True)
    @discord.ui.button(label="🔓 Открыть", style=discord.ButtonStyle.green, row=1)
    async def u(self, i, b): await self.vc.set_permissions(i.guild.default_role, connect=True); await i.response.send_message("🔓", ephemeral=True)

class PrivateVoiceCreateModal(discord.ui.Modal, title='Создать комнату'):
    v_name = discord.ui.TextInput(label='Название', max_length=20)
    v_limit = discord.ui.TextInput(label='Лимит', placeholder='0 = безлимит', max_length=2, required=False)
    async def on_submit(self, i):
        try:
            c = get_config(i.guild.id)
            if not c or not c[13]: return await i.response.send_message("❌ Не настроено.", ephemeral=True)
            cat = i.guild.get_channel(c[13])
            try: lim = int(self.v_limit.value) if self.v_limit.value else 0
            except: lim = 0
            ow = {i.guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True), i.user: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, move_members=True), i.guild.me: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, move_members=True)}
            vc = await i.guild.create_voice_channel(name=self.v_name.value, category=cat, user_limit=lim, overwrites=ow)
            cursor.execute("INSERT INTO voice_channels (voice_id, owner_id) VALUES (?, ?)", (vc.id, i.user.id)); conn.commit()
            if i.user.voice: await i.user.move_to(vc)
            await i.response.send_message(embed=discord.Embed(title=f"🔊 {self.v_name.value}", color=C_GOLD), view=PrivateVoiceControl(vc), ephemeral=True)
        except Exception as e: await i.response.send_message(f"Ошибка: {e}", ephemeral=True)

class PrivateVoiceView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="➕ Создать комнату", style=discord.ButtonStyle.blurple, custom_id="cpv_btn_new")
    async def cr(self, i, b): await i.response.send_modal(PrivateVoiceCreateModal())

# --- ВЕРИФИКАЦИЯ ---
class VerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Пройти Верификацию", style=discord.ButtonStyle.green, custom_id="vp_btn_new")
    async def v(self, i, b):
        try:
            c=get_config(i.guild.id); r=i.guild.get_role(c[1]) if c else None
            if not r: return await i.response.send_message("❌ Роль не настроена", ephemeral=True)
            if r in i.user.roles: return await i.response.send_message("✅ Уже есть", ephemeral=True)
            await i.user.add_roles(r); await i.response.send_message("✅ Доступ выдан!", ephemeral=True)
        except Exception as e: await i.response.send_message(f"Error: {e}", ephemeral=True)

# --- РЫНОК ---
class MarketModal(discord.ui.Modal, title='Продажа'):
    item_name = discord.ui.TextInput(label='Товар')
    item_price = discord.ui.TextInput(label='Цена')
    item_desc = discord.ui.TextInput(label='Описание', style=discord.TextStyle.paragraph)
    item_photo = discord.ui.TextInput(label='Фото (ссылка)', required=False)
    def __init__(self, m_type, c_id): super().__init__(); self.m_type=m_type; self.c_id=c_id
    async def on_submit(self, i):
        ch = i.guild.get_channel(self.c_id)
        col = discord.Color.orange() if "FT" in self.m_type else discord.Color.blue()
        emb = discord.Embed(title=f"🛒 {self.m_type}", color=col, timestamp=datetime.datetime.now())
        emb.set_author(name=i.user.display_name, icon_url=i.user.display_avatar.url)
        emb.add_field(name="📦", value=self.item_name.value); emb.add_field(name="💰", value=self.item_price.value); emb.add_field(name="📝", value=self.item_desc.value, inline=False); emb.set_footer(text=f"Продавец: {i.user.name}")
        if self.item_photo.value: emb.set_image(url=self.item_photo.value)
        await ch.send(embed=emb); await i.response.send_message("✅", ephemeral=True)

class MarketSelectView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="FunTime", style=discord.ButtonStyle.danger, emoji="🧡", custom_id="m_ft_btn")
    async def ft(self, i, b): c=get_config(i.guild.id); (await i.response.send_modal(MarketModal("Рынок FT", c[10]))) if c and c[10] else await i.response.send_message("Не настроено", ephemeral=True)
    @discord.ui.button(label="HolyWorld", style=discord.ButtonStyle.primary, emoji="💙", custom_id="m_hw_btn")
    async def hw(self, i, b): c=get_config(i.guild.id); (await i.response.send_modal(MarketModal("Рынок HW", c[11]))) if c and c[11] else await i.response.send_message("Не настроено", ephemeral=True)

# --- АДМИН ПАНЕЛЬ ---
class AdminSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label="🛠 Верификация", style=discord.ButtonStyle.green, row=1)
    async def b_v(self, i, b):
        ch = await get_or_create_channel(i.guild, "verify", overwrites=get_public_perms(i.guild))
        embed = discord.Embed(title="🛡 ВЕРИФИКАЦИЯ", description="Нажмите кнопку, чтобы получить доступ.", color=C_GOLD)
        embed.set_image(url=IMG_VERIFY)
        await ch.purge(limit=5); await ch.send(embed=embed, view=VerifyView()); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🔊 Приватки", style=discord.ButtonStyle.blurple, row=1)
    async def b_pv(self, i, b):
        cat = await get_or_create_channel(i.guild, "🔊 Приватные Комнаты", channel_type="cat")
        update_config(i.guild.id, "pvoice_category_id", cat.id)
        ch = await get_or_create_channel(i.guild, "create-room", overwrites=get_write_perms(i.guild))
        embed = discord.Embed(title="🔊 ЛИЧНЫЙ ВОЙС", description="Создайте свою комнату и управляйте ею.", color=discord.Color.fuchsia())
        embed.set_image(url=IMG_VOICE)
        await ch.purge(limit=5); await ch.send(embed=embed, view=PrivateVoiceView()); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🏪 Рынок", style=discord.ButtonStyle.secondary, row=1)
    async def b_mm(self, i, b): 
        ch = await get_or_create_channel(i.guild, "create-ad", overwrites=get_write_perms(i.guild))
        embed = discord.Embed(title="🏪 ТОРГОВАЯ ПЛОЩАДКА", description="Выберите сервер для продажи:", color=discord.Color.orange())
        embed.set_image(url=IMG_MARKET)
        await ch.purge(limit=5); await ch.send(embed=embed, view=MarketSelectView()); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🎵 Музыка", style=discord.ButtonStyle.secondary, row=2)
    async def b_mc(self, i, b): 
        ch = await get_or_create_channel(i.guild, "ᴍᴜsɪᴄ🎶", overwrites=get_write_perms(i.guild))
        update_config(i.guild.id, "music_text_channel_id", ch.id)
        await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)

# --- СЛЕШ КОМАНДЫ ---
async def check_music_channel(interaction):
    conf = get_config(interaction.guild.id)
    if conf and conf[6] and interaction.channel.id != conf[6]:
        chan = interaction.guild.get_channel(conf[6])
        await interaction.response.send_message(f"🚫 Идите в: {chan.mention}", ephemeral=True); return False
    return True

@bot.tree.command(name="play", description="Включить музыку")
async def slash_play(i: discord.Interaction, query: str):
    if not await check_music_channel(i): return
    await i.response.defer()
    if not i.user.voice: return await i.followup.send("❌ Войс!")
    try: vc = i.guild.voice_client if i.guild.voice_client else await i.user.voice.channel.connect()
    except: return await i.followup.send("❌ Ошибка")
    try: 
        p = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
        if vc.is_playing(): vc.stop()
        vc.play(p); await i.followup.send(f"🎶 **{p.title}**")
    except: await i.followup.send("❌ Ошибка")

@bot.tree.command(name="top", description="Топ 100")
async def top_ru(i: discord.Interaction):
    await slash_play(i, "Топ 100 русских песен 2024 микс")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
    bot.add_view(VerifyView()); bot.add_view(AdminSelect()); bot.add_view(MarketSelectView()); bot.add_view(PrivateVoiceView())

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

@bot.command()
async def setup(ctx):
    if not ctx.guild.me.guild_permissions.administrator: return await ctx.send("❌ Дайте мне права АДМИНИСТРАТОРА!")
    try:
        # УМНЫЙ SETUP: НЕ ДУБЛИРУЕТ ПАНЕЛЬ
        cat = discord.utils.get(ctx.guild.categories, name="BOT SETTINGS")
        if not cat: cat = await ctx.guild.create_category("BOT SETTINGS")
        
        ch = discord.utils.get(ctx.guild.text_channels, name="admin-panel")
        if not ch: ch = await ctx.guild.create_text_channel("admin-panel", category=cat)
        
        await ch.purge(limit=5)
        await ch.send(embed=discord.Embed(title="⚙️ Админ Панель", description="Главное меню"), view=AdminSelect())
        await ctx.send(f"✅ Панель готова: {ch.mention}")
    except Exception as e: await ctx.send(f"Ошибка: {e}")

@bot.command()
async def reset(ctx):
    if ctx.author.guild_permissions.administrator: cursor.execute("DELETE FROM configs WHERE guild_id=?", (ctx.guild.id,)); conn.commit(); await ctx.send("✅ Сброс")

bot.run(TOKEN)
