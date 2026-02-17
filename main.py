import discord
from discord.ext import commands, tasks
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
import traceback

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("DISCORD_TOKEN")
ADMINS = ["defaultpeople", "anyachkaaaaa"] 

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

# Таблицы
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
    leave_channel_id INTEGER
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
    try:
        background = Image.open(bg_filename).convert("RGBA")
    except:
        background = Image.new("RGBA", (1000, 400), (20, 20, 60))

    background = background.resize((1000, 400))
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(member.display_avatar.url) as resp:
                avatar_bytes = await resp.read()
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
    except:
        avatar = Image.new("RGBA", (250, 250), (100, 100, 100))

    avatar = avatar.resize((250, 250))
    
    mask = Image.new("L", (250, 250), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((0, 0, 250, 250), fill=255)
    
    stroke = Image.new("RGBA", (260, 260), (0, 0, 0, 0))
    draw_stroke = ImageDraw.Draw(stroke)
    draw_stroke.ellipse((0, 0, 260, 260), fill=None, outline=(0, 191, 255), width=5)

    output = background.copy()
    output.paste(stroke, (50, 70), stroke)
    output.paste(avatar, (55, 75), mask)

    draw = ImageDraw.Draw(output)
    try:
        font_large = ImageFont.truetype("font.ttf", 80)
        font_small = ImageFont.truetype("font.ttf", 50)
    except:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    text_x = 350
    text_y = 100

    draw.text((text_x + 4, text_y + 4), title_text, fill="black", font=font_large)
    draw.text((text_x + 4, text_y + 104), str(member), fill="black", font=font_small)
    draw.text((text_x, text_y), title_text, fill=(255, 255, 255), font=font_large)
    draw.text((text_x, text_y + 100), str(member), fill=(0, 255, 255), font=font_small)

    buffer = io.BytesIO()
    output.save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="welcome.png")

# --- МУЗЫКА ---
yt_dlp.utils.bug_reports_message = lambda: ''
ytdl_format_options = {'format': 'bestaudio/best', 'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s', 'restrictfilenames': True, 'noplaylist': True, 'nocheckcertificate': True, 'ignoreerrors': False, 'logtostderr': False, 'quiet': True, 'no_warnings': True, 'default_search': 'auto', 'source_address': '0.0.0.0'}
ffmpeg_options = {'options': '-vn'}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        if not url.startswith("http"): url = f"ytsearch:{url}"
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data: data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# --- ИНТЕРФЕЙСЫ ---
class VerifyModal(discord.ui.Modal, title='Верификация'):
    code_input = discord.ui.TextInput(label='Введите код', style=discord.TextStyle.short)
    def __init__(self, code, role_id):
        super().__init__()
        self.generated_code = code
        self.role_id = role_id
        self.code_input.label = f"Код: {code}"
    async def on_submit(self, interaction: discord.Interaction):
        if self.code_input.value == self.generated_code:
            role = interaction.guild.get_role(self.role_id)
            if role:
                try: await interaction.user.add_roles(role); await interaction.response.send_message(f"✅ Успех!", ephemeral=True)
                except: await interaction.response.send_message("❌ Нет прав на выдачу роли.", ephemeral=True)
        else: await interaction.response.send_message("❌ Неверно.", ephemeral=True)

class VerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Верификация", style=discord.ButtonStyle.green, custom_id="verify_persistent_btn")
    async def verify(self, interaction, button):
        cursor.execute("SELECT verify_role_id FROM configs WHERE guild_id = ?", (interaction.guild.id,))
        res = cursor.fetchone()
        if not res or not res[0]: return await interaction.response.send_message("❌ Ошибка конфига.", ephemeral=True)
        role = interaction.guild.get_role(res[0])
        if role in interaction.user.roles: return await interaction.response.send_message("✅ Вы уже верифицированы.", ephemeral=True)
        code = str(random.randint(1000, 9999))
        await interaction.response.send_modal(VerifyModal(code, res[0]))

class TicketStartView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Создать тикет", style=discord.ButtonStyle.blurple, custom_id="create_ticket_btn")
    async def create(self, interaction, button):
        conf = get_config(interaction.guild.id)
        if not conf or not conf[3]: return await interaction.response.send_message("❌ Не настроено.", ephemeral=True)
        cat = interaction.guild.get_channel(conf[3])
        cursor.execute("SELECT COUNT(*) FROM tickets")
        count = cursor.fetchone()[0] + 1
        overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False), interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True), interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)}
        if conf[2]: 
            r = interaction.guild.get_role(conf[2])
            if r: overwrites[r] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        ch = await interaction.guild.create_text_channel(f"ticket-{count}", category=cat, overwrites=overwrites)
        cursor.execute("INSERT INTO tickets (channel_id, author_id, status, timestamp) VALUES (?, ?, ?, ?)", (ch.id, interaction.user.id, 'open', datetime.datetime.now()))
        conn.commit()
        await ch.send(f"{interaction.user.mention}", embed=discord.Embed(title=f"Тикет #{count}", description="Опишите проблему."), view=TicketControlView())
        await interaction.response.send_message(f"✅ {ch.mention}", ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Закрыть", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close(self, interaction, button):
        cursor.execute("SELECT author_id FROM tickets WHERE channel_id = ?", (interaction.channel.id,))
        res = cursor.fetchone()
        if not res: return
        await interaction.channel.delete()
        cursor.execute("DELETE FROM tickets WHERE channel_id = ?", (interaction.channel.id,))
        conn.commit()

class AdminSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Роль поддержки", row=0)
    async def sel_sup(self, interaction, select): update_config(interaction.guild.id, "support_role_id", select.values[0].id); await interaction.response.send_message("✅", ephemeral=True)
    
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Канал ПРИВЕТСТВИЙ", channel_types=[discord.ChannelType.text], row=1)
    async def sel_welcome(self, interaction, select): update_config(interaction.guild.id, "welcome_channel_id", select.values[0].id); await interaction.response.send_message(f"✅ Приветствия тут: {select.values[0].mention}", ephemeral=True)
    
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Канал ПРОЩАНИЙ", channel_types=[discord.ChannelType.text], row=2)
    async def sel_leave(self, interaction, select): update_config(interaction.guild.id, "leave_channel_id", select.values[0].id); await interaction.response.send_message(f"✅ Прощания тут: {select.values[0].mention}", ephemeral=True)

    @discord.ui.button(label="🛠 Создать Верификацию", style=discord.ButtonStyle.green, row=3)
    async def btn_ver(self, interaction, button):
        await interaction.response.send_message("⚙️ Создаю...", ephemeral=True)
        guild = interaction.guild
        try:
            # ИСПОЛЬЗУЕМ read_messages ВМЕСТО view_channels
            role = await guild.create_role(name="Verified", color=discord.Color.green(), permissions=discord.Permissions(read_messages=True, send_messages=True, connect=True, speak=True))
            update_config(guild.id, "verify_role_id", role.id)
            
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                role: discord.PermissionOverwrite(read_messages=False), 
                guild.me: discord.PermissionOverwrite(read_messages=True)
            }
            
            ch = await guild.create_text_channel("verify", overwrites=overwrites)
            await ch.send(embed=discord.Embed(title="🛡 Верификация", description="Нажмите кнопку для доступа.", color=discord.Color.gold()), view=VerifyView())
            
            # Попытка изоляции
            try: 
                await guild.default_role.edit(permissions=discord.Permissions(read_messages=False))
                await interaction.followup.send("✅ Готово! Изоляция включена.")
            except: 
                await interaction.followup.send("✅ Верификация создана! Но скройте каналы для @everyone вручную (нет прав).")
                
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка: {e}")
            print(e)

    @discord.ui.button(label="🎫 Тикеты", style=discord.ButtonStyle.gray, row=3)
    async def btn_tic(self, interaction, button):
        cat = await interaction.guild.create_category("Поддержка")
        update_config(interaction.guild.id, "ticket_category_id", cat.id)
        ch = await interaction.guild.create_text_channel("create-ticket", category=cat)
        await ch.send(embed=discord.Embed(title="Поддержка"), view=TicketStartView())
        await interaction.response.send_message("✅", ephemeral=True)

# --- СОБЫТИЯ ВХОДА И ВЫХОДА ---
@bot.event
async def on_member_join(member):
    conf = get_config(member.guild.id)
    if conf and conf[9]:
        channel = member.guild.get_channel(conf[9])
        if channel:
            file = await create_banner(member, "ДОБРО ПОЖАЛОВАТЬ", "welcome_bg.png")
            await channel.send(f"Привет, {member.mention}!", file=file)

@bot.event
async def on_member_remove(member):
    conf = get_config(member.guild.id)
    if conf and conf[10]:
        channel = member.guild.get_channel(conf[10])
        if channel:
            file = await create_banner(member, "ПРОЩАЙ", "goodbye_bg.png")
            await channel.send(f"{member.name} покинул нас...", file=file)

# --- ОСТАЛЬНОЕ ---
@bot.command()
async def play(ctx, *, query):
    if not ctx.author.voice: return await ctx.send("!")
    if ctx.voice_client is None: await ctx.author.voice.channel.connect()
    msg = await ctx.send(f"🔎 {query}...")
    try:
        player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
        if ctx.voice_client.is_playing(): ctx.voice_client.stop()
        ctx.voice_client.play(player)
        await msg.edit(content=f'🎶 {player.title}')
    except: await msg.edit(content="Ошибка")

@bot.command()
async def stop(ctx):
    if ctx.voice_client: await ctx.voice_client.disconnect()

@bot.command()
async def reset(ctx):
    if ctx.author.guild_permissions.administrator: cursor.execute("DELETE FROM configs WHERE guild_id=?", (ctx.guild.id,)); conn.commit(); await ctx.send("✅")

@bot.command()
async def admin(ctx):
    if ctx.author.guild_permissions.administrator or ctx.author.name in ADMINS:
        await ctx.send(embed=discord.Embed(title="⚙️ Админ Панель"), view=AdminSelect())

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    bot.add_view(VerifyView())
    bot.add_view(TicketStartView())
    bot.add_view(TicketControlView())
    bot.add_view(AdminSelect())

bot.run(TOKEN)
