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

# Добавили music_text_channel_id и поля для соцсетей
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
    social_twitch TEXT
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

# --- ПРИВАТНЫЕ ВОЙСЫ ---
class PrivateVoiceControl(discord.ui.View):
    def __init__(self, voice_channel): super().__init__(timeout=None); self.voice_channel = voice_channel
    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="➕ Добавить людей", min_values=1, max_values=10, row=0)
    async def whitelist_user(self, i, s):
        res = cursor.execute("SELECT owner_id FROM voice_channels WHERE voice_id = ?", (self.voice_channel.id,)).fetchone()
        if not res or res[0] != i.user.id: return await i.response.send_message("❌ Не владелец.", ephemeral=True)
        for u in s.values: await self.voice_channel.set_permissions(u, connect=True, view_channel=True)
        await i.response.send_message(f"✅ Добавлены.", ephemeral=True)
    @discord.ui.button(label="🔒 Закрыть", style=discord.ButtonStyle.red, row=1)
    async def l(self, i, b): await self.voice_channel.set_permissions(i.guild.default_role, connect=False); await i.response.send_message("🔒", ephemeral=True)
    @discord.ui.button(label="🔓 Открыть", style=discord.ButtonStyle.green, row=1)
    async def u(self, i, b): await self.voice_channel.set_permissions(i.guild.default_role, connect=True); await i.response.send_message("🔓", ephemeral=True)

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

# --- АДМИН ПАНЕЛЬ (НОВАЯ) ---
class SocialsModal(discord.ui.Modal, title="Настройка ссылок"):
    yt = discord.ui.TextInput(label="YouTube", required=False)
    tg = discord.ui.TextInput(label="Telegram", required=False)
    tt = discord.ui.TextInput(label="TikTok", required=False)
    tw = discord.ui.TextInput(label="Twitch", required=False)
    async def on_submit(self, i):
        # Сохраняем в БД
        cursor.execute("UPDATE configs SET social_yt=?, social_tg=?, social_tt=?, social_twitch=? WHERE guild_id=?", 
                       (self.yt.value, self.tg.value, self.tt.value, self.tw.value, i.guild.id))
        conn.commit()
        await i.response.send_message("✅ Ссылки сохранены!", ephemeral=True)

class AdminSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    # ROW 0: Выбор Текстового канала для музыки
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="1. Выберите ЧАТ для команд музыки", channel_types=[discord.ChannelType.text], row=0)
    async def s_mus_txt(self, i, s): update_config(i.guild.id, "music_text_channel_id", s.values[0].id); await i.response.send_message(f"✅ Команды музыки только в: {s.values[0].mention}", ephemeral=True)

    # ROW 1: Выбор Каналов Рынка (Один селект для FT)
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="2. Выберите канал РЫНКА FT", channel_types=[discord.ChannelType.text], row=1)
    async def s_ft(self, i, s): update_config(i.guild.id, "market_ft_channel_id", s.values[0].id); await i.response.send_message("✅ Рынок FT настроен", ephemeral=True)

    # ROW 2: Выбор Каналов Рынка (Один селект для HW)
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="3. Выберите канал РЫНКА HW", channel_types=[discord.ChannelType.text], row=2)
    async def s_hw(self, i, s): update_config(i.guild.id, "market_hw_channel_id", s.values[0].id); await i.response.send_message("✅ Рынок HW настроен", ephemeral=True)

    # ROW 3: Кнопки создания менюшек
    @discord.ui.button(label="🔊 Меню Приваток", style=discord.ButtonStyle.blurple, row=3)
    async def b_pv(self, i, b):
        cat = await i.guild.create_category("Приватные Комнаты")
        update_config(i.guild.id, "pvoice_category_id", cat.id)
        ch = await i.guild.create_text_channel("create-room")
        await ch.send(embed=discord.Embed(title="🔊 Личный Войс", description="Создайте свою комнату:", color=discord.Color.fuchsia()), view=PrivateVoiceView())
        await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🏪 Меню Рынка", style=discord.ButtonStyle.danger, row=3)
    async def b_m(self, i, b): ch=await i.guild.create_text_channel("create-ad"); await ch.send(embed=discord.Embed(title="🏪 Рынок", color=discord.Color.orange()), view=MarketSelectView()); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🔗 Соцсети", style=discord.ButtonStyle.secondary, row=3)
    async def b_soc(self, i, b): await i.response.send_modal(SocialsModal())

    # ROW 4: Кнопки системы
    @discord.ui.button(label="📈 Статистика", style=discord.ButtonStyle.gray, row=4)
    async def b_st(self, i, b):
        ow = {i.guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True)}
        cat = await i.guild.create_category("📊 СТАТИСТИКА", overwrites=ow, position=0)
        await i.guild.create_voice_channel("📊 Загрузка...", category=cat); await i.guild.create_voice_channel("👥 Загрузка...", category=cat)
        await i.guild.create_voice_channel("🧡 FT: ...", category=cat); await i.guild.create_voice_channel("💙 HW: ...", category=cat)
        update_config(i.guild.id, "stats_category_id", cat.id)
        await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🛠 Верификация", style=discord.ButtonStyle.green, row=4)
    async def b_v(self, i, b):
        r=await i.guild.create_role(name="Verified", color=discord.Color.green()); update_config(i.guild.id, "verify_role_id", r.id)
        ow={i.guild.default_role:discord.PermissionOverwrite(read_messages=True, send_messages=False), r:discord.PermissionOverwrite(read_messages=False), i.guild.me:discord.PermissionOverwrite(read_messages=True)}
        ch=await i.guild.create_text_channel("verify", overwrites=ow); await ch.send(embed=discord.Embed(title="Верификация"), view=VerifyView()); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🎫 Тикеты", style=discord.ButtonStyle.primary, row=4)
    async def b_t(self, i, b): c=await i.guild.create_category("Support"); update_config(i.guild.id, "ticket_category_id", c.id); ch=await i.guild.create_text_channel("tickets", category=c); await ch.send(embed=discord.Embed(title="Тикеты"), view=TicketStartView()); await i.response.send_message("✅", ephemeral=True)

# --- VIEWS ---
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

# --- МУЗЫКАЛЬНЫЕ КОМАНДЫ (ЧАРТЫ) ---
async def check_music_channel(interaction):
    conf = get_config(interaction.guild.id)
    # conf[6] = music_text_channel_id
    if conf and conf[6]:
        if interaction.channel.id != conf[6]:
            chan = interaction.guild.get_channel(conf[6])
            await interaction.response.send_message(f"🚫 Используйте команды музыки только в: {chan.mention}", ephemeral=True)
            return False
    return True

@bot.tree.command(name="play", description="Включить музыку")
async def slash_play(i: discord.Interaction, query: str):
    if not await check_music_channel(i): return
    await i.response.defer()
    if not i.user.voice: return await i.followup.send("Войс!")
    if not i.guild.voice_client: await i.user.voice.channel.connect()
    try: p=await YTDLSource.from_url(query, loop=bot.loop, stream=True); i.guild.voice_client.play(p); await i.followup.send(f"🎶 **{p.title}**")
    except: await i.followup.send("Ошибка")

@bot.tree.command(name="top_russia", description="Топ 100 России")
async def top_ru(i: discord.Interaction):
    if not await check_music_channel(i): return
    await i.response.defer(); 
    if not i.guild.voice_client: await i.user.voice.channel.connect()
    try: p=await YTDLSource.from_url("Топ 100 русских песен 2024 микс", loop=bot.loop, stream=True); i.guild.voice_client.play(p); await i.followup.send(f"🇷🇺 Включаю **ТОП России**")
    except: await i.followup.send("Ошибка")

@bot.tree.command(name="top_world", description="Топ Мировой")
async def top_wo(i: discord.Interaction):
    if not await check_music_channel(i): return
    await i.response.defer(); 
    if not i.guild.voice_client: await i.user.voice.channel.connect()
    try: p=await YTDLSource.from_url("Top 100 global songs 2024 mix", loop=bot.loop, stream=True); i.guild.voice_client.play(p); await i.followup.send(f"🌍 Включаю **ТОП Мира**")
    except: await i.followup.send("Ошибка")

@bot.tree.command(name="top_phonk", description="Топ Фонк")
async def top_ph(i: discord.Interaction):
    if not await check_music_channel(i): return
    await i.response.defer(); 
    if not i.guild.voice_client: await i.user.voice.channel.connect()
    try: p=await YTDLSource.from_url("Best Phonk Mix 2024", loop=bot.loop, stream=True); i.guild.voice_client.play(p); await i.followup.send(f"👿 Включаю **FONK**")
    except: await i.followup.send("Ошибка")

# --- СИСТЕМА ---
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
            
            names = [f"💎 {g.name}", f"👥 Людей: {g.member_count}", f"🧡 FT: {st_ft}", f"💙 HW: {st_hw}"]
            for i, c in enumerate(cat.voice_channels):
                if i < 4: await c.edit(name=names[i])
        except: pass

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
    update_stats_loop.start()
    bot.add_view(VerifyView()); bot.add_view(TicketStartView()); bot.add_view(TicketControlView()); bot.add_view(AdminSelect()); bot.add_view(MarketSelectView()); bot.add_view(PrivateVoiceView())

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
