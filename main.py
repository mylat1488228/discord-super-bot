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
import feedparser
from mcstatus import JavaServer

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("DISCORD_TOKEN")
# ТВОИ НИКИ (Точно как в профиле, с точкой если есть)
ADMINS = ["kunilus.", "grif228anki"] 
FUNTIME_IP = "play.funtime.su"
HOLYWORLD_IP = "mc.holyworld.ru"
SERVER_NAME = "BENEZUELA"

# ЦВЕТА
C_GOLD = 0xFFD700
C_RED = 0x990000
C_GREEN = 0x00FF00

# КАРТИНКИ ДЛЯ МЕНЮ
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
    clan_channel_id INTEGER,
    report_channel_id INTEGER,
    auction_channel_id INTEGER,
    last_video_id TEXT
)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 1000,
    reputation INTEGER DEFAULT 0,
    clan_id INTEGER DEFAULT 0,
    xp INTEGER DEFAULT 0,
    bio TEXT DEFAULT 'Игрок BENEZUELA'
)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS clans (
    clan_id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER,
    name TEXT,
    role_id INTEGER,
    category_id INTEGER,
    level INTEGER DEFAULT 1
)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS tickets (channel_id INTEGER PRIMARY KEY, author_id INTEGER)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS voice_channels (voice_id INTEGER PRIMARY KEY, owner_id INTEGER)''')
conn.commit()

def get_config(guild_id):
    cursor.execute("SELECT * FROM configs WHERE guild_id = ?", (guild_id,))
    res = cursor.fetchone()
    if not res:
        cursor.execute("INSERT INTO configs (guild_id) VALUES (?)", (guild_id,))
        conn.commit()
        return get_config(guild_id)
    return res

def update_config(guild_id, column, value):
    get_config(guild_id)
    cursor.execute(f"UPDATE configs SET {column} = ? WHERE guild_id = ?", (value, guild_id))
    conn.commit()

def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    if not res:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return get_user(user_id)
    return res

# --- УМНОЕ СОЗДАНИЕ КАНАЛОВ ---
async def get_or_create_channel(guild, name, category=None, overwrites=None, channel_type="text"):
    if channel_type == "text":
        ch = discord.utils.get(guild.text_channels, name=name)
        if not ch: ch = await guild.create_text_channel(name, category=category, overwrites=overwrites)
        else: await ch.edit(overwrites=overwrites, category=category)
    else:
        if channel_type == "cat":
            ch = discord.utils.get(guild.categories, name=name)
            if not ch: ch = await guild.create_category(name, overwrites=overwrites)
        else:
            ch = discord.utils.get(guild.voice_channels, name=name)
            if not ch: ch = await guild.create_voice_channel(name, category=category, overwrites=overwrites)
    return ch

async def get_or_create_role(guild, name, color):
    r = discord.utils.get(guild.roles, name=name)
    if not r: r = await guild.create_role(name=name, color=color, permissions=discord.Permissions(view_channel=True, read_messages=True, send_messages=True, connect=True, speak=True))
    return r

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
def get_read_only_perms(guild):
    c=get_config(guild.id); ver=guild.get_role(c[1]) if c and c[1] else None
    ow={guild.default_role: discord.PermissionOverwrite(view_channel=False), guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True)}
    if ver: ow[ver] = discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=False, read_message_history=True, add_reactions=True)
    return ow
def get_voice_perms(guild):
    c=get_config(guild.id); ver=guild.get_role(c[1]) if c and c[1] else None
    ow={guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False), guild.me: discord.PermissionOverwrite(view_channel=True, connect=True)}
    if ver: ow[ver] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True, stream=True)
    return ow
def get_newbie_perms(guild):
    return {
        guild.default_role: discord.PermissionOverwrite(view_channel=True, read_messages=True, read_message_history=True, send_messages=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True)
    }

# --- ВИЗУАЛ ---
def create_embed(title, desc, color=C_GOLD):
    emb = discord.Embed(title=title, description=desc, color=color)
    emb.set_footer(text="BENEZUELA SYSTEM", icon_url="https://i.imgur.com/8N4N8XW.png")
    return emb

async def create_banner(member, title_text, bg_filename):
    try: background = Image.open(bg_filename).convert("RGBA")
    except: background = Image.new("RGBA", (1000, 400), (20, 20, 20))
    background = background.resize((1000, 400))
    draw = ImageDraw.Draw(background)
    try: font = ImageFont.truetype("font.ttf", 90); font_small = ImageFont.truetype("font.ttf", 60)
    except: font = ImageFont.load_default(); font_small = ImageFont.load_default()
    W, H = background.size
    
    # Текст по центру
    text = f"{title_text}\n@{member.name}"
    draw.multiline_text((W/2+4, H/2-60+4), text, fill="black", font=font, anchor="mm", align="center")
    draw.multiline_text((W/2, H/2-60), text, fill="white", font=font, anchor="mm", align="center")

    buffer = io.BytesIO(); background.save(buffer, format="PNG"); buffer.seek(0)
    return discord.File(buffer, filename="banner.png")

async def create_profile_card(member):
    u = get_user(member.id)
    img = Image.new('RGB', (800, 400), color=(25, 25, 25))
    draw = ImageDraw.Draw(img)
    try: font = ImageFont.truetype("font.ttf", 40); font_s = ImageFont.truetype("font.ttf", 25)
    except: font = ImageFont.load_default(); font_s = ImageFont.load_default()

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(member.display_avatar.url) as resp: av_bytes = await resp.read()
        av = Image.open(io.BytesIO(av_bytes)).resize((150, 150))
        img.paste(av, (50, 50))
    except: pass

    draw.text((230, 60), f"{member.name}", font=font, fill=C_GOLD)
    draw.text((50, 250), f"💰 Баланс: {u[1]}$", font=font_s, fill="white")
    draw.text((350, 250), f"⭐ Репутация: {u[2]}", font=font_s, fill="white")
    draw.text((50, 350), f"📝 {u[5]}", font=font_s, fill="gray")

    buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
    return discord.File(buf, filename='profile.png')

# --- МУЗЫКА ---
yt_dlp.utils.bug_reports_message = lambda: ''
ytdl_format_options = {'format': 'bestaudio/best', 'restrictfilenames': True, 'noplaylist': True, 'nocheckcertificate': True, 'ignoreerrors': False, 'logtostderr': False, 'quiet': True, 'no_warnings': True, 'default_search': 'auto', 'source_address': '0.0.0.0', 'http_headers': {'User-Agent': 'Mozilla/5.0'}}
ffmpeg_options = {'options': '-vn', 'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)
class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5): super().__init__(source, volume); self.data = data; self.title = data.get('title'); self.url = data.get('url')
    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        if not url.startswith("http"): url = f"scsearch:{url}"
        data = await asyncio.wait_for(loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream)), timeout=15.0)
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
        c=get_config(i.guild.id); r=i.guild.get_role(c[1]) if c else None
        if r: await i.user.add_roles(r); await i.response.send_message("✅ Доступ выдан!", ephemeral=True)

# --- КАЗИНО И ПРОФИЛЬ ---
@bot.tree.command(name="profile", description="Профиль")
async def profile(i: discord.Interaction, member: discord.Member = None):
    member = member or i.user
    await i.response.defer()
    file = await create_profile_card(member)
    await i.followup.send(file=file)

@bot.tree.command(name="casino", description="Ставка")
async def casino(i: discord.Interaction, bet: int):
    u = get_user(i.user.id)
    if u[1] < bet: return await i.response.send_message("❌ Мало денег!", ephemeral=True)
    win = random.choice([True, False])
    new_bal = u[1] + bet if win else u[1] - bet
    cursor.execute("UPDATE users SET balance=? WHERE user_id=?", (new_bal, i.user.id)); conn.commit()
    col = C_GREEN if win else C_RED
    await i.response.send_message(embed=discord.Embed(title="🎰 CASINO", description=f"Баланс: {new_bal}$", color=col))

# --- РЫНОК И МАГАЗИН ---
class MarketModal(discord.ui.Modal, title='Продажа'):
    item_name = discord.ui.TextInput(label='Товар'); item_price = discord.ui.TextInput(label='Цена'); item_desc = discord.ui.TextInput(label='Описание', style=discord.TextStyle.paragraph); item_photo = discord.ui.TextInput(label='Фото', required=False)
    def __init__(self, m_type, c_id): super().__init__(); self.m_type=m_type; self.c_id=c_id
    async def on_submit(self, i):
        ch = i.guild.get_channel(self.c_id)
        emb = discord.Embed(title=f"🛒 {self.m_type}", color=discord.Color.orange())
        emb.add_field(name="📦", value=self.item_name.value); emb.add_field(name="💰", value=self.item_price.value); emb.add_field(name="📝", value=self.item_desc.value, inline=False); emb.set_footer(text=f"Продавец: {i.user.name}")
        if self.item_photo.value: emb.set_image(url=self.item_photo.value)
        await ch.send(embed=emb); await i.response.send_message("✅", ephemeral=True)

class MarketSelectView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="FunTime", style=discord.ButtonStyle.danger, emoji="🧡", custom_id="m_ft_btn")
    async def ft(self, i, b): c=get_config(i.guild.id); (await i.response.send_modal(MarketModal("Рынок FT", c[10]))) if c and c[10] else await i.response.send_message("Не настроено", ephemeral=True)
    @discord.ui.button(label="HolyWorld", style=discord.ButtonStyle.primary, emoji="💙", custom_id="m_hw_btn")
    async def hw(self, i, b): c=get_config(i.guild.id); (await i.response.send_modal(MarketModal("Рынок HW", c[11]))) if c and c[11] else await i.response.send_message("Не настроено", ephemeral=True)

class ShopControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="✅ Оплатил", style=discord.ButtonStyle.green)
    async def paid(self, i, b): await i.channel.send(f"🔔 {i.user.mention} подтвердил оплату! @here")
    @discord.ui.button(label="🔒 Закрыть", style=discord.ButtonStyle.red)
    async def close(self, i, b): await i.channel.delete()

async def create_shop_ch(i, prod, price):
    cat = discord.utils.get(i.guild.categories, name="🛒 ЗАКАЗЫ")
    if not cat: cat = await i.guild.create_category("🛒 ЗАКАЗЫ")
    ow = {i.guild.default_role: discord.PermissionOverwrite(read_messages=False), i.user: discord.PermissionOverwrite(read_messages=True), i.guild.me: discord.PermissionOverwrite(read_messages=True)}
    ch = await i.guild.create_text_channel(f"buy-{i.user.name}"[:20], category=cat, overwrites=ow)
    emb = discord.Embed(title="🧾 ОПЛАТА", color=C_GOLD)
    emb.add_field(name="Товар", value=prod); emb.add_field(name="Сумма", value=price)
    emb.add_field(name="Реквизиты", value="💳 СБП: `+7 900 000 00 00`\n🪙 USDT: `THxxxxxxxx`", inline=False)
    await ch.send(f"{i.user.mention}", embed=emb, view=ShopControlView())
    await i.response.send_message(f"✅ Перейдите в {ch.mention}", ephemeral=True)

class ShopAdsSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.select(placeholder="Срок", options=[discord.SelectOption(label="1 День", description="50R"), discord.SelectOption(label="7 Дней", description="250R")])
    async def sel(self, i, s): await create_shop_ch(i, f"Реклама {s.values[0]}", "По прайсу")

class ShopMainView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="📢 Реклама", style=discord.ButtonStyle.primary)
    async def ads(self, i, b): await i.response.send_message("Тарифы:", view=ShopAdsSelect(), ephemeral=True)
    @discord.ui.button(label="🤖 Купить Бота", style=discord.ButtonStyle.secondary)
    async def bot(self, i, b): await create_shop_ch(i, "Полный Бот", "1000 RUB")
    @discord.ui.button(label="🏰 Купить Клан", style=discord.ButtonStyle.success)
    async def clan(self, i, b): await create_shop_ch(i, "Создание Клана", "100 RUB")

# --- КЛАНЫ (БЕСПЛАТНО) ---
class ClanBuyModal(discord.ui.Modal, title="Создание Клана"):
    c_name = discord.ui.TextInput(label="Название")
    async def on_submit(self, i):
        r = await i.guild.create_role(name=f"Clan: {self.c_name.value}", color=discord.Color.random())
        await i.user.add_roles(r)
        cat = await i.guild.create_category(f"🏰 {self.c_name.value}")
        await i.guild.create_text_channel("chat", category=cat)
        cursor.execute("INSERT INTO clans (owner_id, name) VALUES (?, ?)", (i.user.id, self.c_name.value)); conn.commit()
        await i.response.send_message(f"✅ Клан **{self.c_name.value}** создан!", ephemeral=True)

class ClanView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Создать Клан (Бесплатно)", style=discord.ButtonStyle.success, custom_id="clan_create")
    async def cr(self, i, b): await i.response.send_modal(ClanBuyModal())

# --- АДМИН ПАНЕЛЬ ---
class AdminSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="📁 Создать Каналы", style=discord.ButtonStyle.success, row=0)
    async def b_all(self, i, b):
        await i.response.defer(ephemeral=True); g=i.guild
        r = await get_or_create_role(g, "Verified", C_GREEN); update_config(g.id, "verify_role_id", r.id)
        c_i = await get_or_create_channel(g, "INFO", channel_type="cat"); c_v = await get_or_create_channel(g, "VOICES", channel_type="cat")
        await get_or_create_channel(g, "ʀᴜʟᴇ📜", c_i, get_read_only_perms(g)); np = await get_or_create_channel(g, "ɴᴇᴡ-ᴘʟᴀʏᴇʀs", c_i, get_write_perms(g)); update_config(g.id, "welcome_channel_id", np.id)
        await get_or_create_channel(g, "ᴄᴏᴍᴍᴜɴɪᴄᴀᴛɪᴏɴ📕", c_i, get_write_perms(g))
        for x in range(1, 4): await get_or_create_channel(g, f"ᴠᴏɪsᴇs {x}🍀", c_v, get_voice_perms(g), "voice")
        c_m = await get_or_create_channel(g, "🛒 РЫНОК", channel_type="cat")
        f=await get_or_create_channel(g, "🧡┃рынок-ft", c_m, get_read_only_perms(g)); update_config(g.id, "market_ft_channel_id", f.id)
        h=await get_or_create_channel(g, "💙┃рынок-hw", c_m, get_read_only_perms(g)); update_config(g.id, "market_hw_channel_id", h.id)
        await i.followup.send("✅ Каналы созданы!")

    @discord.ui.button(label="🛠 Верификация", style=discord.ButtonStyle.green, row=1)
    async def b_v(self, i, b):
        ch=await get_or_create_channel(i.guild, "verify", overwrites=get_newbie_perms(i.guild))
        await ch.send(embed=create_embed("🛡 ВЕРИФИКАЦИЯ", "Нажми кнопку", C_GOLD), view=VerifyView())
        await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🔊 Приватки", style=discord.ButtonStyle.blurple, row=1)
    async def b_pv(self, i, b):
        c=await get_or_create_channel(i.guild, "🔊 Приватные Комнаты", channel_type="cat"); update_config(i.guild.id, "pvoice_category_id", c.id)
        ch=await get_or_create_channel(i.guild, "create-room", overwrites=get_write_perms(i.guild)); await ch.send(embed=create_embed("🔊 ЛИЧНЫЙ ВОЙС", "Создай комнату", 0xFF00FF), view=PrivateVoiceView())
        await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🏪 Рынок", style=discord.ButtonStyle.secondary, row=1)
    async def b_m(self, i, b):
        ch=await get_or_create_channel(i.guild, "create-ad", overwrites=get_write_perms(i.guild)); await ch.send(embed=create_embed("🏪 РЫНОК", "Выберите сервер", 0xFFA500), view=MarketSelectView())
        await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🛒 Магазин", style=discord.ButtonStyle.success, row=2)
    async def b_s(self, i, b):
        ch=await get_or_create_channel(i.guild, "shop", overwrites=get_public_perms(i.guild)); await ch.send(embed=create_embed("🛒 МАГАЗИН", "Товары:", C_GOLD), view=ShopMainView())
        await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🏰 Кланы", style=discord.ButtonStyle.success, row=2)
    async def b_cl(self, i, b):
        ch=await get_or_create_channel(i.guild, "create-clan", overwrites=get_public_perms(i.guild)); await ch.send(embed=create_embed("🏰 КЛАНЫ", "Создание клана", C_GOLD), view=ClanView())
        await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🎵 Музыка", style=discord.ButtonStyle.secondary, row=2)
    async def b_mc(self, i, b): 
        ch=await get_or_create_channel(i.guild, "ᴍᴜsɪᴄ🎶", overwrites=get_write_perms(i.guild)); update_config(i.guild.id, "music_text_channel_id", ch.id)
        await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)

    @discord.ui.button(label="🎫 Тикеты", style=discord.ButtonStyle.primary, row=3)
    async def b_t(self, i, b): 
        c=await get_or_create_channel(i.guild, "📩 Support", channel_type="cat"); l=await get_or_create_channel(i.guild, "ticket-logs", c, get_admin_perms(i.guild)); update_config(i.guild.id, "ticket_log_channel_id", l.id)
        update_config(i.guild.id, "ticket_category_id", c.id); ch=await get_or_create_channel(i.guild, "tickets", c, get_write_perms(i.guild)); await ch.send(embed=discord.Embed(title="Тикеты"), view=TicketStartView()); await i.response.send_message("✅", ephemeral=True)

class TicketStartView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Тикет", style=discord.ButtonStyle.blurple, custom_id="ct_btn")
    async def c(self, i, b):
        c=get_config(i.guild.id); cat=i.guild.get_channel(c[3]); ch=await i.guild.create_text_channel(f"ticket-{random.randint(1,999)}", category=cat)
        cursor.execute("INSERT INTO tickets (channel_id, author_id) VALUES (?, ?)", (ch.id, i.user.id)); conn.commit()
        await ch.set_permissions(i.user, read_messages=True, send_messages=True)
        if c and c[2]: 
            sup=i.guild.get_role(c[2]); 
            if sup: await ch.set_permissions(sup, read_messages=True, send_messages=True)
        await ch.send(f"{i.user.mention}", embed=discord.Embed(title="Тикет"), view=TicketControlView()); await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Закрыть", style=discord.ButtonStyle.red, custom_id="clt_btn")
    async def cl(self, i, b): await i.channel.delete()

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

@tasks.loop(minutes=5)
async def update_stats_loop():
    cursor.execute("SELECT guild_id, stats_category_id FROM configs")
    for row in cursor.fetchall():
        try:
            g = bot.get_guild(row[0]); cat = g.get_channel(row[1])
            if not g or not cat: continue
            names = [f"👑 {SERVER_NAME}", f"👥 Людей: {g.member_count}", f"🤝 Гарантов: 0"]
            for i, c in enumerate(cat.voice_channels):
                if i < 3: await c.edit(name=names[i])
        except: pass

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
    update_stats_loop.start()
    bot.add_view(VerifyView()); bot.add_view(TicketStartView()); bot.add_view(TicketControlView()); bot.add_view(AdminSelect()); bot.add_view(MarketSelectView()); bot.add_view(PrivateVoiceView()); bot.add_view(ShopMainView()); bot.add_view(ClanView())

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
        if ch: await ch.send(file=await create_banner(member, "WELCOME", "welcome_bg.png"))

@bot.command()
async def setup(ctx):
    if ctx.author.name not in ADMINS: return await ctx.send("⛔ Доступ запрещен")
    cat = await get_or_create_channel(ctx.guild, "BOT SETTINGS", channel_type="cat")
    ch = await get_or_create_channel(ctx.guild, "admin-panel", cat)
    await ch.purge(limit=5); await ch.send(embed=create_embed("⚙️ Админ Панель", "Главное меню"), view=AdminSelect())
    await ctx.send(f"✅ Панель создана: {ch.mention}")

@bot.command()
async def reset(ctx):
    if ctx.author.name in ADMINS: cursor.execute("DELETE FROM configs WHERE guild_id=?", (ctx.guild.id,)); conn.commit(); await ctx.send("✅ Сброс")

bot.run(TOKEN)
