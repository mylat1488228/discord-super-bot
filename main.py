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
    garant_role_id INTEGER,
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
    global_log_channel_id INTEGER,
    social_yt_id TEXT, 
    contest_channel_id INTEGER,
    media_channel_id INTEGER
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
# Таблица профилей
cursor.execute('''CREATE TABLE IF NOT EXISTS profiles (
    user_id INTEGER PRIMARY KEY,
    reputation INTEGER DEFAULT 0,
    balance INTEGER DEFAULT 0,
    clan_name TEXT,
    bio TEXT DEFAULT 'Я играю на BENEZUELA'
)''')
conn.commit()

def get_config(guild_id):
    cursor.execute("SELECT * FROM configs WHERE guild_id = ?", (guild_id,))
    return cursor.fetchone()

def update_config(guild_id, column, value):
    cursor.execute("SELECT guild_id FROM configs WHERE guild_id = ?", (guild_id,))
    if cursor.fetchone() is None: cursor.execute("INSERT INTO configs (guild_id) VALUES (?)", (guild_id,))
    cursor.execute(f"UPDATE configs SET {column} = ? WHERE guild_id = ?", (value, guild_id)); conn.commit()

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

# --- ПРОФИЛЬ И РЕПУТАЦИЯ ---
@bot.tree.command(name="profile", description="Посмотреть свой профиль")
async def slash_profile(i: discord.Interaction, member: discord.Member = None):
    member = member or i.user
    cursor.execute("SELECT * FROM profiles WHERE user_id = ?", (member.id,))
    res = cursor.fetchone()
    if not res:
        cursor.execute("INSERT INTO profiles (user_id) VALUES (?)", (member.id,)); conn.commit()
        res = (member.id, 0, 0, "Нет", "Я играю на BENEZUELA")
    
    rep = res[1]; bal = res[2]; clan = res[3]; bio = res[4]
    
    emb = discord.Embed(title=f"👤 Профиль: {member.name}", color=discord.Color.gold())
    emb.set_thumbnail(url=member.display_avatar.url)
    emb.add_field(name="📅 На сервере с", value=member.joined_at.strftime("%d.%m.%Y"), inline=True)
    emb.add_field(name="⭐ Репутация", value=f"{rep} (Legit)", inline=True)
    emb.add_field(name="💰 Баланс", value=f"{bal} $", inline=True)
    emb.add_field(name="🏰 Клан", value=clan, inline=True)
    emb.add_field(name="📝 О себе", value=bio, inline=False)
    
    await i.response.send_message(embed=emb)

@bot.tree.command(name="bio", description="Установить описание профиля")
async def slash_bio(i: discord.Interaction, text: str):
    cursor.execute("INSERT OR IGNORE INTO profiles (user_id) VALUES (?)", (i.user.id,))
    cursor.execute("UPDATE profiles SET bio = ? WHERE user_id = ?", (text, i.user.id)); conn.commit()
    await i.response.send_message("✅ Био обновлено!", ephemeral=True)

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
            if not c or not c[14]: return await i.response.send_message("❌ Не настроено.", ephemeral=True)
            cat = i.guild.get_channel(c[14])
            try: lim = int(self.v_limit.value) if self.v_limit.value else 0
            except: lim = 0
            ow = {i.guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True), i.user: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, move_members=True), i.guild.me: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, move_members=True)}
            vc = await i.guild.create_voice_channel(name=self.v_name.value, category=cat, user_limit=lim, overwrites=ow)
            cursor.execute("INSERT INTO voice_channels (voice_id, owner_id) VALUES (?, ?)", (vc.id, i.user.id)); conn.commit()
            if i.user.voice: await i.user.move_to(vc)
            await i.response.send_message(embed=discord.Embed(title=f"🔊 {self.v_name.value}", color=discord.Color.gold()), view=PrivateVoiceControl(vc), ephemeral=True)
        except Exception as e: await i.response.send_message(f"Ошибка: {e}", ephemeral=True)

class PrivateVoiceView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="➕ Создать комнату", style=discord.ButtonStyle.blurple, custom_id="cpv_btn_new")
    async def cr(self, i, b): await i.response.send_modal(PrivateVoiceCreateModal())

# --- МАГАЗИН (ОПЛАТА) ---
class PaymentMethodView(discord.ui.View):
    def __init__(self, amount, item): super().__init__(timeout=None); self.amount = amount; self.item = item
    @discord.ui.button(label="СБП (Карта)", style=discord.ButtonStyle.green)
    async def sbp(self, i, b): await create_shop_ch(i, self.item, f"{self.amount} RUB", "СБП: `+7 900 000 00 00` (Сбер)")
    @discord.ui.button(label="Crypto (USDT)", style=discord.ButtonStyle.gray)
    async def crypto(self, i, b): await create_shop_ch(i, self.item, f"{self.amount} RUB", "USDT (TRC20): `THxxxxxxxxxxxxxxxx`")

async def create_shop_ch(i, prod, price, requisites):
    cat = discord.utils.get(i.guild.categories, name="🛒 Заказы")
    if not cat: cat = await i.guild.create_category("🛒 Заказы")
    ow = {i.guild.default_role: discord.PermissionOverwrite(read_messages=False), i.user: discord.PermissionOverwrite(read_messages=True), i.guild.me: discord.PermissionOverwrite(read_messages=True)}
    ch = await i.guild.create_text_channel(f"buy-{i.user.name}"[:20], category=cat, overwrites=ow)
    emb = discord.Embed(title="🧾 ОПЛАТА ЗАКАЗА", color=discord.Color.green())
    emb.add_field(name="Товар", value=prod); emb.add_field(name="Сумма", value=price)
    emb.add_field(name="Реквизиты", value=requisites, inline=False)
    emb.set_footer(text="После перевода прикрепите чек и нажмите кнопку.")
    await ch.send(f"{i.user.mention}", embed=emb, view=ShopControlView())
    await i.response.send_message(f"✅ Перейдите в {ch.mention}", ephemeral=True)

class ShopControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="✅ Оплатил", style=discord.ButtonStyle.success)
    async def paid(self, i, b): await i.channel.send(f"🔔 {i.user.mention} подтвердил оплату! Админы проверят.")
    @discord.ui.button(label="❌ Отмена", style=discord.ButtonStyle.danger)
    async def cancel(self, i, b): await i.channel.delete()

class ShopAdsSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.select(placeholder="Выберите срок рекламы", options=[
        discord.SelectOption(label="1 День", description="50 RUB"),
        discord.SelectOption(label="3 Дня", description="120 RUB"),
        discord.SelectOption(label="7 Дней", description="250 RUB"),
        discord.SelectOption(label="14 Дней", description="450 RUB"),
        discord.SelectOption(label="30 Дней", description="800 RUB")
    ])
    async def sel(self, i, s): await i.response.send_message("Выберите метод оплаты:", view=PaymentMethodView(s.values[0].split(" - ")[-1], f"Реклама {s.values[0]}"), ephemeral=True)

class ShopMainView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="📢 Реклама", style=discord.ButtonStyle.primary, emoji="📣")
    async def ads(self, i, b): await i.response.send_message("📢 Тарифы рекламы:", view=ShopAdsSelect(), ephemeral=True)
    @discord.ui.button(label="🤖 Купить Бота", style=discord.ButtonStyle.secondary, emoji="🤖")
    async def bot(self, i, b): await i.response.send_message("Выберите метод:", view=PaymentMethodView("1000", "Полный Бот"), ephemeral=True)
    @discord.ui.button(label="🏰 Создать Клан (10кк)", style=discord.ButtonStyle.success, emoji="🛡")
    async def clan(self, i, b): await i.response.send_message("Выберите метод:", view=PaymentMethodView("100 RUB / 10кк", "Создание Клана"), ephemeral=True)

# --- АДМИН ПАНЕЛЬ ---
class AdminSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    # 0. КАНАЛЫ
    @discord.ui.button(label="📁 Создать Основные Каналы", style=discord.ButtonStyle.success, row=0)
    async def b_create_all(self, i, b):
        await i.response.defer(ephemeral=True)
        guild = i.guild
        # Роль
        c = get_config(guild.id)
        if not c or not c[1]:
             r = await guild.create_role(name="Verified", color=discord.Color.green())
             update_config(guild.id, "verify_role_id", r.id)
        
        # Категории и каналы
        cat_info = await guild.create_category("INFO")
        cat_voice = await guild.create_category("VOICES")
        
        await guild.create_text_channel("ʀᴜʟᴇ📜", category=cat_info, overwrites=get_read_only_perms(guild))
        await guild.create_text_channel("ᴀɴɴᴏᴜɴᴄᴇᴍᴇɴᴛ📒", category=cat_info, overwrites=get_read_only_perms(guild))
        await guild.create_text_channel("ᴘᴀʀᴛɴᴇʀs🤝", category=cat_info, overwrites=get_read_only_perms(guild))
        
        np = await guild.create_text_channel("ɴᴇᴡ-ᴘʟᴀʏᴇʀs", category=cat_info, overwrites=get_write_perms(guild))
        update_config(guild.id, "welcome_channel_id", np.id)
        
        await guild.create_text_channel("ᴄᴏᴍᴍᴜɴɪᴄᴀᴛɪᴏɴ📕", category=cat_info, overwrites=get_write_perms(guild))
        for x in range(1, 4): await guild.create_voice_channel(f"ᴠᴏɪsᴇs {x}🍀", category=cat_voice, overwrites=get_voice_perms(guild))
        await i.followup.send("✅ Основные каналы созданы!", ephemeral=True)

    @discord.ui.button(label="🎵 Чат Музыки", style=discord.ButtonStyle.blurple, row=1)
    async def b_mc(self, i, b): ch=await i.guild.create_text_channel("ᴍᴜsɪᴄ🎶", overwrites=get_write_perms(i.guild)); update_config(i.guild.id, "music_text_channel_id", ch.id); await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)
    
    @discord.ui.button(label="📺 Медиа", style=discord.ButtonStyle.danger, row=1)
    async def b_md(self, i, b): ch=await i.guild.create_text_channel("📺┃медиа", overwrites=get_read_only_perms(i.guild)); update_config(i.guild.id, "media_channel_id", ch.id); await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)

    # 1. МЕНЮ
    @discord.ui.button(label="🔊 Меню Приваток", style=discord.ButtonStyle.secondary, row=2)
    async def b_pv(self, i, b):
        c=await i.guild.create_category("🔊 Приватные Комнаты"); update_config(i.guild.id, "pvoice_category_id", c.id)
        ch=await i.guild.create_text_channel("create-room", overwrites=get_write_perms(i.guild)); await ch.send(embed=discord.Embed(title="🔊 Личный Войс", color=discord.Color.fuchsia()), view=PrivateVoiceView()); await i.response.send_message("✅", ephemeral=True)
    
    @discord.ui.button(label="🏪 Меню Рынка", style=discord.ButtonStyle.secondary, row=2)
    async def b_mm(self, i, b): ch=await i.guild.create_text_channel("create-ad", overwrites=get_write_perms(i.guild)); await ch.send(embed=discord.Embed(title="🏪 Рынок", color=discord.Color.orange()), view=MarketSelectView()); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🛒 Меню Магазина", style=discord.ButtonStyle.success, row=2)
    async def b_shop(self, i, b): ch=await i.guild.create_text_channel("shop", overwrites=get_public_perms(i.guild)); await ch.send(embed=discord.Embed(title="🛒 Магазин BENEZUELA", description="Выберите категорию товаров:", color=discord.Color.dark_theme()), view=ShopMainView()); await i.response.send_message("✅", ephemeral=True)

    # 2. НАСТРОЙКА
    @discord.ui.button(label="🏪 Каналы Рынков", style=discord.ButtonStyle.gray, row=3)
    async def b_mk(self, i, b):
        cat = await i.guild.create_category("🛒 РЫНОК")
        ft = await i.guild.create_text_channel("🧡┃рынок-ft", category=cat, overwrites=get_read_only_perms(i.guild))
        hw = await i.guild.create_text_channel("💙┃рынок-hw", category=cat, overwrites=get_read_only_perms(i.guild))
        cursor.execute("UPDATE configs SET market_ft_channel_id=?, market_hw_channel_id=? WHERE guild_id=?", (ft.id, hw.id, i.guild.id)); conn.commit()
        await i.response.send_message("✅ Каналы рынков созданы!", ephemeral=True)

    @discord.ui.button(label="🎫 Тикеты", style=discord.ButtonStyle.primary, row=3)
    async def b_t(self, i, b): 
        c=await i.guild.create_category("📩 Support"); l=await i.guild.create_text_channel("ticket-logs", category=c); update_config(i.guild.id, "ticket_log_channel_id", l.id)
        update_config(i.guild.id, "ticket_category_id", c.id); ch=await i.guild.create_text_channel("tickets", category=c, overwrites=get_write_perms(i.guild)); await ch.send(embed=discord.Embed(title="Тикеты"), view=TicketStartView()); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="📈 Статистика", style=discord.ButtonStyle.gray, row=3)
    async def b_st(self, i, b):
        ow={i.guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True)}
        c=await i.guild.create_category("📊 СТАТИСТИКА", overwrites=ow, position=0)
        await i.guild.create_voice_channel(f"👑 {SERVER_NAME}", category=c)
        await i.guild.create_voice_channel("👥 Загрузка...", category=c)
        await i.guild.create_voice_channel("🤝 Гарантов: 0", category=c)
        update_config(i.guild.id, "stats_category_id", c.id); await i.response.send_message("✅ Статистика создана!", ephemeral=True)

    @discord.ui.button(label="🛠 Верификация", style=discord.ButtonStyle.green, row=4)
    async def b_v(self, i, b):
        r=await i.guild.create_role(name="Verified", color=discord.Color.green(), permissions=discord.Permissions(view_channel=True, read_messages=True, send_messages=True, connect=True, speak=True, stream=True)); update_config(i.guild.id, "verify_role_id", r.id)
        ow={i.guild.default_role:discord.PermissionOverwrite(read_messages=True, send_messages=False, read_message_history=True), r:discord.PermissionOverwrite(read_messages=False), i.guild.me:discord.PermissionOverwrite(read_messages=True)}
        ch=await i.guild.create_text_channel("verify", overwrites=ow); await ch.send(embed=discord.Embed(title="Верификация"), view=VerifyView()); await i.response.send_message("✅", ephemeral=True)
        try: await i.guild.default_role.edit(permissions=discord.Permissions(read_messages=False, view_channel=False))
        except: pass

class VerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Пройти Верификацию", style=discord.ButtonStyle.green, custom_id="vp_btn_new")
    async def v(self, i, b):
        try:
            c=get_config(i.guild.id); r=i.guild.get_role(c[1]) if c else None
            if r: await i.user.add_roles(r); await i.response.send_message("✅ Успех!", ephemeral=True)
        except: await i.response.send_message("❌ Ошибка", ephemeral=True)

# --- РЫНОК ---
class MarketModal(discord.ui.Modal, title='Продажа'):
    item_name = discord.ui.TextInput(label='Товар'); item_price = discord.ui.TextInput(label='Цена'); item_desc = discord.ui.TextInput(label='Описание', style=discord.TextStyle.paragraph); item_photo = discord.ui.TextInput(label='Фото', required=False)
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
    async def ft(self, i, b): c=get_config(i.guild.id); (await i.response.send_modal(MarketModal("Рынок FT", c[11]))) if c and c[11] else await i.response.send_message("Не настроено", ephemeral=True)
    @discord.ui.button(label="HolyWorld", style=discord.ButtonStyle.primary, emoji="💙", custom_id="m_hw_btn")
    async def hw(self, i, b): c=get_config(i.guild.id); (await i.response.send_modal(MarketModal("Рынок HW", c[12]))) if c and c[12] else await i.response.send_message("Не настроено", ephemeral=True)

# --- ТИКЕТЫ ---
class TicketStartView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Тикет", style=discord.ButtonStyle.blurple, custom_id="ct_btn")
    async def c(self, i, b):
        c=get_config(i.guild.id); cat=i.guild.get_channel(c[3])
        ch=await i.guild.create_text_channel(f"ticket-{random.randint(1,999)}", category=cat)
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

@bot.tree.command(name="play", description="Музыка")
async def slash_play(i: discord.Interaction, query: str):
    if not await check_music_channel(i): return
    await i.response.defer()
    if not i.user.voice: return await i.followup.send("❌ Войс!")
    try: vc = i.guild.voice_client; 
    except: pass
    if not vc: vc = await i.user.voice.channel.connect()
    try: 
        player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
        if vc.is_playing(): vc.stop()
        vc.play(player); await i.followup.send(f"🎶 **{player.title}**")
    except: await i.followup.send("❌ Ошибка")

@tasks.loop(minutes=5)
async def update_stats_loop():
    cursor.execute("SELECT guild_id, stats_category_id, garant_role_id FROM configs")
    for row in cursor.fetchall():
        try:
            g = bot.get_guild(row[0]); cat = g.get_channel(row[1])
            if not g or not cat: continue
            
            # Считаем гарантов
            garants = 0
            if row[2]:
                r = g.get_role(row[2])
                if r: garants = len(r.members)

            names = [f"👑 {SERVER_NAME}", f"👥 Людей: {g.member_count}", f"🤝 Гарантов: {garants}"]
            for i, c in enumerate(cat.voice_channels):
                if i < 3: await c.edit(name=names[i])
        except: pass

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
    update_stats_loop.start()
    bot.add_view(VerifyView()); bot.add_view(TicketStartView()); bot.add_view(TicketControlView()); bot.add_view(AdminSelect()); bot.add_view(MarketSelectView()); bot.add_view(PrivateVoiceView()); bot.add_view(ShopMainView())

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
        if ch: 
            embed = discord.Embed(title=f"Привет, {member.name}!", description=f"Рады видеть тебя на **{SERVER_NAME}**!", color=discord.Color.gold())
            await ch.send(f"{member.mention}", embed=embed)

@bot.command()
async def setup(ctx):
    if not ctx.guild.me.guild_permissions.administrator: return await ctx.send("❌ Дайте мне права АДМИНИСТРАТОРА!")
    try:
        cat = await ctx.guild.create_category("BOT SETTINGS")
        try: await cat.set_permissions(ctx.guild.default_role, read_messages=False)
        except: pass
        ch = await ctx.guild.create_text_channel("admin-panel", category=cat)
        await ch.send(embed=discord.Embed(title="⚙️ Админ Панель", description="BENEZUELA SYSTEM v3.0"), view=AdminSelect())
        await ctx.send(f"✅ Панель создана: {ch.mention}")
    except Exception as e: await ctx.send(f"Ошибка: {e}")

@bot.command()
async def reset(ctx):
    if ctx.author.guild_permissions.administrator: cursor.execute("DELETE FROM configs WHERE guild_id=?", (ctx.guild.id,)); conn.commit(); await ctx.send("✅ Сброс")

bot.run(TOKEN)
