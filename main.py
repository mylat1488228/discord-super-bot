import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import sqlite3
import random
import yt_dlp
import datetime
import feedparser
import re
import os

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("DISCORD_TOKEN")
ADMINS = ["defaultpeople", "anyachkaaaaa"] 

# Включаем все интенты
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

# Создание таблиц
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
    welcome_channel_id INTEGER
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

# --- МУЗЫКАЛЬНЫЕ НАСТРОЙКИ ---
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
    'source_address': '0.0.0.0'
}
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
        
        # Поиск по названию
        if not url.startswith("http"):
            url = f"ytsearch:{url}"
        
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data: data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

# --- 1. ВЕРИФИКАЦИЯ ---
class VerifyModal(discord.ui.Modal, title='Верификация'):
    code_input = discord.ui.TextInput(label='Введите код ниже', style=discord.TextStyle.short)
    def __init__(self, code, role_id):
        super().__init__()
        self.generated_code = code
        self.role_id = role_id
        self.code_input.label = f"Введите этот код: {code}"

    async def on_submit(self, interaction: discord.Interaction):
        if self.code_input.value == self.generated_code:
            role = interaction.guild.get_role(self.role_id)
            if role:
                try:
                    await interaction.user.add_roles(role)
                    await interaction.response.send_message(f"✅ Доступ открыт!", ephemeral=True)
                except:
                    await interaction.response.send_message("❌ Ошибка прав! Поднимите роль бота ВЫШЕ роли Verified.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Роль не найдена.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Неверный код.", ephemeral=True)

class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Пройти верификацию", style=discord.ButtonStyle.green, custom_id="verify_persistent_btn", emoji="✅")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        cursor.execute("SELECT verify_role_id FROM configs WHERE guild_id = ?", (interaction.guild.id,))
        res = cursor.fetchone()
        if not res or not res[0]: return await interaction.response.send_message("❌ Верификация сбилась.", ephemeral=True)
        role = interaction.guild.get_role(res[0])
        if not role: return await interaction.response.send_message("❌ Роль удалена.", ephemeral=True)
        if role in interaction.user.roles: return await interaction.response.send_message("✅ Вы уже тут.", ephemeral=True)
        code = str(random.randint(1000, 9999))
        await interaction.response.send_modal(VerifyModal(code, res[0]))

# --- 2. ТИКЕТЫ ---
class TicketControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="🔒 Закрыть тикет", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        conf = get_config(interaction.guild.id)
        support_role = interaction.guild.get_role(conf[2]) if conf and conf[2] else None
        
        cursor.execute("SELECT author_id FROM tickets WHERE channel_id = ?", (interaction.channel.id,))
        ticket_data = cursor.fetchone()
        if not ticket_data: return await interaction.response.send_message("Ошибка.", ephemeral=True)

        is_support = support_role in interaction.user.roles if support_role else False
        if interaction.user.id == ticket_data[0] or is_support or interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Закрытие...")
            if conf and conf[4]:
                log_chan = interaction.guild.get_channel(conf[4])
                if log_chan:
                    msgs = [m async for m in interaction.channel.history(limit=200)]
                    content = "\n".join([f"{m.author.name}: {m.content}" for m in reversed(msgs)])
                    with open(f"/tmp/{interaction.channel.name}.txt", "w", encoding="utf-8") as f: f.write(content)
                    await log_chan.send(f"📕 Тикет закрыт: {interaction.channel.name}", file=discord.File(f"/tmp/{interaction.channel.name}.txt"))
            await asyncio.sleep(2)
            await interaction.channel.delete()
            cursor.execute("DELETE FROM tickets WHERE channel_id = ?", (interaction.channel.id,))
            conn.commit()
        else: await interaction.response.send_message("Нет прав.", ephemeral=True)

class TicketStartView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="📩 Создать тикет", style=discord.ButtonStyle.blurple, custom_id="create_ticket_btn")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        conf = get_config(interaction.guild.id)
        if not conf or not conf[3]: return await interaction.response.send_message("❌ Не настроено.", ephemeral=True)
        cat = interaction.guild.get_channel(conf[3])
        cursor.execute("SELECT COUNT(*) FROM tickets")
        count = cursor.fetchone()[0] + 1
        overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False), interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True), interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)}
        if conf[2]: 
            r = interaction.guild.get_role(conf[2])
            if r: overwrites[r] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        ch = await interaction.guild.create_text_channel(name=f"ticket-{count}", category=cat, overwrites=overwrites)
        cursor.execute("INSERT INTO tickets (channel_id, author_id, status, timestamp) VALUES (?, ?, ?, ?)", (ch.id, interaction.user.id, 'open', datetime.datetime.now()))
        conn.commit()
        await ch.send(f"{interaction.user.mention}", embed=discord.Embed(title=f"Тикет #{count}", description="Опишите проблему.", color=discord.Color.blue()), view=TicketControlView())
        await interaction.response.send_message(f"✅ Создано: {ch.mention}", ephemeral=True)

# --- 3. АДМИН ПАНЕЛЬ ---
class YouTubeURLModal(discord.ui.Modal, title='YouTube'):
    url = discord.ui.TextInput(label='Ссылка')
    async def on_submit(self, interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            info = await asyncio.to_thread(lambda: ytdl.extract_info(self.url.value, download=False))
            rss = f"https://www.youtube.com/feeds/videos.xml?channel_id={info.get('channel_id')}"
            update_config(interaction.guild.id, "youtube_channel_url", rss)
            await interaction.followup.send(f"✅ Подключен: {info.get('uploader')}")
        except: await interaction.followup.send("Ошибка.")

class AdminSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Роль Поддержки", row=0)
    async def sel_sup(self, interaction, select):
        update_config(interaction.guild.id, "support_role_id", select.values[0].id)
        await interaction.response.send_message(f"✅ Поддержка: {select.values[0].mention}", ephemeral=True)
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Логи", channel_types=[discord.ChannelType.text], row=1)
    async def sel_log(self, interaction, select):
        update_config(interaction.guild.id, "ticket_log_channel_id", select.values[0].id)
        await interaction.response.send_message(f"✅ Логи: {select.values[0].mention}", ephemeral=True)
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Музыка", channel_types=[discord.ChannelType.text], row=2)
    async def sel_mus(self, interaction, select):
        update_config(interaction.guild.id, "music_channel_id", select.values[0].id)
        await interaction.response.send_message(f"✅ Музыка: {select.values[0].mention}", ephemeral=True)
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="YouTube канал", channel_types=[discord.ChannelType.text], row=3)
    async def sel_yt(self, interaction, select):
        update_config(interaction.guild.id, "notification_channel_id", select.values[0].id)
        await interaction.response.send_message(f"✅ YouTube посты: {select.values[0].mention}", ephemeral=True)
    @discord.ui.button(label="🔗 YouTube Ссылка", style=discord.ButtonStyle.blurple, row=4)
    async def btn_yt(self, interaction, button): await interaction.response.send_modal(YouTubeURLModal())
    
    # --- КНОПКА СОЗДАНИЯ ВЕРИФИКАЦИИ ---
    @discord.ui.button(label="🛠 Создать Верификацию", style=discord.ButtonStyle.green, row=4)
    async def btn_ver(self, interaction, button):
        await interaction.response.send_message("⚙️ Создаю...", ephemeral=True)
        guild = interaction.guild
        
        # 1. СНАЧАЛА Создаем роль
        verified_role = await guild.create_role(name="Verified", permissions=discord.Permissions(read_messages=True, view_channels=True, send_messages=True, connect=True, speak=True), color=discord.Color.green())
        
        # 2. Обновляем конфиг
        update_config(guild.id, "verify_role_id", verified_role.id)
        
        # 3. Создаем канал
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channels=True, read_messages=True, send_messages=False),
            verified_role: discord.PermissionOverwrite(view_channels=False), # Верифицированные его не видят
            guild.me: discord.PermissionOverwrite(view_channels=True)
        }
        verify_channel = await guild.create_text_channel("verify", overwrites=overwrites)
        await verify_channel.send(embed=discord.Embed(title="🛡 Верификация", description="Нажмите кнопку.", color=discord.Color.gold()), view=VerifyView())
        
        # 4. И ТОЛЬКО В КОНЦЕ пытаемся скрыть каналы (это может не сработать, но роль уже есть!)
        msg_end = f"✅ Успешно! Роль: {verified_role.mention}, Канал: {verify_channel.mention}."
        try:
            await guild.default_role.edit(permissions=discord.Permissions(read_messages=False, view_channels=False))
            msg_end += "\n✅ Изоляция настроена автоматически."
        except:
            msg_end += "\n⚠️ Не удалось скрыть каналы для @everyone автоматически. Зайдите в настройки роли @everyone и отключите 'Просмотр каналов' вручную."
        
        await interaction.followup.send(msg_end)

    @discord.ui.button(label="🎫 Создать Тикеты", style=discord.ButtonStyle.gray, row=4)
    async def btn_tic(self, interaction, button):
        cat = await interaction.guild.create_category("Поддержка")
        update_config(interaction.guild.id, "ticket_category_id", cat.id)
        ch = await interaction.guild.create_text_channel("create-ticket", category=cat)
        await ch.send(embed=discord.Embed(title="Поддержка", description="Создать тикет:", color=discord.Color.blue()), view=TicketStartView())
        await interaction.response.send_message("✅ Готово.", ephemeral=True)

# --- 4. МУЗЫКА ---
@bot.command()
async def play(ctx, *, query):
    conf = get_config(ctx.guild.id)
    if conf and conf[5] and ctx.channel.id != conf[5]: return await ctx.send(f"🚫 Только в <#{conf[5]}>!", delete_after=5)
    if not ctx.author.voice: return await ctx.send("Зайдите в ГК!")
    
    if ctx.voice_client is None: await ctx.author.voice.channel.connect()
    else: await ctx.voice_client.move_to(ctx.author.voice.channel)
    
    msg = await ctx.send(f"🔎 Ищу: **{query}**...")
    async with ctx.typing():
        try:
            player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
            if ctx.voice_client.is_playing(): ctx.voice_client.stop()
            ctx.voice_client.play(player, after=lambda e: print(e) if e else None)
            await msg.edit(content=f'🎶 Играет: **{player.title}**')
        except Exception as e: await msg.edit(content=f"⚠️ Ошибка: {e}")

@bot.command()
async def stop(ctx):
    if ctx.voice_client: await ctx.voice_client.disconnect(); await ctx.send("⏹️")

# --- КОМАНДЫ И СОБЫТИЯ ---
@bot.command()
async def reset(ctx):
    if ctx.author.guild_permissions.administrator:
        cursor.execute("DELETE FROM configs WHERE guild_id = ?", (ctx.guild.id,))
        conn.commit()
        await ctx.send("✅ Сброшено.")

@bot.command()
async def setup(ctx):
    """Создать админ-панель вручную"""
    if ctx.author.guild_permissions.administrator or ctx.author.name in ADMINS:
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        overwrites[ctx.author] = discord.PermissionOverwrite(read_messages=True)
        cat = await ctx.guild.create_category("BOT SETTINGS", overwrites=overwrites)
        chan = await ctx.guild.create_text_channel("admin-panel", category=cat)
        embed = discord.Embed(title="⚙️ Админ Панель", description="Управление ботом.", color=discord.Color.dark_grey())
        await chan.send(embed=embed, view=AdminSelect())
        await ctx.send(f"✅ Панель создана: {chan.mention}")
    else:
        await ctx.send("Нет прав.")

@bot.command()
async def admin(ctx):
    if ctx.author.guild_permissions.administrator or ctx.author.name in ADMINS:
        await ctx.send(embed=discord.Embed(title="⚙️ Админ Панель", color=discord.Color.dark_grey()), view=AdminSelect())

# АВТО-СОЗДАНИЕ ПРИ ДОБАВЛЕНИИ БОТА НА СЕРВЕР
@bot.event
async def on_guild_join(guild):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True)
    }
    if guild.owner: overwrites[guild.owner] = discord.PermissionOverwrite(read_messages=True)
    try:
        cat = await guild.create_category("BOT SETTINGS", overwrites=overwrites)
        chan = await guild.create_text_channel("admin-panel", category=cat)
        embed = discord.Embed(title="⚙️ Админ Панель", description="Управление ботом.", color=discord.Color.dark_grey())
        await chan.send(embed=embed, view=AdminSelect())
    except: pass

@tasks.loop(minutes=5)
async def check_updates():
    cursor.execute("SELECT guild_id, youtube_channel_url, youtube_last_video_id, notification_channel_id FROM configs")
    for row in cursor.fetchall():
        try:
            feed = feedparser.parse(row[1])
            if feed.entries and feed.entries[0].yt_videoid != row[2]:
                bot.get_channel(row[3]).send(f"🚨 **Новое видео!**\n{feed.entries[0].link}")
                update_config(row[0], "youtube_last_video_id", feed.entries[0].yt_videoid)
        except: pass

@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and "Создать войс" in after.channel.name:
        guild = member.guild
        overwrites = {guild.default_role: discord.PermissionOverwrite(connect=True), member: discord.PermissionOverwrite(connect=True, manage_channels=True, move_members=True)}
        vc = await guild.create_voice_channel(f"Комната {member.name}", category=after.channel.category, overwrites=overwrites)
        await member.move_to(vc)
        cursor.execute("INSERT INTO voice_channels (voice_id, owner_id) VALUES (?, ?)", (vc.id, member.id))
        conn.commit()
    if before.channel:
        cursor.execute("SELECT voice_id FROM voice_channels WHERE voice_id = ?", (before.channel.id,))
        if cursor.fetchone() and len(before.channel.members) == 0:
            await before.channel.delete()
            cursor.execute("DELETE FROM voice_channels WHERE voice_id = ?", (before.channel.id,))
            conn.commit()

@bot.event
async def on_ready():
    print(f'Ready: {bot.user}')
    check_updates.start()
    bot.add_view(VerifyView())
    bot.add_view(TicketStartView())
    bot.add_view(TicketControlView())
    bot.add_view(AdminSelect())

bot.run(TOKEN)
