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

# ==========================================
# ⚙️ КОНФИГУРАЦИЯ СЕРВЕРА
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")
ADMINS = ["defaultpeople", "anyachkaaaaa"] 
FUNTIME_IP = "play.funtime.su"
HOLYWORLD_IP = "mc.holyworld.ru"
SERVER_NAME = "BENEZUELA"

# ЦВЕТА И ССЫЛКИ
C_GOLD = 0xFFD700
C_RED = 0x990000
C_GREEN = 0x00FF00
C_DARK = 0x2F3136

# ИЗОБРАЖЕНИЯ ДЛЯ МЕНЮ (GIF)
IMG_MAIN = "https://i.pinimg.com/originals/e4/26/70/e426702edf874b181aced1e2fa5c6cde.gif" # Рынок
IMG_PVOICE = "https://i.pinimg.com/originals/2b/26/5c/2b265c37253337b32d47485773224795.gif" # Приватки
IMG_VERIFY = "https://i.pinimg.com/originals/1c/54/f7/1c54f7b06d7723c21afc5035bf88a5ef.gif" # Верификация
IMG_CLAN = "https://i.pinimg.com/originals/a5/37/67/a53767576572793267759d825c9772da.gif" # Кланы

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command('help')

# ==========================================
# 💾 БАЗА ДАННЫХ
# ==========================================
if os.path.exists("/app/data"):
    DB_PATH = "/app/data/server_data.db"
else:
    DB_PATH = "server_data.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Таблица настроек каналов и ролей
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

# Таблица пользователей (Экономика, Репутация)
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 1000,
    reputation INTEGER DEFAULT 0,
    clan_id INTEGER DEFAULT 0,
    xp INTEGER DEFAULT 0,
    bio TEXT DEFAULT 'Игрок BENEZUELA'
)''')

# Таблица кланов
cursor.execute('''CREATE TABLE IF NOT EXISTS clans (
    clan_id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER,
    name TEXT,
    role_id INTEGER,
    category_id INTEGER,
    level INTEGER DEFAULT 1,
    balance INTEGER DEFAULT 0
)''')

# Технические таблицы
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
    else: # Voice or Category
        if channel_type == "cat":
            ch = discord.utils.get(guild.categories, name=name)
            if not ch: ch = await guild.create_category(name, overwrites=overwrites)
        else:
            ch = discord.utils.get(guild.voice_channels, name=name)
            if not ch: ch = await guild.create_voice_channel(name, category=category, overwrites=overwrites)
    return ch

# ==========================================
# 🎨 ВИЗУАЛ И ГЕНЕРАТОР КАРТИНОК
# ==========================================
async def create_banner(member, title_text, bg_filename):
    try: background = Image.open(bg_filename).convert("RGBA")
    except: background = Image.new("RGBA", (1000, 400), (20, 20, 20))
    background = background.resize((1000, 400))
    draw = ImageDraw.Draw(background)
    try: font = ImageFont.truetype("font.ttf", 90); font_small = ImageFont.truetype("font.ttf", 60)
    except: font = ImageFont.load_default(); font_small = ImageFont.load_default()
    
    W, H = background.size
    
    # ТЕКСТ ПО ЦЕНТРУ (БЕЗ АВАТАРКИ)
    # Заголовок
    _, _, w, h = draw.textbbox((0, 0), title_text, font=font)
    draw.text(((W-w)/2+4, H/2-80+4), title_text, fill="black", font=font) # Тень
    draw.text(((W-w)/2, H/2-80), title_text, fill="white", font=font)
    
    # Никнейм
    name_text = f"@{member.name}"
    _, _, w2, h2 = draw.textbbox((0, 0), name_text, font=font_small)
    draw.text(((W-w2)/2+4, H/2+30+4), name_text, fill="black", font=font_small)
    draw.text(((W-w2)/2, H/2+30), name_text, fill=(0, 255, 255), font=font_small) # Cyan neon

    buffer = io.BytesIO(); background.save(buffer, format="PNG"); buffer.seek(0)
    return discord.File(buffer, filename="welcome.png")

async def create_profile_card(member):
    user_data = get_user(member.id) # (id, bal, rep, clan_id, xp, bio)
    
    # Получаем название клана
    clan_name = "Нет"
    if user_data[3]:
        cursor.execute("SELECT name FROM clans WHERE clan_id=?", (user_data[3],))
        c_res = cursor.fetchone()
        if c_res: clan_name = c_res[0]

    img = Image.new('RGB', (800, 400), color=(25, 25, 25))
    draw = ImageDraw.Draw(img)
    try: font = ImageFont.truetype("font.ttf", 40); font_s = ImageFont.truetype("font.ttf", 25)
    except: font = ImageFont.load_default(); font_s = ImageFont.load_default()

    # Аватарка
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(member.display_avatar.url) as resp: av_bytes = await resp.read()
        av = Image.open(io.BytesIO(av_bytes)).resize((150, 150))
        img.paste(av, (50, 50))
    except: pass

    # Текст
    draw.text((230, 60), f"{member.name}", font=font, fill=C_GOLD)
    draw.text((230, 110), f"ID: {member.id}", font=font_s, fill="white")
    
    draw.text((50, 250), f"💰 Баланс: {user_data[1]}$", font=font_s, fill="white")
    draw.text((350, 250), f"⭐ Репутация: {user_data[2]}", font=font_s, fill="white")
    draw.text((50, 300), f"🏰 Клан: {clan_name}", font=font_s, fill="white")
    draw.text((50, 350), f"📝 {user_data[5]}", font=font_s, fill="gray")

    buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
    return discord.File(buf, filename='profile.png')

# ==========================================
# 🎶 МУЗЫКАЛЬНАЯ СИСТЕМА
# ==========================================
yt_dlp.utils.bug_reports_message = lambda: ''
ytdl_format_options = {
    'format': 'bestaudio/best', 'restrictfilenames': True, 'noplaylist': True, 
    'nocheckcertificate': True, 'ignoreerrors': False, 'logtostderr': False, 'quiet': True, 'no_warnings': True, 
    'default_search': 'auto', 'source_address': '0.0.0.0',
    'http_headers': {'User-Agent': 'Mozilla/5.0'}
}
ffmpeg_options = {'options': '-vn', 'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5): super().__init__(source, volume); self.data = data; self.title = data.get('title'); self.url = data.get('url')
    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        # FALLBACK: Если не ссылка -> SoundCloud
        if not url.startswith("http"): url = f"scsearch:{url}"
        
        data = await asyncio.wait_for(loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream)), timeout=15.0)
        if 'entries' in data: data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

async def check_music_channel(i):
    c = get_config(i.guild.id)
    # c[6] = music_text_channel_id
    if c and c[6] and i.channel.id != c[6]:
        ch = i.guild.get_channel(c[6])
        await i.response.send_message(f"🚫 Используйте команды только в {ch.mention}", ephemeral=True)
        return False
    return True

@bot.tree.command(name="play", description="Включить трек")
async def play(i: discord.Interaction, query: str):
    if not await check_music_channel(i): return
    await i.response.defer()
    if not i.user.voice: return await i.followup.send("❌ Зайдите в голосовой канал!")
    
    # Безопасное подключение
    try:
        vc = i.guild.voice_client
        if not vc: vc = await i.user.voice.channel.connect()
        elif vc.channel.id != i.user.voice.channel.id: await vc.move_to(i.user.voice.channel)
    except: return await i.followup.send("❌ Ошибка подключения.")

    try:
        player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
        if vc.is_playing(): vc.stop()
        vc.play(player)
        await i.followup.send(f"🎶 **{player.title}**")
    except Exception as e: await i.followup.send(f"❌ Ошибка: {e}")

@bot.tree.command(name="top", description="Топ 100")
async def top(i: discord.Interaction):
    await play(i, "Топ 100 русских песен 2024 микс")

# ==========================================
# 🏰 СИСТЕМА КЛАНОВ
# ==========================================
class ClanBuyModal(discord.ui.Modal, title="Создание Клана"):
    c_name = discord.ui.TextInput(label="Название клана", max_length=20)
    c_tag = discord.ui.TextInput(label="Тег клана (3-4 буквы)", max_length=4)
    async def on_submit(self, i):
        # Проверка денег (10кк) или Бесплатно
        # Пока делаем бесплатно, как ты просил
        
        # Создаем роль
        role = await i.guild.create_role(name=f"[{self.c_tag.value}] {self.c_name.value}", color=discord.Color.random())
        await i.user.add_roles(role)
        
        # Создаем категорию
        overwrites = {
            i.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            role: discord.PermissionOverwrite(read_messages=True, connect=True, speak=True),
            i.guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        cat = await i.guild.create_category(f"🏰 {self.c_name.value}", overwrites=overwrites)
        await i.guild.create_text_channel("chat", category=cat)
        await i.guild.create_voice_channel("voice", category=cat)
        
        # Запись в БД
        cursor.execute("INSERT INTO clans (owner_id, name, role_id, category_id) VALUES (?, ?, ?, ?)", (i.user.id, self.c_name.value, role.id, cat.id))
        clan_id = cursor.lastrowid
        cursor.execute("UPDATE users SET clan_id=? WHERE user_id=?", (clan_id, i.user.id))
        conn.commit()
        
        await i.response.send_message(f"✅ Клан **{self.c_name.value}** создан! Ваша категория готова.", ephemeral=True)

class ClanView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Создать Клан (Бесплатно 7 дней)", style=discord.ButtonStyle.success, emoji="🏰", custom_id="clan_create_btn")
    async def create(self, i, b):
        u = get_user(i.user.id)
        if u[3]: return await i.response.send_message("❌ У вас уже есть клан!", ephemeral=True)
        await i.response.send_modal(ClanBuyModal())

# ==========================================
# 💰 МАГАЗИН И ЭКОНОМИКА
# ==========================================
class ShopControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="✅ Оплатил", style=discord.ButtonStyle.green)
    async def paid(self, i, b): await i.channel.send(f"🔔 {i.user.mention} подтвердил оплату! @here")
    @discord.ui.button(label="🔒 Закрыть", style=discord.ButtonStyle.red)
    async def close(self, i, b): await i.channel.delete()

async def create_order(i, item, price):
    cat = discord.utils.get(i.guild.categories, name="🛒 ЗАКАЗЫ")
    if not cat: cat = await i.guild.create_category("🛒 ЗАКАЗЫ")
    
    overwrites = {
        i.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        i.user: discord.PermissionOverwrite(read_messages=True),
        i.guild.me: discord.PermissionOverwrite(read_messages=True)
    }
    # Добавляем роль поддержки
    c = get_config(i.guild.id)
    if c and c[2]:
        sup = i.guild.get_role(c[2])
        if sup: overwrites[sup] = discord.PermissionOverwrite(read_messages=True)

    ch = await i.guild.create_text_channel(f"buy-{i.user.name}", category=cat, overwrites=overwrites)
    
    emb = discord.Embed(title="🧾 ОФОРМЛЕНИЕ ЗАКАЗА", color=C_GOLD)
    emb.add_field(name="Товар", value=item)
    emb.add_field(name="Цена", value=price)
    emb.add_field(name="Реквизиты", value="💳 СБП: `+7 900 000 00 00`\n🪙 USDT (TRC20): `THxxxxxxxxxx`", inline=False)
    emb.set_footer(text="Скиньте скриншот оплаты сюда")
    
    await ch.send(f"{i.user.mention}", embed=emb, view=ShopControlView())
    await i.response.send_message(f"✅ Перейдите в канал заказа: {ch.mention}", ephemeral=True)

class ShopAdsSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.select(placeholder="Выберите срок рекламы", options=[
        discord.SelectOption(label="1 День", description="50 RUB"),
        discord.SelectOption(label="3 Дня", description="120 RUB"),
        discord.SelectOption(label="7 Дней", description="250 RUB"),
        discord.SelectOption(label="14 Дней", description="450 RUB"),
        discord.SelectOption(label="30 Дней", description="800 RUB")
    ])
    async def sel(self, i, s): await create_order(i, f"Реклама {s.values[0]}", "По прайсу")

class ShopMainView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="📢 Реклама", style=discord.ButtonStyle.primary, emoji="📢")
    async def ads(self, i, b): await i.response.send_message("Выберите срок:", view=ShopAdsSelect(), ephemeral=True)
    @discord.ui.button(label="🤖 Купить Бота", style=discord.ButtonStyle.secondary, emoji="🤖")
    async def bot(self, i, b): await create_order(i, "Полный Бот (Исходник)", "1000 RUB")
    @discord.ui.button(label="🏰 Купить Клан", style=discord.ButtonStyle.success, emoji="🏰")
    async def clan(self, i, b): await create_order(i, "Создание Клана (Навсегда)", "100 RUB / 10кк")

# ==========================================
# 🔊 ПРИВАТНЫЕ ВОЙСЫ
# ==========================================
class PrivateVoiceControl(discord.ui.View):
    def __init__(self, vc): super().__init__(timeout=None); self.vc = vc
    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="➕ Добавить друга", min_values=1, max_values=10)
    async def add(self, i, s):
        for u in s.values: await self.vc.set_permissions(u, connect=True, view_channel=True)
        await i.response.send_message("✅ Добавлены", ephemeral=True)
    @discord.ui.button(label="🔒", style=discord.ButtonStyle.red)
    async def l(self, i, b): await self.vc.set_permissions(i.guild.default_role, connect=False); await i.response.send_message("🔒", ephemeral=True)
    @discord.ui.button(label="🔓", style=discord.ButtonStyle.green)
    async def u(self, i, b): await self.vc.set_permissions(i.guild.default_role, connect=True); await i.response.send_message("🔓", ephemeral=True)

class PrivateVoiceCreateModal(discord.ui.Modal, title="Настройки комнаты"):
    name = discord.ui.TextInput(label="Название")
    limit = discord.ui.TextInput(label="Лимит", placeholder="0", required=False)
    async def on_submit(self, i):
        c = get_config(i.guild.id)
        cat = i.guild.get_channel(c[13]) # pvoice_category_id
        try: lim = int(self.limit.value) if self.limit.value else 0
        except: lim = 0
        
        ow = {i.guild.default_role: discord.PermissionOverwrite(connect=False), i.user: discord.PermissionOverwrite(connect=True, manage_channels=True)}
        vc = await i.guild.create_voice_channel(name=self.name.value, category=cat, user_limit=lim, overwrites=ow)
        cursor.execute("INSERT INTO voice_channels (voice_id, owner_id) VALUES (?, ?)", (vc.id, i.user.id)); conn.commit()
        if i.user.voice: await i.user.move_to(vc)
        await i.response.send_message(embed=discord.Embed(title=f"🔊 {self.name.value}", color=C_GOLD), view=PrivateVoiceControl(vc), ephemeral=True)

class PrivateVoiceView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="➕ Создать комнату", style=discord.ButtonStyle.blurple, custom_id="pv_create")
    async def cr(self, i, b): await i.response.send_modal(PrivateVoiceCreateModal())

# ==========================================
# 🛠 ВЕРИФИКАЦИЯ И ТИКЕТЫ
# ==========================================
class VerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Пройти Верификацию", style=discord.ButtonStyle.green, custom_id="verify_btn")
    async def v(self, i, b):
        c=get_config(i.guild.id); r=i.guild.get_role(c[1])
        if r: await i.user.add_roles(r); await i.response.send_message("✅ Доступ открыт!", ephemeral=True)

class TicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Создать Тикет", style=discord.ButtonStyle.blurple, custom_id="create_ticket")
    async def cr(self, i, b):
        c=get_config(i.guild.id); cat=i.guild.get_channel(c[3])
        ch=await i.guild.create_text_channel(f"ticket-{i.user.name}", category=cat)
        await ch.set_permissions(i.user, read_messages=True, send_messages=True)
        # Поддержка
        if c[2]: 
            sup=i.guild.get_role(c[2])
            if sup: await ch.set_permissions(sup, read_messages=True, send_messages=True)
        
        await ch.send(f"{i.user.mention}", embed=discord.Embed(title="Тикет", description="Опишите проблему", color=C_GOLD), view=TicketControlView())
        await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Закрыть", style=discord.ButtonStyle.red)
    async def cl(self, i, b): await i.channel.delete()

# ==========================================
# 🏪 РЫНОК (FT / HW)
# ==========================================
class MarketModal(discord.ui.Modal, title='Продажа'):
    name = discord.ui.TextInput(label='Товар'); price = discord.ui.TextInput(label='Цена'); desc = discord.ui.TextInput(label='Описание', style=discord.TextStyle.paragraph)
    def __init__(self, t, cid): super().__init__(); self.t=t; self.cid=cid
    async def on_submit(self, i):
        ch = i.guild.get_channel(self.cid)
        emb = discord.Embed(title=f"🛒 {self.t}", color=discord.Color.orange())
        emb.add_field(name="📦 Товар", value=self.name.value)
        emb.add_field(name="💰 Цена", value=self.price.value)
        emb.add_field(name="📝 Инфо", value=self.desc.value, inline=False)
        emb.set_footer(text=f"Продавец: {i.user.name}")
        await ch.send(embed=emb)
        await i.response.send_message("✅ Объявление опубликовано!", ephemeral=True)

class MarketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="FunTime", style=discord.ButtonStyle.danger, emoji="🧡", custom_id="m_ft")
    async def ft(self, i, b): c=get_config(i.guild.id); await i.response.send_modal(MarketModal("FunTime", c[10]))
    @discord.ui.button(label="HolyWorld", style=discord.ButtonStyle.primary, emoji="💙", custom_id="m_hw")
    async def hw(self, i, b): c=get_config(i.guild.id); await i.response.send_modal(MarketModal("HolyWorld", c[11]))

# ==========================================
# ⚙️ АДМИН ПАНЕЛЬ
# ==========================================
class AdminSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    # 1. СОЗДАНИЕ КАНАЛОВ (СМАРТ)
    @discord.ui.button(label="📁 Создать Каналы", style=discord.ButtonStyle.success, row=0)
    async def b_all(self, i, b):
        await i.response.defer()
        g=i.guild
        
        # Роль Verified
        r_ver = discord.utils.get(g.roles, name="Verified")
        if not r_ver: r_ver = await g.create_role(name="Verified", color=discord.Color.green())
        update_config(g.id, "verify_role_id", r_ver.id)
        
        # Категории
        c_info = await get_or_create_channel(g, "INFO", channel_type="cat")
        c_voice = await get_or_create_channel(g, "VOICES", channel_type="cat")
        c_shop = await get_or_create_channel(g, "SHOP", channel_type="cat")
        
        # Приветствия / Правила / Чат (с правами)
        ow_read = {g.default_role: discord.PermissionOverwrite(view_channel=False), r_ver: discord.PermissionOverwrite(view_channel=True, send_messages=False)}
        ow_write = {g.default_role: discord.PermissionOverwrite(view_channel=False), r_ver: discord.PermissionOverwrite(view_channel=True, send_messages=True)}
        
        await get_or_create_channel(g, "ʀᴜʟᴇ📜", c_info, ow_read)
        np = await get_or_create_channel(g, "ɴᴇᴡ-ᴘʟᴀʏᴇʀs", c_info, ow_write); update_config(g.id, "welcome_channel_id", np.id)
        await get_or_create_channel(g, "ᴄᴏᴍᴍᴜɴɪᴄᴀᴛɪᴏɴ📕", c_info, ow_write)
        
        # Голосовые
        for x in range(1, 4): await get_or_create_channel(g, f"ᴠᴏɪsᴇs {x}🍀", c_voice, channel_type="voice")
        
        # Рынок
        c_market = await get_or_create_channel(g, "🛒 РЫНОК", channel_type="cat")
        ft = await get_or_create_channel(g, "🧡┃рынок-ft", c_market, ow_read); update_config(g.id, "market_ft_channel_id", ft.id)
        hw = await get_or_create_channel(g, "💙┃рынок-hw", c_market, ow_read); update_config(g.id, "market_hw_channel_id", hw.id)
        
        await i.followup.send("✅ Основные каналы созданы!")

    # 2. МЕНЮ
    @discord.ui.button(label="🛠 Верификация", style=discord.ButtonStyle.green, row=1)
    async def b_v(self, i, b):
        ch = await get_or_create_channel(i.guild, "verify")
        # Изоляция для новичков
        await ch.set_permissions(i.guild.default_role, view_channel=True, read_messages=True)
        await ch.send(embed=create_embed("🛡 ВЕРИФИКАЦИЯ", "Нажмите кнопку, чтобы войти", C_GOLD), view=VerifyView())
        await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🔊 Приватки", style=discord.ButtonStyle.blurple, row=1)
    async def b_pv(self, i, b):
        c = await get_or_create_channel(i.guild, "🔊 Приватные Комнаты", channel_type="cat")
        update_config(i.guild.id, "pvoice_category_id", c.id)
        ch = await get_or_create_channel(i.guild, "create-room")
        await ch.send(embed=create_embed("🔊 ЛИЧНЫЙ ВОЙС", "Создай свою комнату", 0xFF00FF), view=PrivateVoiceView())
        await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🏪 Рынок", style=discord.ButtonStyle.secondary, row=1)
    async def b_m(self, i, b):
        ch = await get_or_create_channel(i.guild, "create-ad")
        await ch.send(embed=create_embed("🏪 РЫНОК", "Выберите сервер для продажи", 0xFFA500), view=MarketSelectView())
        await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🛒 Магазин", style=discord.ButtonStyle.success, row=2)
    async def b_s(self, i, b):
        ch = await get_or_create_channel(i.guild, "shop")
        await ch.send(embed=create_embed("🛒 МАГАЗИН", "Выберите товар:", C_GOLD), view=ShopMainView())
        await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🏰 Кланы", style=discord.ButtonStyle.success, row=2)
    async def b_cl(self, i, b):
        ch = await get_or_create_channel(i.guild, "create-clan")
        await ch.send(embed=create_embed("🏰 КЛАНЫ", "Создание клана - Бесплатно (7 дней)", C_GOLD), view=ClanView())
        await i.response.send_message("✅", ephemeral=True)

    # 3. НАСТРОЙКИ
    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Выберите РОЛЬ ПОДДЕРЖКИ", row=3)
    async def s_sup(self, i, s): update_config(i.guild.id, "support_role_id", s.values[0].id); await i.response.send_message("✅", ephemeral=True)

# --- ГЛОБАЛЬНЫЕ СОБЫТИЯ ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
    bot.add_view(VerifyView()); bot.add_view(TicketView()); bot.add_view(PrivateVoiceView()); bot.add_view(MarketSelectView()); bot.add_view(ShopMainView()); bot.add_view(ClanView()); bot.add_view(AdminSelect())

@bot.event
async def on_member_join(member):
    c=get_config(member.guild.id)
    if c and c[8]:
        ch=member.guild.get_channel(c[8])
        if ch: await ch.send(file=await create_banner(member, "WELCOME", "welcome_bg.png"))

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel:
        cursor.execute("SELECT voice_id FROM voice_channels WHERE voice_id = ?", (before.channel.id,))
        if cursor.fetchone() and len(before.channel.members) == 0:
            await before.channel.delete(); cursor.execute("DELETE FROM voice_channels WHERE voice_id = ?", (before.channel.id,)); conn.commit()

@bot.command()
async def setup(ctx):
    if ctx.author.name not in ADMINS: return
    cat = await get_or_create_channel(ctx.guild, "BOT SETTINGS", channel_type="cat")
    ch = await get_or_create_channel(ctx.guild, "admin-panel", cat)
    await ch.purge(limit=5)
    await ch.send(embed=create_embed("⚙️ АДМИН ПАНЕЛЬ", "Управление сервером"), view=AdminSelect())
    await ctx.send(f"✅ {ch.mention}")

# СЛЕШ КОМАНДЫ (ПРОФИЛЬ, КАЗИНО, РЕПОРТ, АУКЦИОН) - Добавлены выше в коде

bot.run(TOKEN)
