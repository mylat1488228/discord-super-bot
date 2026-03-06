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

# --- ПРАВА (ЧТОБЫ КНОПКИ БЫЛИ ВИДНЫ) ---
def get_public_perms(guild):
    return {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=True,
            read_messages=True,
            read_message_history=True, # ОБЯЗАТЕЛЬНО ДЛЯ КНОПОК
            send_messages=False
        ),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True)
    }

# --- МУЗЫКАЛЬНЫЙ ДВИЖОК (УМНЫЙ) ---
yt_dlp.utils.bug_reports_message = lambda: ''
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    # Притворяемся браузером
    'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
}
ffmpeg_options = {'options': '-vn', 'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, query, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        
        # 1. Попытка через YouTube
        try:
            # Если это ссылка
            if query.startswith("http"):
                search = query
            else:
                search = f"ytsearch:{query}"
            
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search, download=not stream))
        except Exception as e:
            # 2. ФОЛЛБЭК: Если Ютуб не работает -> Ищем на SoundCloud
            print(f"YT Error, switching to SC: {e}")
            if not query.startswith("http"):
                search = f"scsearch:{query}"
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(search, download=not stream))
            else:
                raise e # Если ссылка была битая, то падаем

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# --- ГЕНЕРАТОР КАРТИНОК (ОБНОВЛЕН ДЛЯ ТВОИХ ФОТО) ---
async def create_banner(member, title_text, bg_filename):
    try:
        background = Image.open(bg_filename).convert("RGBA")
    except:
        # Если файла нет, делаем черный фон
        background = Image.new("RGBA", (1000, 500), (20, 20, 20))
    
    # Ресайз под стандарт
    background = background.resize((1000, 500))

    # Аватарка
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(member.display_avatar.url) as resp:
                avatar_bytes = await resp.read()
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
    except:
        avatar = Image.new("RGBA", (200, 200), (100, 100, 100))

    avatar = avatar.resize((200, 200))
    
    # Круглая маска
    mask = Image.new("L", (200, 200), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((0, 0, 200, 200), fill=255)
    
    # Накладываем аватарку (В центр, чуть ниже надписи WELCOME на картинке)
    # На твоем фото Welcome сверху, значит аватарку ставим ниже
    avatar_x = 400 # Центр по ширине
    avatar_y = 250 # Центр по высоте
    
    output = background.copy()
    output.paste(avatar, (avatar_x, avatar_y), mask)

    # Добавляем текст (Никнейм)
    draw = ImageDraw.Draw(output)
    try:
        font = ImageFont.truetype("font.ttf", 60)
    except:
        font = ImageFont.load_default()

    text = str(member.name)
    # Рисуем текст с обводкой для читаемости
    text_pos = (avatar_x, avatar_y + 210)
    draw.text((text_pos[0]+2, text_pos[1]+2), text, fill="black", font=font) # Тень
    draw.text(text_pos, text, fill="white", font=font) # Текст

    buffer = io.BytesIO()
    output.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="welcome.png")

# --- СЛЕШ КОМАНДЫ ДЛЯ МУЗЫКИ ---
@bot.tree.command(name="play", description="Включить музыку (Название или ссылка)")
async def slash_play(i: discord.Interaction, query: str):
    await i.response.defer()
    
    if not i.user.voice:
        return await i.followup.send("❌ Зайдите в голосовой канал!")
        
    try:
        if not i.guild.voice_client: 
            await i.user.voice.channel.connect()
        else:
            await i.guild.voice_client.move_to(i.user.voice.channel)
    except: pass

    try:
        # Используем умный поиск (YT -> SC)
        player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
        
        if i.guild.voice_client.is_playing(): 
            i.guild.voice_client.stop()
            
        i.guild.voice_client.play(player)
        await i.followup.send(f"🎶 Играет: **{player.title}**")
        
    except Exception as e:
        await i.followup.send(f"❌ Ошибка: {e}")

@bot.tree.command(name="stop", description="Остановить музыку")
async def slash_stop(i: discord.Interaction):
    if i.guild.voice_client: await i.guild.voice_client.disconnect(); await i.response.send_message("⏹️")

@bot.tree.command(name="top", description="Топ чарт (Микс)")
async def slash_top(i: discord.Interaction):
    await slash_play(i, "Топ 100 русских песен 2024 микс")

# --- ОСТАЛЬНОЙ ФУНКЦИОНАЛ (ПАНЕЛИ, РЫНОК, ПРИВАТКИ) ---
class AdminSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="🎵 Создать Чат Музыки", style=discord.ButtonStyle.blurple, row=0)
    async def b_mc(self, i, b): ch=await i.guild.create_text_channel("music-cmd", overwrites=get_public_perms(i.guild)); update_config(i.guild.id, "music_text_channel_id", ch.id); await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)
    
    @discord.ui.button(label="🏪 Создать Каналы Рынков", style=discord.ButtonStyle.danger, row=0)
    async def b_mk(self, i, b):
        ow = get_public_perms(i.guild)
        cat = await i.guild.create_category("РЫНОК")
        ft = await i.guild.create_text_channel("рынок-ft", category=cat, overwrites=ow)
        hw = await i.guild.create_text_channel("рынок-hw", category=cat, overwrites=ow)
        ad = await i.guild.create_text_channel("реклама", category=cat, overwrites=ow)
        cursor.execute("UPDATE configs SET market_ft_channel_id=?, market_hw_channel_id=?, market_ads_channel_id=? WHERE guild_id=?", (ft.id, hw.id, ad.id, i.guild.id)); conn.commit()
        await i.response.send_message("✅ Каналы созданы!", ephemeral=True)

    @discord.ui.button(label="🔊 Меню Приваток", style=discord.ButtonStyle.secondary, row=1)
    async def b_pv(self, i, b):
        c=await i.guild.create_category("Приватные Комнаты"); update_config(i.guild.id, "pvoice_category_id", c.id)
        ch=await i.guild.create_text_channel("create-room", overwrites=get_public_perms(i.guild)); await ch.send(embed=discord.Embed(title="🔊 Личный Войс", color=discord.Color.fuchsia()), view=PrivateVoiceView()); await i.response.send_message("✅", ephemeral=True)
    
    @discord.ui.button(label="🏪 Меню Рынка", style=discord.ButtonStyle.secondary, row=1)
    async def b_mm(self, i, b): ch=await i.guild.create_text_channel("create-ad", overwrites=get_public_perms(i.guild)); await ch.send(embed=discord.Embed(title="🏪 Рынок", color=discord.Color.orange()), view=MarketSelectView()); await i.response.send_message("✅", ephemeral=True)

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

    @discord.ui.button(label="📈 Статистика", style=discord.ButtonStyle.gray, row=3)
    async def b_st(self, i, b):
        ow={i.guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True)}
        c=await i.guild.create_category("📊 СТАТИСТИКА", overwrites=ow, position=0)
        await i.guild.create_voice_channel("Загрузка...", category=c); await i.guild.create_voice_channel("Загрузка...", category=c)
        update_config(i.guild.id, "stats_category_id", c.id); await i.response.send_message("✅", ephemeral=True)

class VerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Верификация", style=discord.ButtonStyle.green, custom_id="vp_btn")
    async def v(self, i, b): 
        c=get_config(i.guild.id); r=i.guild.get_role(c[1]) if c else None; 
        if r: await i.user.add_roles(r); await i.response.send_message("✅", ephemeral=True)

class TicketStartView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Тикет", style=discord.ButtonStyle.blurple, custom_id="ct_btn")
    async def c(self, i, b):
        c=get_config(i.guild.id); cat=i.guild.get_channel(c[3])
        ch=await i.guild.create_text_channel(f"ticket-{random.randint(1,999)}", category=cat)
        cursor.execute("INSERT INTO tickets (channel_id, author_id) VALUES (?, ?)", (ch.id, i.user.id)); conn.commit()
        await ch.set_permissions(i.user, read_messages=True, send_messages=True)
        await ch.send(f"{i.user.mention}", embed=discord.Embed(title="Тикет"), view=TicketControlView()); await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Закрыть", style=discord.ButtonStyle.red, custom_id="clt_btn")
    async def cl(self, i, b): await i.channel.delete()

class PrivateVoiceView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="➕ Создать комнату", style=discord.ButtonStyle.blurple, custom_id="cpv_btn")
    async def cr(self, i, b): await i.response.send_modal(PrivateVoiceCreateModal())

class PrivateVoiceCreateModal(discord.ui.Modal, title='Создать'):
    v_name = discord.ui.TextInput(label='Название', max_length=20)
    async def on_submit(self, i):
        c=get_config(i.guild.id); cat=i.guild.get_channel(c[14])
        ow = {i.guild.default_role: discord.PermissionOverwrite(connect=False), i.user: discord.PermissionOverwrite(connect=True, manage_channels=True)}
        vc = await i.guild.create_voice_channel(name=self.v_name.value, category=cat, overwrites=ow)
        cursor.execute("INSERT INTO voice_channels (voice_id, owner_id) VALUES (?, ?)", (vc.id, i.user.id)); conn.commit()
        if i.user.voice: await i.user.move_to(vc)
        await i.response.send_message(f"✅ {vc.mention}", ephemeral=True)

class PrivateVoiceControl(discord.ui.View): # Заглушка, чтобы не крашило, если вызовется
    def __init__(self, vc): super().__init__(timeout=None)

class MarketSelectView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="FunTime", style=discord.ButtonStyle.danger, emoji="🧡", custom_id="m_ft")
    async def ft(self, i, b): c=get_config(i.guild.id); await i.response.send_modal(MarketModal("FT", c[10]))
    @discord.ui.button(label="HolyWorld", style=discord.ButtonStyle.primary, emoji="💙", custom_id="m_hw")
    async def hw(self, i, b): c=get_config(i.guild.id); await i.response.send_modal(MarketModal("HW", c[11]))
    @discord.ui.button(label="Реклама", style=discord.ButtonStyle.secondary, emoji="📢", custom_id="m_ad")
    async def ad(self, i, b): c=get_config(i.guild.id); await i.response.send_modal(MarketModal("AD", c[12]))

class MarketModal(discord.ui.Modal, title='Продажа'):
    item_name = discord.ui.TextInput(label='Товар')
    item_price = discord.ui.TextInput(label='Цена')
    def __init__(self, m_type, c_id): super().__init__(); self.m_type=m_type; self.c_id=c_id
    async def on_submit(self, i):
        ch = i.guild.get_channel(self.c_id)
        emb = discord.Embed(title=f"🛒 {self.m_type}", color=discord.Color.orange())
        emb.add_field(name="📦", value=self.item_name.value); emb.add_field(name="💰", value=self.item_price.value)
        emb.set_footer(text=f"Продавец: {i.user.name}")
        await ch.send(embed=emb); await i.response.send_message("✅", ephemeral=True)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
    update_stats_loop.start()
    bot.add_view(VerifyView()); bot.add_view(TicketStartView()); bot.add_view(TicketControlView()); bot.add_view(AdminSelect()); bot.add_view(MarketSelectView()); bot.add_view(PrivateVoiceView())

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
