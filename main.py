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

# ==========================================
# ⚙️ КОНФИГУРАЦИЯ
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")
# ВПИШИ СЮДА СВОИ НИКИ
ADMINS = ["defaultpeople", "anyachkaaaaa", "kunilus.", "grif228anki"] 
FUNTIME_IP = "play.funtime.su"
HOLYWORLD_IP = "mc.holyworld.ru"
SERVER_NAME = "BENEZUELA"

# ЦВЕТА
C_GOLD = 0xFFD700
C_RED = 0x990000
C_GREEN = 0x00FF00
C_BLUE = 0x00BFFF

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
    stats_category_id INTEGER,
    pvoice_category_id INTEGER,
    global_log_channel_id INTEGER,
    social_yt_id TEXT, 
    contest_channel_id INTEGER,
    media_channel_id INTEGER,
    clan_channel_id INTEGER,
    report_channel_id INTEGER,
    trade_category_id INTEGER
)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 1000,
    reputation INTEGER DEFAULT 0,
    clan_id INTEGER DEFAULT 0,
    bio TEXT DEFAULT 'Игрок BENEZUELA'
)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS clans (
    clan_id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER,
    name TEXT,
    role_id INTEGER,
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
    cursor.execute(f"UPDATE configs SET {column} = ? WHERE guild_id = ?", (value, guild_id)); conn.commit()

def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    if not res:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return get_user(user_id)
    return res

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

# --- ГЕНЕРАТОРЫ ---
async def create_banner(member, title_text, bg_filename):
    try: background = Image.open(bg_filename).convert("RGBA")
    except: background = Image.new("RGBA", (1000, 400), (20, 20, 60))
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
    u = get_user(member.id) # (id, bal, rep, clan_id, bio)
    
    # Ищем клан
    clan_name = "Нет"
    clan_lvl = ""
    if u[3]:
        cursor.execute("SELECT name, level FROM clans WHERE clan_id=?", (u[3],))
        c_res = cursor.fetchone()
        if c_res: clan_name = c_res[0]; clan_lvl = f" (Lvl {c_res[1]})"

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
    draw.text((50, 300), f"🏰 Клан: {clan_name}{clan_lvl}", font=font_s, fill="white")
    draw.text((50, 350), f"📝 {u[4]}", font=font_s, fill="gray") # u[4] is bio

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

# ==========================================
# 🤝 СИСТЕМА СДЕЛОК (TRADE)
# ==========================================
class DealControlView(discord.ui.View):
    def __init__(self, partner_id): super().__init__(timeout=None); self.pid = partner_id
    
    @discord.ui.button(label="✅ Сделка успешна (+Rep)", style=discord.ButtonStyle.success)
    async def success(self, i, b):
        # Накидываем репутацию
        # i.user - тот кто нажал (должен быть создателем сделки или гарантом)
        # self.pid - второй участник
        
        cursor.execute("UPDATE users SET reputation = reputation + 1 WHERE user_id=?", (self.pid,))
        conn.commit()
        await i.response.send_message(f"✅ Сделка завершена! Репутация <@{self.pid}> повышена.")
        await i.channel.delete()

    @discord.ui.button(label="⛔ Отменить", style=discord.ButtonStyle.danger)
    async def cancel(self, i, b): await i.channel.delete()

@bot.tree.command(name="trade", description="Начать безопасную сделку")
@app_commands.describe(member="С кем сделка?", garant="Гарант (если есть)")
async def trade(i: discord.Interaction, member: discord.Member, garant: discord.Member = None):
    c = get_config(i.guild.id)
    # Ищем или создаем категорию для сделок
    cat = discord.utils.get(i.guild.categories, name="🤝 СДЕЛКИ")
    if not cat: cat = await i.guild.create_category("🤝 СДЕЛКИ")
    
    # Права
    ow = {
        i.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        i.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        i.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    if garant:
        ow[garant] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
    
    ch = await i.guild.create_text_channel(f"trade-{i.user.name}-{member.name}", category=cat, overwrites=ow)
    
    desc = f"Участники: {i.user.mention} ↔️ {member.mention}"
    if garant: desc += f"\nГарант: {garant.mention}"
    
    emb = discord.Embed(title="🤝 БЕЗОПАСНАЯ СДЕЛКА", description=desc, color=C_GREEN)
    emb.add_field(name="Правила", value="1. Обсудите условия.\n2. После обмена нажмите 'Сделка успешна', чтобы повысить репутацию партнеру.")
    
    await ch.send(embed=emb, view=DealControlView(member.id)) # Кнопка повысит реп партнеру
    await i.response.send_message(f"✅ Чат сделки создан: {ch.mention}", ephemeral=True)

# ==========================================
# 💾 КЛАНЫ И ПРОФИЛЬ
# ==========================================
@bot.tree.command(name="profile", description="Профиль игрока")
async def profile(i: discord.Interaction, member: discord.Member = None):
    member = member or i.user
    await i.response.defer()
    file = await create_profile_card(member)
    await i.followup.send(file=file)

@bot.tree.command(name="bio", description="Изменить описание профиля")
async def bio(i: discord.Interaction, text: str):
    get_user(i.user.id) # Создаем если нет
    cursor.execute("UPDATE users SET bio = ? WHERE user_id = ?", (text, i.user.id)); conn.commit()
    await i.response.send_message("✅ Био обновлено!", ephemeral=True)

@bot.tree.command(name="setclanlevel", description="[ADMIN] Изменить уровень клана")
async def setclan(i: discord.Interaction, member: discord.Member, level: int):
    if i.user.name not in ADMINS and not i.user.guild_permissions.administrator: 
        return await i.response.send_message("⛔ Только Админ", ephemeral=True)
    
    u = get_user(member.id)
    if not u[3]: return await i.response.send_message("У него нет клана.", ephemeral=True)
    
    cursor.execute("UPDATE clans SET level=? WHERE clan_id=?", (level, u[3]))
    conn.commit()
    await i.response.send_message(f"✅ Уровень клана пользователя {member.mention} изменен на {level}.")

@bot.tree.command(name="casino", description="Ставка")
async def casino(i: discord.Interaction, bet: int):
    u = get_user(i.user.id)
    if u[1] < bet: return await i.response.send_message("❌ Мало денег!", ephemeral=True)
    win = random.choice([True, False])
    new_bal = u[1] + bet if win else u[1] - bet
    cursor.execute("UPDATE users SET balance=? WHERE user_id=?", (new_bal, i.user.id)); conn.commit()
    col = C_GREEN if win else C_RED
    await i.response.send_message(embed=discord.Embed(title="🎰 CASINO", description=f"Баланс: {new_bal}$", color=col))

# --- АДМИН ПАНЕЛЬ ---
class AdminSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label="📁 Создать Основные Каналы", style=discord.ButtonStyle.success, row=0)
    async def b_create_all(self, i, b):
        await i.response.defer(ephemeral=True)
        guild = i.guild
        c = get_config(guild.id)
        if not c or not c[1]:
             r = await guild.create_role(name="Verified", color=discord.Color.green())
             update_config(guild.id, "verify_role_id", r.id)
        
        # Создаем каналы
        cat_info = await get_or_create_channel(guild, "INFO", channel_type="cat")
        cat_voice = await get_or_create_channel(guild, "VOICES", channel_type="cat")
        
        await get_or_create_channel(guild, "ʀᴜʟᴇ📜", cat_info, get_read_only_perms(guild))
        await get_or_create_channel(guild, "ᴀɴɴᴏᴜɴᴄᴇᴍᴇɴᴛ📒", cat_info, get_read_only_perms(guild))
        np = await get_or_create_channel(guild, "ɴᴇᴡ-ᴘʟᴀʏᴇʀs", cat_info, get_write_perms(guild))
        update_config(guild.id, "welcome_channel_id", np.id)
        
        await get_or_create_channel(guild, "ᴄᴏᴍᴍᴜɴɪᴄᴀᴛɪᴏɴ📕", cat_info, get_write_perms(guild))
        for x in range(1, 4): await get_or_create_channel(guild, f"ᴠᴏɪsᴇs {x}🍀", cat_voice, get_voice_perms(guild), "voice")
        await i.followup.send("✅ Основные каналы созданы!")

    @discord.ui.button(label="🛡 Создать Роли Гарантов", style=discord.ButtonStyle.primary, row=0)
    async def b_garant(self, i, b):
        await i.response.defer(ephemeral=True)
        colors = [0xcd7f32, 0xc0c0c0, 0xffd700, 0xe5e4e2, 0xff0000] # Bronze -> Red
        names = ["Garant I (Novice)", "Garant II (Trusted)", "Garant III (Expert)", "Garant IV (Master)", "Garant V (Legend)"]
        for idx, name in enumerate(names):
            if not discord.utils.get(i.guild.roles, name=name):
                await i.guild.create_role(name=name, color=discord.Color(colors[idx]), hover=True)
        await i.followup.send("✅ Роли гарантов созданы!")

    @discord.ui.button(label="🔊 Меню Приваток", style=discord.ButtonStyle.secondary, row=1)
    async def b_pv(self, i, b):
        c=await get_or_create_channel(i.guild, "🔊 Приватные Комнаты", channel_type="cat"); update_config(i.guild.id, "pvoice_category_id", c.id)
        ch=await get_or_create_channel(i.guild, "create-room", overwrites=get_public_perms(i.guild)); await ch.send(embed=discord.Embed(title="🔊 Личный Войс", color=discord.Color.fuchsia()), view=PrivateVoiceView()); await i.response.send_message("✅", ephemeral=True)
    
    @discord.ui.button(label="🏪 Меню Рынка", style=discord.ButtonStyle.secondary, row=1)
    async def b_mm(self, i, b): ch=await get_or_create_channel(i.guild, "create-ad", overwrites=get_public_perms(i.guild)); await ch.send(embed=discord.Embed(title="🏪 Рынок", color=discord.Color.orange()), view=MarketSelectView()); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🛒 Меню Магазина", style=discord.ButtonStyle.success, row=1)
    async def b_shop(self, i, b): ch=await get_or_create_channel(i.guild, "shop", overwrites=get_public_perms(i.guild)); await ch.send(embed=discord.Embed(title="🛒 Магазин", color=discord.Color.blue()), view=ShopMainView()); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🏰 Меню Кланов", style=discord.ButtonStyle.success, row=2)
    async def b_cl(self, i, b):
        ch = await get_or_create_channel(i.guild, "create-clan", overwrites=get_public_perms(i.guild))
        await ch.send(embed=discord.Embed(title="🏰 КЛАНЫ", description="Создание клана - Бесплатно (7 дней)", color=C_GOLD), view=ClanView())
        await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🛠 Верификация", style=discord.ButtonStyle.green, row=2)
    async def b_v(self, i, b):
        r=await i.guild.create_role(name="Verified", color=discord.Color.green()); update_config(i.guild.id, "verify_role_id", r.id)
        ow=get_newbie_perms(i.guild)
        ch=await get_or_create_channel(i.guild, "verify", overwrites=ow); await ch.send(embed=discord.Embed(title="Верификация", view=VerifyView())); await i.response.send_message("✅", ephemeral=True)
        try: await i.guild.default_role.edit(permissions=discord.Permissions(read_messages=False))
        except: pass

    @discord.ui.button(label="🎫 Тикеты", style=discord.ButtonStyle.primary, row=2)
    async def b_t(self, i, b): 
        c=await get_or_create_channel(i.guild, "📩 Support", channel_type="cat"); l=await get_or_create_channel(i.guild, "ticket-logs", c, get_admin_perms(i.guild)); update_config(i.guild.id, "ticket_log_channel_id", l.id)
        update_config(i.guild.id, "ticket_category_id", c.id); ch=await get_or_create_channel(i.guild, "tickets", c, get_public_perms(i.guild)); await ch.send(embed=discord.Embed(title="Тикеты"), view=TicketStartView()); await i.response.send_message("✅", ephemeral=True)

# --- VIEWS И КЛАССЫ ---
class VerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Верификация", style=discord.ButtonStyle.green, custom_id="vp_btn")
    async def v(self, i, b): c=get_config(i.guild.id); r=i.guild.get_role(c[1]); await i.user.add_roles(r); await i.response.send_message("✅", ephemeral=True)

class ClanView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Создать Клан", style=discord.ButtonStyle.success, custom_id="clan_create")
    async def cr(self, i, b): await i.response.send_modal(ClanBuyModal())

class ClanBuyModal(discord.ui.Modal, title="Создание Клана"):
    c_name = discord.ui.TextInput(label="Название")
    async def on_submit(self, i):
        r = await i.guild.create_role(name=f"Clan: {self.c_name.value}")
        cat = await i.guild.create_category(f"🏰 {self.c_name.value}")
        await i.guild.create_text_channel("chat", category=cat)
        cursor.execute("INSERT INTO clans (owner_id, name) VALUES (?, ?)", (i.user.id, self.c_name.value)); conn.commit()
        await i.user.add_roles(r)
        await i.response.send_message("✅ Клан создан!", ephemeral=True)

class ShopMainView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="📢 Реклама", style=discord.ButtonStyle.primary)
    async def ads(self, i, b): await i.response.send_message("Тарифы:", view=ShopAdsSelect(), ephemeral=True)
    @discord.ui.button(label="🤖 Купить Бота", style=discord.ButtonStyle.secondary)
    async def bot(self, i, b): await create_shop_ch(i, "Полный Бот", "1000 RUB")

class ShopAdsSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.select(placeholder="Срок", options=[discord.SelectOption(label="1 День", description="50R"), discord.SelectOption(label="7 Дней", description="250R")])
    async def sel(self, i, s): await create_shop_ch(i, f"Реклама {s.values[0]}", "По прайсу")

class MarketSelectView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="FunTime", style=discord.ButtonStyle.danger, emoji="🧡", custom_id="m_ft_btn")
    async def ft(self, i, b): c=get_config(i.guild.id); (await i.response.send_modal(MarketModal("Рынок FT", c[10]))) if c and c[10] else await i.response.send_message("Не настроено", ephemeral=True)
    @discord.ui.button(label="HolyWorld", style=discord.ButtonStyle.primary, emoji="💙", custom_id="m_hw_btn")
    async def hw(self, i, b): c=get_config(i.guild.id); (await i.response.send_modal(MarketModal("Рынок HW", c[11]))) if c and c[11] else await i.response.send_message("Не настроено", ephemeral=True)

class MarketModal(discord.ui.Modal, title='Продажа'):
    item_name = discord.ui.TextInput(label='Товар'); item_price = discord.ui.TextInput(label='Цена'); item_desc = discord.ui.TextInput(label='Описание', style=discord.TextStyle.paragraph); item_photo = discord.ui.TextInput(label='Фото (ссылка)', required=False)
    def __init__(self, m_type, c_id): super().__init__(); self.m_type=m_type; self.c_id=c_id
    async def on_submit(self, i):
        ch = i.guild.get_channel(self.c_id)
        emb = discord.Embed(title=f"🛒 {self.m_type}", color=discord.Color.orange())
        emb.add_field(name="📦", value=self.item_name.value); emb.add_field(name="💰", value=self.item_price.value); emb.add_field(name="📝", value=self.item_desc.value, inline=False); emb.set_footer(text=f"Продавец: {i.user.name}")
        if self.item_photo.value: emb.set_image(url=self.item_photo.value)
        await ch.send(embed=emb); await i.response.send_message("✅", ephemeral=True)

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
    cursor.execute("SELECT guild_id, stats_category_id, support_role_id FROM configs")
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
    if not ctx.guild.me.guild_permissions.administrator: return await ctx.send("❌ Дайте мне права АДМИНИСТРАТОРА!")
    try:
        cat = await get_or_create_channel(ctx.guild, "BOT SETTINGS", channel_type="cat")
        ch = await get_or_create_channel(ctx.guild, "admin-panel", cat)
        await ch.send(embed=discord.Embed(title="⚙️ Админ Панель", description="BENEZUELA SYSTEM v5.0"), view=AdminSelect())
        await ctx.send(f"✅ Панель создана: {ch.mention}")
    except Exception as e: await ctx.send(f"Ошибка: {e}")

@bot.command()
async def reset(ctx):
    if ctx.author.name in ADMINS: cursor.execute("DELETE FROM configs WHERE guild_id=?", (ctx.guild.id,)); conn.commit(); await ctx.send("✅ Сброс")

bot.run(TOKEN)
