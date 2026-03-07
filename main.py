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
    social_yt TEXT,
    social_tg TEXT,
    social_tt TEXT,
    social_twitch TEXT,
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

# --- ПРАВА ---
def get_admin_perms(guild):
    return {
        guild.default_role: discord.PermissionOverwrite(read_messages=False, view_channel=False),
        guild.me: discord.PermissionOverwrite(read_messages=True, view_channel=True)
    }

def get_public_perms(guild):
    return {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True,
            read_messages=True,
            read_message_history=True,
            send_messages=False
        ),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True)
    }

# --- ЛОГЕР ---
async def log_action(guild, title, desc, color=discord.Color.light_grey()):
    try:
        conf = get_config(guild.id)
        if conf and conf[15]: 
            ch = guild.get_channel(conf[15])
            if ch: await ch.send(embed=discord.Embed(title=title, description=desc, color=color, timestamp=datetime.datetime.now()))
    except: pass

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
ytdl_format_options = {'format': 'bestaudio/best', 'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s', 'restrictfilenames': True, 'noplaylist': True, 'nocheckcertificate': True, 'ignoreerrors': False, 'logtostderr': False, 'quiet': True, 'no_warnings': True, 'default_search': 'auto', 'source_address': '0.0.0.0', 'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}}
ffmpeg_options = {'options': '-vn', 'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5): super().__init__(source, volume); self.data = data; self.title = data.get('title'); self.url = data.get('url')
    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        if not url.startswith("http"): url = f"scsearch:{url}" # SC по умолчанию
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
            if not c or not c[14]: return await i.response.send_message("❌ Админ не настроил категорию приваток!", ephemeral=True)
            cat = i.guild.get_channel(c[14])
            if not cat: return await i.response.send_message("❌ Категория удалена. Перенастройте бота.", ephemeral=True)
            try: lim = int(self.v_limit.value) if self.v_limit.value else 0
            except: lim = 0
            ow = {i.guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True), i.user: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, move_members=True)}
            vc = await i.guild.create_voice_channel(name=self.v_name.value, category=cat, user_limit=lim, overwrites=ow)
            cursor.execute("INSERT INTO voice_channels (voice_id, owner_id) VALUES (?, ?)", (vc.id, i.user.id)); conn.commit()
            if i.user.voice: await i.user.move_to(vc)
            await i.response.send_message(embed=discord.Embed(title=f"⚙️ {self.v_name.value}", color=discord.Color.gold()), view=PrivateVoiceControl(vc), ephemeral=True)
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
    @discord.ui.button(label="Реклама", style=discord.ButtonStyle.secondary, emoji="📢", custom_id="m_ad_btn")
    async def ad(self, i, b): c=get_config(i.guild.id); (await i.response.send_modal(MarketModal("Реклама", c[12]))) if c and c[12] else await i.response.send_message("Не настроено", ephemeral=True)

# --- МАГАЗИН ---
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
    ow = {i.guild.default_role: discord.PermissionOverwrite(read_messages=False), i.user: discord.PermissionOverwrite(read_messages=True), i.guild.me: discord.PermissionOverwrite(read_messages=True)}
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

# --- АДМИН ПАНЕЛЬ ---
class SocialsModal(discord.ui.Modal, title="Настройка ссылок"):
    yt = discord.ui.TextInput(label="YouTube", required=False); tg = discord.ui.TextInput(label="Telegram", required=False)
    async def on_submit(self, i): cursor.execute("UPDATE configs SET social_yt=?, social_tg=? WHERE guild_id=?", (self.yt.value, self.tg.value, i.guild.id)); conn.commit(); await i.response.send_message("✅", ephemeral=True)

class AdminSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="🎵 Создать Чат Музыки", style=discord.ButtonStyle.blurple, row=0)
    async def b_mc(self, i, b): ch=await i.guild.create_text_channel("music-cmd", overwrites=get_public_perms(i.guild)); update_config(i.guild.id, "music_text_channel_id", ch.id); await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)
    
    @discord.ui.button(label="🎉 Создать Поиск Ивентов", style=discord.ButtonStyle.success, row=0)
    async def b_ev(self, i, b):
        ch=await i.guild.create_text_channel("поиск-ивентов", overwrites=get_public_perms(i.guild))
        await ch.send(embed=discord.Embed(title="🔎 Поиск Ивентов", description="Нажмите кнопку, чтобы найти ивенты на серверах.", color=discord.Color.gold()), view=EventsView())
        await i.response.send_message(f"✅ Создано: {ch.mention}", ephemeral=True)

    @discord.ui.button(label="🏪 Создать Каналы Рынков", style=discord.ButtonStyle.danger, row=0)
    async def b_mk(self, i, b):
        ow = get_public_perms(i.guild)
        cat = await i.guild.create_category("РЫНОК")
        ft = await i.guild.create_text_channel("рынок-ft", category=cat, overwrites=ow)
        hw = await i.guild.create_text_channel("рынок-hw", category=cat, overwrites=ow)
        ad = await i.guild.create_text_channel("реклама", category=cat, overwrites=ow)
        cursor.execute("UPDATE configs SET market_ft_channel_id=?, market_hw_channel_id=?, market_ads_channel_id=? WHERE guild_id=?", (ft.id, hw.id, ad.id, i.guild.id)); conn.commit()
        await i.response.send_message("✅ Каналы рынков созданы!", ephemeral=True)

    # РЯД 1
    @discord.ui.button(label="🏪 Меню Рынка", style=discord.ButtonStyle.secondary, row=1)
    async def b_mm(self, i, b): ch=await i.guild.create_text_channel("create-ad", overwrites=get_public_perms(i.guild)); await ch.send(embed=discord.Embed(title="🏪 Рынок", color=discord.Color.orange()), view=MarketSelectView()); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🛒 Меню Магазина", style=discord.ButtonStyle.success, row=1)
    async def b_shop(self, i, b): ch=await i.guild.create_text_channel("shop", overwrites=get_public_perms(i.guild)); await ch.send(embed=discord.Embed(title="Магазин", color=discord.Color.blue()), view=ShopCatSelect()); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🔊 Меню Приваток", style=discord.ButtonStyle.blurple, row=1)
    async def b_pv(self, i, b):
        c=await i.guild.create_category("Приватные Комнаты"); update_config(i.guild.id, "pvoice_category_id", c.id)
        ch=await i.guild.create_text_channel("create-room", overwrites=get_public_perms(i.guild)); await ch.send(embed=discord.Embed(title="🔊 Личный Войс", color=discord.Color.fuchsia()), view=PrivateVoiceView()); await i.response.send_message("✅", ephemeral=True)

    # РЯД 2
    @discord.ui.button(label="🛠 Верификация", style=discord.ButtonStyle.green, row=2)
    async def b_v(self, i, b):
        r=await i.guild.create_role(name="Verified", color=discord.Color.green(), permissions=discord.Permissions(view_channel=True, read_messages=True, send_messages=True, connect=True)); update_config(i.guild.id, "verify_role_id", r.id)
        ow={i.guild.default_role:discord.PermissionOverwrite(read_messages=True, send_messages=False, read_message_history=True), r:discord.PermissionOverwrite(read_messages=False), i.guild.me:discord.PermissionOverwrite(read_messages=True)}
        ch=await i.guild.create_text_channel("verify", overwrites=ow); await ch.send(embed=discord.Embed(title="Верификация"), view=VerifyView()); await i.response.send_message("✅", ephemeral=True)
        try: await i.guild.default_role.edit(permissions=discord.Permissions(read_messages=False, view_channel=False))
        except: pass

    @discord.ui.button(label="🎫 Тикеты", style=discord.ButtonStyle.primary, row=2)
    async def b_t(self, i, b): 
        c=await i.guild.create_category("Support"); l=await i.guild.create_text_channel("ticket-logs", category=c); update_config(i.guild.id, "ticket_log_channel_id", l.id)
        update_config(i.guild.id, "ticket_category_id", c.id); ch=await i.guild.create_text_channel("tickets", category=c, overwrites=get_public_perms(i.guild)); await ch.send(embed=discord.Embed(title="Тикеты"), view=TicketStartView()); await i.response.send_message("✅", ephemeral=True)

    # РЯД 3
    @discord.ui.button(label="⚙️ Настройки (Страница 2)", style=discord.ButtonStyle.danger, row=3)
    async def b_next(self, i, b): await i.response.send_message("Настройки:", view=AdminSettingsView(), ephemeral=True)
    
    @discord.ui.button(label="🔗 Соцсети", style=discord.ButtonStyle.secondary, row=3)
    async def b_soc(self, i, b): await i.response.send_modal(SocialsModal())

class AdminSettingsView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="1. Выберите РОЛЬ ПОДДЕРЖКИ", row=0)
    async def s_sup(self, i, s): update_config(i.guild.id, "support_role_id", s.values[0].id); await i.response.send_message(f"✅ Роль: {s.values[0].mention}", ephemeral=True)
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="2. Чат Музыки", channel_types=[discord.ChannelType.text], row=1)
    async def s_mc(self, i, s): update_config(i.guild.id, "music_text_channel_id", s.values[0].id); await i.response.send_message(f"✅", ephemeral=True)
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="3. Рынок FT", channel_types=[discord.ChannelType.text], row=2)
    async def s_ft(self, i, s): update_config(i.guild.id, "market_ft_channel_id", s.values[0].id); await i.response.send_message("✅", ephemeral=True)
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="4. Рынок HW", channel_types=[discord.ChannelType.text], row=3)
    async def s_hw(self, i, s): update_config(i.guild.id, "market_hw_channel_id", s.values[0].id); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="📈 Создать Статистику", style=discord.ButtonStyle.gray, row=4)
    async def b_st(self, i, b):
        ow={i.guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True)}
        c=await i.guild.create_category("📊 СТАТИСТИКА", overwrites=ow, position=0)
        await i.guild.create_voice_channel("Загрузка...", category=c); await i.guild.create_voice_channel("Загрузка...", category=c)
        update_config(i.guild.id, "stats_category_id", c.id); await i.response.send_message("✅", ephemeral=True)
    @discord.ui.button(label="📜 Создать Логи", style=discord.ButtonStyle.gray, row=4)
    async def b_lg(self, i, b): ch=await i.guild.create_text_channel("global-logs", overwrites=get_admin_perms(i.guild)); update_config(i.guild.id, "global_log_channel_id", ch.id); await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)

# --- ИВЕНТЫ ---
class EventSolver:
    @staticmethod
    def get_next_event(interval, offset=0):
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
        m = now.hour*60 + now.minute
        nxt = ((m - offset) // interval + 1) * interval + offset
        h = (nxt // 60) % 24; mn = nxt % 60; diff = nxt - m
        return f"{h:02}:{mn:02}", diff

class EventsView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Поиск FT", style=discord.ButtonStyle.danger, emoji="🧡", custom_id="evt_ft_tracer")
    async def ft(self, i, b):
        await i.response.defer(ephemeral=True)
        mt, md = EventSolver.get_next_event(45, 15)
        try: st=(await asyncio.wait_for((await JavaServer.async_lookup(FUNTIME_IP)).async_status(), 2.0)); on=st.players.online; pg=int(st.latency)
        except: on="Off"; pg="-"
        emb = discord.Embed(title="🧡 FunTime", color=discord.Color.orange())
        emb.add_field(name="Status", value=f"Online: `{on}`\nPing: `{pg}ms`"); emb.add_field(name="Mystic", value=f"Time: **{mt}**\nIn: **{md}m**")
        await i.followup.send(embed=emb, ephemeral=True)

    @discord.ui.button(label="Поиск HW", style=discord.ButtonStyle.primary, emoji="💙", custom_id="evt_hw_pulse")
    async def hw(self, i, b):
        await i.response.defer(ephemeral=True)
        at, ad = EventSolver.get_next_event(60); bt, bd = EventSolver.get_next_event(120)
        try: st=(await asyncio.wait_for((await JavaServer.async_lookup(HOLYWORLD_IP)).async_status(), 2.0)); on=st.players.online
        except: on="Off"
        emb = discord.Embed(title="💙 HolyWorld", color=discord.Color.blue())
        emb.add_field(name="Status", value=f"Users: `{on}`"); emb.add_field(name="AirDrop", value=f"**{at}** ({ad}m)"); emb.add_field(name="Boss", value=f"**{bt}** ({bd}m)")
        await i.followup.send(embed=emb, ephemeral=True)

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
    if not i.user.voice: return await i.followup.send("Войс!")
    
    # БЕЗОПАСНОЕ ПОДКЛЮЧЕНИЕ
    try:
        vc = i.guild.voice_client
        if not vc: 
            vc = await i.user.voice.channel.connect()
        elif vc.channel.id != i.user.voice.channel.id:
            await vc.move_to(i.user.voice.channel)
    except:
        return await i.followup.send("❌ Не могу подключиться к каналу.")

    try: 
        player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
        if vc.is_playing(): vc.stop()
        vc.play(player)
        await i.followup.send(f"🎶 **{player.title}**")
    except Exception as e:
        await i.followup.send(f"❌ Ошибка: {e}")

@bot.tree.command(name="top_russia", description="Топ 100")
async def top_ru(i: discord.Interaction):
    await slash_play(i, "Топ 100 русских песен 2024 микс")

@tasks.loop(minutes=5)
async def update_stats_loop():
    cursor.execute("SELECT guild_id, stats_category_id FROM configs")
    for row in cursor.fetchall():
        try:
            g = bot.get_guild(row[0]); cat = g.get_channel(row[1])
            if not g or not cat: continue
            try: st_ft = (await asyncio.wait_for((await JavaServer.async_lookup(FUNTIME_IP)).async_status(), 2.0)).players.online
            except: st_ft = "Off"
            try: st_hw = (await asyncio.wait_for((await JavaServer.async_lookup(HOLYWORLD_IP)).async_status(), 2.0)).players.online
            except: st_hw = "Off"
            names = [f"💎 Souls Visuals", f"👥 Людей: {g.member_count}", f"🧡 FT: {st_ft}", f"💙 HW: {st_hw}"]
            for i, c in enumerate(cat.voice_channels):
                if i < 4: await c.edit(name=names[i])
        except: pass

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
    update_stats_loop.start()
    bot.add_view(VerifyView()); bot.add_view(TicketStartView()); bot.add_view(TicketControlView()); bot.add_view(AdminSelect()); bot.add_view(MarketSelectView()); bot.add_view(PrivateVoiceView()); bot.add_view(ShopCatSelect()); bot.add_view(EventsView()); bot.add_view(AdminSettingsView())

# --- ЛОГИ ---
@bot.event
async def on_message_delete(message):
    if message.author.bot: return
    await log_action(message.guild, "🗑 Удаление", f"**{message.author}**: {message.content}", discord.Color.red())

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel:
        cursor.execute("SELECT voice_id FROM voice_channels WHERE voice_id = ?", (before.channel.id,))
        if cursor.fetchone() and len(before.channel.members) == 0:
            await before.channel.delete(); cursor.execute("DELETE FROM voice_channels WHERE voice_id = ?", (before.channel.id,)); conn.commit()
    if before.channel != after.channel:
        desc = f"-> {after.channel.name}" if after.channel else f"<- {before.channel.name}"
        await log_action(member.guild, "🔊 Голос", f"**{member}** {desc}", discord.Color.blue())

@bot.event
async def on_member_join(member):
    await log_action(member.guild, "➕ Вход", f"{member.mention}", discord.Color.green())
    c=get_config(member.guild.id)
    if c and c[8]: 
        ch=member.guild.get_channel(c[8])
        if ch: await ch.send(f"Привет {member.mention}", file=await create_banner(member, "WELCOME", "welcome_bg.png"))

@bot.event
async def on_member_remove(member):
    await log_action(member.guild, "➖ Выход", f"{member.mention}", discord.Color.red())
    c=get_config(member.guild.id)
    if c and c[9]: 
        ch=member.guild.get_channel(c[9])
        if ch: await ch.send(f"Пока...", file=await create_banner(member, "GOODBYE", "goodbye_bg.png"))

@bot.command()
async def setup(ctx):
    try:
        ow = get_admin_perms(ctx.guild)
        cat = await ctx.guild.create_category("BOT SETTINGS", overwrites=ow)
        ch = await ctx.guild.create_text_channel("admin-panel", category=cat)
        await ch.send(embed=discord.Embed(title="⚙️ Админ Панель", description="Главное меню"), view=AdminSelect())
        await ctx.send(f"✅ {ch.mention}")
    except: await ctx.send("Ошибка прав")

@bot.command()
async def fixmenus(ctx):
    if not ctx.author.guild_permissions.administrator: return
    await ctx.send("🔧 Чиним права...")
    for ch_name in ["create-ad", "create-room", "shop", "tickets", "music-cmd", "поиск-ивентов"]:
        ch = discord.utils.get(ctx.guild.text_channels, name=ch_name)
        if ch: await ch.set_permissions(ctx.guild.default_role, view_channel=True, read_messages=True, read_message_history=True, send_messages=False)
    await ctx.send("✅ Готово!")

@bot.command()
async def reset(ctx):
    if ctx.author.guild_permissions.administrator: cursor.execute("DELETE FROM configs WHERE guild_id=?", (ctx.guild.id,)); conn.commit(); await ctx.send("✅ Сброс")

@bot.command()
async def admin(ctx):
    if ctx.author.guild_permissions.administrator: await ctx.send(embed=discord.Embed(title="⚙️ Админ Панель"), view=AdminSelect())

@bot.command()
async def set_welcome(ctx):
    if ctx.author.guild_permissions.administrator: update_config(ctx.guild.id, "welcome_channel_id", ctx.channel.id); await ctx.send("✅")

@bot.command()
async def set_leave(ctx):
    if ctx.author.guild_permissions.administrator: update_config(ctx.guild.id, "leave_channel_id", ctx.channel.id); await ctx.send("✅")

bot.run(TOKEN)
