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
ADMINS = ["defaultpeople", "anyachkaaaaa", "kunilus.", "grif228anki"] 
FUNTIME_IP = "play.funtime.su"
HOLYWORLD_IP = "mc.holyworld.ru"
SERVER_NAME = "BENEZUELA"

# ЦВЕТА
C_GOLD = 0xFFD700
C_RED = 0x990000
C_GREEN = 0x00FF00
C_BLUE = 0x00BFFF

# КАРТИНКИ
IMG_MARKET = "https://i.pinimg.com/originals/e4/26/70/e426702edf874b181aced1e2fa5c6cde.gif"
IMG_VOICE = "https://i.pinimg.com/originals/2b/26/5c/2b265c37253337b32d47485773224795.gif"
IMG_VERIFY = "https://i.pinimg.com/originals/1c/54/f7/1c54f7b06d7723c21afc5035bf88a5ef.gif"
IMG_SHOP = "https://i.pinimg.com/originals/a5/37/67/a53767576572793267759d825c9772da.gif"
IMG_CLAN = "https://i.pinimg.com/originals/0c/3b/3a/0c3b3a2a5e5f58c7f7e7e5e7e5e7e5e7.gif"

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

# ТАБЛИЦЫ
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
    trade_category_id INTEGER,
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
    level INTEGER DEFAULT 1,
    balance INTEGER DEFAULT 0
)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS tickets (channel_id INTEGER PRIMARY KEY, author_id INTEGER)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS voice_channels (voice_id INTEGER PRIMARY KEY, owner_id INTEGER)''')
conn.commit()

# --- ФУНКЦИИ БД ---
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
    cursor.execute(f"UPDATE configs SET {column} = ? WHERE guild_id = ?", (value, guild_id)); conn.commit()

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
    if overwrites is None: overwrites = {}
    if channel_type == "text":
        ch = discord.utils.get(guild.text_channels, name=name)
        if not ch: ch = await guild.create_text_channel(name, category=category, overwrites=overwrites)
        else: 
            if category and ch.category != category: await ch.edit(category=category)
            await ch.edit(overwrites=overwrites)
    else:
        if channel_type == "cat":
            ch = discord.utils.get(guild.categories, name=name)
            if not ch: ch = await guild.create_category(name, overwrites=overwrites)
        else:
            ch = discord.utils.get(guild.voice_channels, name=name)
            if not ch: ch = await guild.create_voice_channel(name, category=category, overwrites=overwrites)
            else: await ch.edit(overwrites=overwrites)
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
def get_admin_perms(guild):
    return {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, read_messages=True)
    }
def get_newbie_perms(guild):
    return {
        guild.default_role: discord.PermissionOverwrite(view_channel=True, read_messages=True, read_message_history=True, send_messages=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True)
    }

# --- ВИЗУАЛ ---
def create_embed(title, description, color=C_GOLD, image=None): # ИСПРАВЛЕНО
    emb = discord.Embed(title=title, description=description, color=color)
    if image: emb.set_image(url=image)
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
    draw.multiline_text((W/2+4, H/2-60+4), text, fill="black", font=font, anchor="ms", align="center")
    draw.multiline_text((W/2, H/2-60), text, fill="white", font=font, anchor="ms", align="center")

    buffer = io.BytesIO(); background.save(buffer, format="PNG"); buffer.seek(0)
    return discord.File(buffer, filename="banner.png")

async def create_profile_card(member):
    u = get_user(member.id)
    # Клан
    clan_name = "Нет"
    if u[3]:
        cursor.execute("SELECT name FROM clans WHERE clan_id=?", (u[3],))
        res = cursor.fetchone()
        if res: clan_name = res[0]

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
    draw.text((230, 110), f"ID: {member.id}", font=font_s, fill="white")
    
    draw.text((50, 250), f"💰 Баланс: {u[1]}$", font=font_s, fill="white")
    draw.text((350, 250), f"⭐ Репутация: {u[2]}", font=font_s, fill="white")
    draw.text((50, 300), f"🏰 Клан: {clan_name}", font=font_s, fill="white")
    draw.text((50, 350), f"📝 {u[5]}", font=font_s, fill="gray")

    buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
    return discord.File(buf, filename='profile.png')

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
            await i.response.send_message(embed=create_embed(f"🔊 {self.v_name.value}", "Управление комнатой", C_GOLD), view=PrivateVoiceControl(vc), ephemeral=True)
        except Exception as e: await i.response.send_message(f"Ошибка: {e}", ephemeral=True)

class PrivateVoiceView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="➕ Создать комнату", style=discord.ButtonStyle.blurple, custom_id="cpv_btn_new")
    async def cr(self, i, b): await i.response.send_modal(PrivateVoiceCreateModal())

# --- ВЕРИФИКАЦИЯ ---
class VerifyModal(discord.ui.Modal, title='Верификация'):
    code_input = discord.ui.TextInput(label='Введите код', style=discord.TextStyle.short)
    def __init__(self, code, role_id): super().__init__(); self.generated_code = code; self.role_id = role_id; self.code_input.label = f"Введите: {code}"
    async def on_submit(self, i):
        if self.code_input.value == self.generated_code:
            try: await i.user.add_roles(i.guild.get_role(self.role_id)); await i.response.send_message("✅ Успех!", ephemeral=True)
            except: await i.response.send_message("❌ Ошибка прав", ephemeral=True)
        else: await i.response.send_message("❌ Неверно", ephemeral=True)

class VerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Пройти Верификацию", style=discord.ButtonStyle.green, custom_id="vp_btn_new")
    async def v(self, i, b):
        try:
            c=get_config(i.guild.id); r=i.guild.get_role(c[1]) if c else None
            if not r: return await i.response.send_message("❌ Роль не настроена", ephemeral=True)
            if r in i.user.roles: return await i.response.send_message("✅ Уже есть", ephemeral=True)
            await i.response.send_modal(VerifyModal(str(random.randint(1000, 9999)), c[1]))
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
        if not ch: return await i.response.send_message("Ошибка канала", ephemeral=True)
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

# --- МАГАЗИН И ОПЛАТА ---
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
    cat = await get_or_create_channel(i.guild, "🛒 ЗАКАЗЫ", channel_type="cat")
    ow = {i.guild.default_role: discord.PermissionOverwrite(read_messages=False), i.user: discord.PermissionOverwrite(read_messages=True), i.guild.me: discord.PermissionOverwrite(read_messages=True)}
    ch = await i.guild.create_text_channel(f"buy-{i.user.name}"[:20], category=cat, overwrites=ow)
    emb = discord.Embed(title="🧾 СЧЕТ", color=discord.Color.green())
    emb.add_field(name="Товар", value=prod); emb.add_field(name="Цена", value=price)
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

# --- ТРЕЙД ---
class DealControlView(discord.ui.View):
    def __init__(self, pid): super().__init__(timeout=None); self.pid = pid
    @discord.ui.button(label="✅ Успешно (+Rep)", style=discord.ButtonStyle.success)
    async def suc(self, i, b):
        cursor.execute("UPDATE users SET reputation = reputation + 1 WHERE user_id=?", (self.pid,)); conn.commit()
        await i.response.send_message(f"✅ Репутация повышена!"); await i.channel.delete()
    @discord.ui.button(label="⛔ Отмена", style=discord.ButtonStyle.danger)
    async def can(self, i, b): await i.channel.delete()

@bot.tree.command(name="trade", description="Безопасная сделка")
async def trade(i: discord.Interaction, member: discord.Member):
    cat = await get_or_create_channel(i.guild, "🤝 СДЕЛКИ", channel_type="cat")
    ow = {i.guild.default_role: discord.PermissionOverwrite(read_messages=False), i.user: discord.PermissionOverwrite(read_messages=True), member: discord.PermissionOverwrite(read_messages=True), i.guild.me: discord.PermissionOverwrite(read_messages=True)}
    ch = await i.guild.create_text_channel(f"trade-{i.user.name}", category=cat, overwrites=ow)
    await ch.send(f"{i.user.mention} {member.mention}", embed=create_embed("🤝 СДЕЛКА", "Обсудите условия.", C_GREEN), view=DealControlView(member.id))
    await i.response.send_message(f"✅ Чат создан: {ch.mention}", ephemeral=True)

# --- ПРОФИЛЬ, БИО, КАЗИНО, РЕПОРТ, АУКЦИОН ---
@bot.tree.command(name="profile", description="Профиль игрока")
async def profile(i: discord.Interaction, member: discord.Member = None):
    member = member or i.user
    await i.response.defer()
    file = await create_profile_card(member)
    await i.followup.send(file=file)

@bot.tree.command(name="bio", description="Изменить описание профиля")
async def bio(i: discord.Interaction, text: str):
    get_user(i.user.id) 
    cursor.execute("UPDATE users SET bio = ? WHERE user_id = ?", (text, i.user.id)); conn.commit()
    await i.response.send_message("✅ Био обновлено!", ephemeral=True)

@bot.tree.command(name="casino", description="Ставка")
async def casino(i: discord.Interaction, bet: int):
    u = get_user(i.user.id)
    if u[1] < bet: return await i.response.send_message("❌ Мало денег!", ephemeral=True)
    win = random.choice([True, False])
    new_bal = u[1] + bet if win else u[1] - bet
    cursor.execute("UPDATE users SET balance=? WHERE user_id=?", (new_bal, i.user.id)); conn.commit()
    col = C_GREEN if win else C_RED
    await i.response.send_message(embed=create_embed("🎰 CASINO", f"Баланс: {new_bal}$", col))

class ReportView(discord.ui.View):
    def __init__(self, user_id): super().__init__(timeout=None); self.uid = user_id
    @discord.ui.button(label="🔨 Бан", style=discord.ButtonStyle.danger)
    async def ban(self, i, b): await i.guild.ban(discord.Object(self.uid)); await i.channel.send("✅ Забанен")

@bot.tree.command(name="report", description="Пожаловаться")
async def report(i: discord.Interaction, user: discord.Member, reason: str):
    c = get_config(i.guild.id)
    if c and c[20]: # report
        ch = i.guild.get_channel(c[20])
        emb = create_embed("🚨 REPORT", f"На: {user.mention}\nПричина: {reason}", C_RED)
        await ch.send(embed=emb, view=ReportView(user.id))
        await i.response.send_message("✅ Отправлено.", ephemeral=True)
    else: await i.response.send_message("❌ Не настроено", ephemeral=True)

class AuctionView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="💰 Ставка (+1000$)", style=discord.ButtonStyle.success)
    async def bid(self, i, b): await i.response.send_message("✅ Ставка принята!", ephemeral=True)

@bot.tree.command(name="auction", description="Аукцион")
async def auction(i: discord.Interaction, item: str, price: int):
    c = get_config(i.guild.id)
    if c and c[21]: 
        ch = i.guild.get_channel(c[21])
        await ch.send(embed=create_embed("🔨 АУКЦИОН", f"Лот: {item}\nЦена: {price}", C_GOLD), view=AuctionView())
        await i.response.send_message("✅ Запущен", ephemeral=True)
    else: await i.response.send_message("❌ Не настроено", ephemeral=True)

# --- АДМИН ПАНЕЛЬ ---
class SocialsModal(discord.ui.Modal, title="Настройка ссылок"):
    yt = discord.ui.TextInput(label="YouTube Channel ID", required=False)
    async def on_submit(self, i): 
        cursor.execute("UPDATE configs SET social_yt_id=? WHERE guild_id=?", (self.yt.value, i.guild.id)); conn.commit()
        await i.response.send_message("✅ ID сохранен!", ephemeral=True)

class AdminSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label="📁 Создать Основные Каналы", style=discord.ButtonStyle.success, row=0)
    async def b_create_all(self, i, b):
        await i.response.defer(ephemeral=True)
        guild = i.guild
        r = await get_or_create_role(guild, "Verified", C_GREEN); update_config(guild.id, "verify_role_id", r.id)
        c_i = await get_or_create_channel(guild, "INFO", channel_type="cat"); c_v = await get_or_create_channel(guild, "VOICES", channel_type="cat")
        await get_or_create_channel(guild, "ʀᴜʟᴇ📜", c_i, get_read_only_perms(guild))
        await get_or_create_channel(guild, "ᴀɴɴᴏᴜɴᴄᴇᴍᴇɴᴛ📒", c_i, get_read_only_perms(guild))
        await get_or_create_channel(guild, "ᴘᴀʀᴛɴᴇʀs🤝", c_i, get_read_only_perms(guild))
        np = await get_or_create_channel(guild, "ɴᴇᴡ-ᴘʟᴀʏᴇʀs", c_i, get_write_perms(guild)); update_config(guild.id, "welcome_channel_id", np.id)
        await get_or_create_channel(guild, "ᴄᴏᴍᴍᴜɴɪᴄᴀᴛɪᴏɴ📕", c_i, get_write_perms(guild))
        for x in range(1, 4): await get_or_create_channel(guild, f"ᴠᴏɪsᴇs {x}🍀", c_v, get_voice_perms(guild), "voice")
        # Spec channels
        rep = await get_or_create_channel(guild, "🚨┃репорты", c_i, get_admin_perms(guild)); update_config(guild.id, "report_channel_id", rep.id)
        auc = await get_or_create_channel(guild, "🔨┃аукцион", c_i, get_read_only_perms(guild)); update_config(guild.id, "auction_channel_id", auc.id)
        
        await i.followup.send("✅ Все основные каналы созданы!")

    @discord.ui.button(label="🎵 Чат Музыки", style=discord.ButtonStyle.blurple, row=1)
    async def b_mc(self, i, b): ch=await get_or_create_channel(i.guild, "ᴍᴜsɪᴄ🎶", overwrites=get_write_perms(i.guild)); update_config(i.guild.id, "music_text_channel_id", ch.id); await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)
    
    @discord.ui.button(label="📺 Медиа", style=discord.ButtonStyle.danger, row=1)
    async def b_md(self, i, b): ch=await get_or_create_channel(i.guild, "📺┃медиа", overwrites=get_read_only_perms(i.guild)); update_config(i.guild.id, "media_channel_id", ch.id); await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)

    @discord.ui.button(label="🎉 Конкурсы", style=discord.ButtonStyle.success, row=1)
    async def b_cn(self, i, b): ch=await get_or_create_channel(i.guild, "🎉┃конкурсы", overwrites=get_read_only_perms(i.guild)); update_config(i.guild.id, "contest_channel_id", ch.id); await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)

    # 1. МЕНЮ
    @discord.ui.button(label="🔊 Меню Приваток", style=discord.ButtonStyle.secondary, row=2)
    async def b_pv(self, i, b):
        c=await get_or_create_channel(i.guild, "🔊 Приватные Комнаты", channel_type="cat"); update_config(i.guild.id, "pvoice_category_id", c.id)
        ch=await get_or_create_channel(i.guild, "create-room", overwrites=get_write_perms(i.guild)); await ch.send(embed=create_embed("🔊 Личный Войс", "Создай комнату", 0xFF00FF, IMG_VOICE), view=PrivateVoiceView()); await i.response.send_message("✅", ephemeral=True)
    
    @discord.ui.button(label="🏪 Меню Рынка", style=discord.ButtonStyle.secondary, row=2)
    async def b_mm(self, i, b): ch=await get_or_create_channel(i.guild, "create-ad", overwrites=get_write_perms(i.guild)); await ch.send(embed=create_embed("🏪 Рынок", "Выберите сервер", 0xFFA500, IMG_MARKET), view=MarketSelectView()); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🛒 Меню Магазина", style=discord.ButtonStyle.success, row=2)
    async def b_shop(self, i, b): ch=await get_or_create_channel(i.guild, "shop", overwrites=get_public_perms(i.guild)); await ch.send(embed=create_embed("🛒 МАГАЗИН", "Товары:", C_GOLD, IMG_SHOP), view=ShopMainView()); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🏰 Меню Кланов", style=discord.ButtonStyle.primary, row=2)
    async def b_cl(self, i, b):
        ch = await get_or_create_channel(i.guild, "create-clan", overwrites=get_public_perms(i.guild))
        await ch.send(embed=create_embed("🏰 КЛАНЫ", "Создание клана - Бесплатно (7 дней)", C_GOLD, IMG_CLAN), view=ClanView())
        await i.response.send_message("✅", ephemeral=True)

    # 2. НАСТРОЙКА
    @discord.ui.button(label="🏪 Каналы Рынков", style=discord.ButtonStyle.gray, row=3)
    async def b_mk(self, i, b):
        cat = await get_or_create_channel(i.guild, "🛒 РЫНОК", channel_type="cat")
        ft = await get_or_create_channel(i.guild, "🧡┃рынок-ft", cat, get_read_only_perms(i.guild))
        hw = await get_or_create_channel(i.guild, "💙┃рынок-hw", cat, get_read_only_perms(i.guild))
        cursor.execute("UPDATE configs SET market_ft_channel_id=?, market_hw_channel_id=? WHERE guild_id=?", (ft.id, hw.id, i.guild.id)); conn.commit()
        await i.response.send_message("✅ Каналы рынков созданы!", ephemeral=True)

    @discord.ui.button(label="⚙️ Настройки (Стр 2)", style=discord.ButtonStyle.danger, row=3)
    async def b_next(self, i, b): await i.response.send_message("Настройки:", view=AdminSettingsView(), ephemeral=True)

    @discord.ui.button(label="🛠 Верификация", style=discord.ButtonStyle.green, row=4)
    async def b_v(self, i, b):
        r=await get_or_create_role(i.guild, "Verified", C_GREEN); update_config(i.guild.id, "verify_role_id", r.id)
        ch=await get_or_create_channel(i.guild, "verify", overwrites=get_newbie_perms(i.guild)); await ch.send(embed=create_embed("ВЕРИФИКАЦИЯ", "Нажми кнопку", C_GOLD, IMG_VERIFY), view=VerifyView()); await i.response.send_message("✅", ephemeral=True)
        try: await i.guild.default_role.edit(permissions=discord.Permissions(read_messages=False))
        except: pass

    @discord.ui.button(label="🎫 Тикеты", style=discord.ButtonStyle.primary, row=4)
    async def b_t(self, i, b): 
        c=await get_or_create_channel(i.guild, "📩 Support", channel_type="cat"); l=await get_or_create_channel(i.guild, "ticket-logs", c, get_admin_perms(i.guild)); update_config(i.guild.id, "ticket_log_channel_id", l.id)
        update_config(i.guild.id, "ticket_category_id", c.id); ch=await get_or_create_channel(i.guild, "tickets", c, get_public_perms(i.guild)); await ch.send(embed=create_embed("ТИКЕТЫ", "Создать тикет:"), view=TicketStartView()); await i.response.send_message("✅", ephemeral=True)

class AdminSettingsView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="1. Выберите РОЛЬ ПОДДЕРЖКИ", row=0)
    async def s_sup(self, i, s): update_config(i.guild.id, "support_role_id", s.values[0].id); await i.response.send_message(f"✅ Роль: {s.values[0].mention}", ephemeral=True)
    @discord.ui.button(label="📈 Создать Статистику", style=discord.ButtonStyle.gray, row=1)
    async def b_st(self, i, b):
        ow={i.guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True)}
        c=await get_or_create_channel(i.guild, "📊 СТАТИСТИКА", channel_type="cat", overwrites=ow)
        await get_or_create_channel(i.guild, "Загрузка...", c, channel_type="voice"); await get_or_create_channel(i.guild, "Загрузка...", c, channel_type="voice")
        update_config(i.guild.id, "stats_category_id", c.id); await i.response.send_message("✅", ephemeral=True)
    @discord.ui.button(label="📜 Создать Логи", style=discord.ButtonStyle.gray, row=1)
    async def b_lg(self, i, b): ch=await get_or_create_channel(i.guild, "global-logs", overwrites=get_admin_perms(i.guild)); update_config(i.guild.id, "global_log_channel_id", ch.id); await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)
    @discord.ui.button(label="⚙️ YouTube ID", style=discord.ButtonStyle.gray, row=1)
    async def b_yt(self, i, b): await i.response.send_modal(SocialsModal())
    @discord.ui.button(label="🛡 Создать Роли Гарантов", style=discord.ButtonStyle.primary, row=2)
    async def b_gar(self, i, b):
        for n in ["Garant I", "Garant II", "Garant III", "Garant IV", "Garant V"]: await get_or_create_role(i.guild, n, discord.Color.random())
        await i.response.send_message("✅", ephemeral=True)

class ContestJoinView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="🎉 Участвовать", style=discord.ButtonStyle.success, custom_id="join_contest")
    async def join(self, i, b): await i.response.send_message("✅ Вы записаны!", ephemeral=True)

class ContestCreateModal(discord.ui.Modal, title="Создание Конкурса"):
    c_title = discord.ui.TextInput(label="Приз")
    c_desc = discord.ui.TextInput(label="Условия", style=discord.TextStyle.paragraph)
    c_img = discord.ui.TextInput(label="Ссылка на картинку", required=False)
    async def on_submit(self, i):
        c = get_config(i.guild.id)
        if not c or not c[17]: return await i.response.send_message("❌ Канал конкурсов не создан.", ephemeral=True)
        ch = i.guild.get_channel(c[17])
        emb = discord.Embed(title=f"🎉 КОНКУРС: {self.c_title.value}", description=self.c_desc.value, color=discord.Color.fuchsia())
        if self.c_img.value: emb.set_image(url=self.c_img.value)
        emb.set_footer(text=f"Создал: {i.user.name}")
        await ch.send(embed=emb, view=ContestJoinView())
        await i.response.send_message("✅ Конкурс опубликован!", ephemeral=True)

class TicketStartView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Тикет", style=discord.ButtonStyle.blurple, custom_id="ct_btn")
    async def c(self, i, b):
        c=get_config(i.guild.id); cat=i.guild.get_channel(c[3])
        if not cat: return await i.response.send_message("Ошибка настроек", ephemeral=True)
        ch=await i.guild.create_text_channel(f"ticket-{random.randint(1,999)}", category=cat)
        cursor.execute("INSERT INTO tickets (channel_id, author_id) VALUES (?, ?)", (ch.id, i.user.id)); conn.commit()
        await ch.set_permissions(i.user, read_messages=True, send_messages=True)
        if c and c[2]: 
            sup=i.guild.get_role(c[2])
            if sup: await ch.set_permissions(sup, read_messages=True, send_messages=True)
        await log_action(i.guild, "🎫 Тикет создан", f"{i.user.mention} создал {ch.mention}")
        await ch.send(f"{i.user.mention}", embed=discord.Embed(title="Тикет"), view=TicketControlView()); await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Закрыть", style=discord.ButtonStyle.red, custom_id="clt_btn")
    async def cl(self, i, b):
        c = get_config(i.guild.id)
        if c and c[4]: 
            l = i.guild.get_channel(c[4])
            if l: await l.send(f"📕 Тикет {i.channel.name} закрыт пользователем {i.user.name}")
        await i.channel.delete()

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
    if not i.user.voice: return await i.followup.send("❌ Вы не в голосовом канале!")
    try: vc = i.guild.voice_client if i.guild.voice_client else await i.user.voice.channel.connect()
    except: return await i.followup.send("❌ Ошибка")
    try: 
        p = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
        if vc.is_playing(): vc.stop()
        vc.play(p); await i.followup.send(f"🎶 **{player.title}**")
    except: await i.followup.send("❌ Ошибка")

@bot.tree.command(name="top", description="Топ 100")
async def top_ru(i: discord.Interaction):
    await slash_play(i, "Топ 100 русских песен 2024 микс")

@tasks.loop(minutes=5)
async def update_stats_loop():
    cursor.execute("SELECT guild_id, stats_category_id, support_role_id FROM configs")
    for row in cursor.fetchall():
        try:
            g = bot.get_guild(row[0]); cat = g.get_channel(row[1])
            if not g or not cat: continue
            try: st_ft = (await asyncio.wait_for((await JavaServer.async_lookup(FUNTIME_IP)).async_status(), 2.0)).players.online
            except: st_ft = "Off"
            try: st_hw = (await asyncio.wait_for((await JavaServer.async_lookup(HOLYWORLD_IP)).async_status(), 2.0)).players.online
            except: st_hw = "Off"
            names = [f"💎 {SERVER_NAME}", f"👥 Людей: {g.member_count}", f"🧡 FT: {st_ft}", f"💙 HW: {st_hw}"]
            for i, c in enumerate(cat.voice_channels):
                if i < 4: await c.edit(name=names[i])
        except: pass

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
    update_stats_loop.start()
    bot.add_view(VerifyView()); bot.add_view(TicketStartView()); bot.add_view(TicketControlView()); bot.add_view(AdminSelect()); bot.add_view(MarketSelectView()); bot.add_view(PrivateVoiceView()); bot.add_view(ShopMainView()); bot.add_view(ClanView()); bot.add_view(ContestJoinView()); bot.add_view(AdminSettingsView()); bot.add_view(ReportView(0)); bot.add_view(AuctionView())

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

@bot.event
async def on_member_remove(member):
    c=get_config(member.guild.id)
    if c and c[9]: 
        ch=member.guild.get_channel(c[9])
        if ch: await ch.send(file=await create_banner(member, "GOODBYE", "goodbye_bg.png"))

@bot.command()
async def setup(ctx):
    if not ctx.guild.me.guild_permissions.administrator: return await ctx.send("❌ Дайте мне права АДМИНИСТРАТОРА!")
    try:
        cat = await get_or_create_channel(ctx.guild, "BOT SETTINGS", channel_type="cat")
        ch = await get_or_create_channel(ctx.guild, "admin-panel", cat)
        await ch.purge(limit=5); await ch.send(embed=create_embed("⚙️ Админ Панель", description="BENEZUELA SYSTEM v9.0"), view=AdminSelect())
        await ctx.send(f"✅ Панель создана: {ch.mention}")
    except Exception as e: await ctx.send(f"Ошибка: {e}")

@bot.command()
async def reset(ctx):
    if ctx.author.guild_permissions.administrator: cursor.execute("DELETE FROM configs WHERE guild_id=?", (ctx.guild.id,)); conn.commit(); await ctx.send("✅ Сброс")

bot.run(TOKEN)
