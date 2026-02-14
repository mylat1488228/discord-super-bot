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

# --- МУЗЫКАЛЬНЫЕ НАСТРОЙКИ (ОБНОВЛЕННЫЕ) ---
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
        
        # --- ГЛАВНОЕ ИЗМЕНЕНИЕ: ПОИСК ПО НАЗВАНИЮ ---
        # Если это не ссылка (нет http), добавляем 'ytsearch:', чтобы искать на ютубе
        if not url.startswith("http"):
            url = f"ytsearch:{url}"
        
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        
        if 'entries' in data:
            # Если это поиск или плейлист, берем первое видео
            data = data['entries'][0]

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
                    await interaction.response.send_message(f"✅ Вы успешно верифицированы!", ephemeral=True)
                except discord.Forbidden:
                    await interaction.response.send_message("❌ Ошибка прав! Роль бота должна быть ВЫШЕ роли верификации.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Роль верификации не найдена. Попросите админа нажать !reset.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Неверный код.", ephemeral=True)

class VerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Пройти верификацию", style=discord.ButtonStyle.green, custom_id="verify_persistent_btn", emoji="✅")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        cursor.execute("SELECT verify_role_id FROM configs WHERE guild_id = ?", (interaction.guild.id,))
        res = cursor.fetchone()
        
        if not res or not res[0]:
            return await interaction.response.send_message("❌ Верификация сбилась. Введите !reset.", ephemeral=True)

        role_id = res[0]
        role = interaction.guild.get_role(role_id)
        
        if not role:
            return await interaction.response.send_message("❌ Роль удалена. Введите !reset.", ephemeral=True)

        if role in interaction.user.roles:
            return await interaction.response.send_message("✅ Вы уже верифицированы.", ephemeral=True)

        code = str(random.randint(1000, 9999))
        await interaction.response.send_modal(VerifyModal(code, role_id))

# --- 2. ТИКЕТЫ ---

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Закрыть тикет", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        conf = get_config(interaction.guild.id)
        support_role_id = conf[2] if conf else None
        log_channel_id = conf[4] if conf else None

        has_role = False
        if support_role_id:
            role = interaction.guild.get_role(support_role_id)
            if role and role in interaction.user.roles:
                has_role = True
        
        cursor.execute("SELECT author_id FROM tickets WHERE channel_id = ?", (interaction.channel.id,))
        ticket_data = cursor.fetchone()
        
        if not ticket_data:
            return await interaction.response.send_message("Ошибка тикета.", ephemeral=True)

        if interaction.user.id == ticket_data[0] or has_role or interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Тикет закрывается...")
            
            if log_channel_id:
                log_channel = interaction.guild.get_channel(log_channel_id)
                if log_channel:
                    messages = [message async for message in interaction.channel.history(limit=200)]
                    content = "\n".join([f"[{m.created_at.strftime('%H:%M')}] {m.author.name}: {m.content}" for m in reversed(messages)])
                    log_path = f"/tmp/log_{interaction.channel.name}.txt"
                    with open(log_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    await log_channel.send(f"📕 Тикет `{interaction.channel.name}` закрыт.", file=discord.File(log_path))
                    os.remove(log_path)

            await asyncio.sleep(3)
            await interaction.channel.delete()
            cursor.execute("DELETE FROM tickets WHERE channel_id = ?", (interaction.channel.id,))
            conn.commit()
        else:
            await interaction.response.send_message("Нет прав.", ephemeral=True)

class TicketStartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📩 Создать тикет", style=discord.ButtonStyle.blurple, custom_id="create_ticket_btn")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        conf = get_config(interaction.guild.id)
        if not conf or not conf[3]:
            return await interaction.response.send_message("❌ Тикеты не настроены (категория).", ephemeral=True)
        
        category = interaction.guild.get_channel(conf[3])
        support_role = interaction.guild.get_role(conf[2]) if conf[2] else None

        cursor.execute("SELECT COUNT(*) FROM tickets")
        count = cursor.fetchone()[0] + 1
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        channel = await interaction.guild.create_text_channel(name=f"ticket-{count}", category=category, overwrites=overwrites)
        cursor.execute("INSERT INTO tickets (channel_id, author_id, status, timestamp) VALUES (?, ?, ?, ?)", (channel.id, interaction.user.id, 'open', datetime.datetime.now()))
        conn.commit()

        embed = discord.Embed(title=f"Тикет #{count}", description="Опишите проблему.", color=discord.Color.blue())
        await channel.send(f"{interaction.user.mention}", embed=embed, view=TicketControlView())
        await interaction.response.send_message(f"✅ Тикет создан: {channel.mention}", ephemeral=True)

# --- 3. АДМИН ПАНЕЛЬ ---

class YouTubeURLModal(discord.ui.Modal, title='Настройка YouTube'):
    url = discord.ui.TextInput(label='Ссылка на канал YouTube')

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True) 
            info = await asyncio.to_thread(lambda: ytdl.extract_info(self.url.value, download=False))
            channel_id = info.get('channel_id')
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            update_config(interaction.guild.id, "youtube_channel_url", rss_url)
            await interaction.followup.send(f"✅ YouTube подключен: {info.get('uploader')}")
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка: {e}")

class AdminSelect(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Роль Поддержки", min_values=1, max_values=1, row=0)
    async def select_support_role(self, interaction: discord.Interaction, select: discord.ui.RoleSelect):
        update_config(interaction.guild.id, "support_role_id", select.values[0].id)
        await interaction.response.send_message(f"✅ Поддержка: {select.values[0].mention}", ephemeral=True)

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Канал логов", channel_types=[discord.ChannelType.text], row=1)
    async def select_log_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        update_config(interaction.guild.id, "ticket_log_channel_id", select.values[0].id)
        await interaction.response.send_message(f"✅ Логи: {select.values[0].mention}", ephemeral=True)

    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Канал музыки", channel_types=[discord.ChannelType.text], row=2)
    async def select_music_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        update_config(interaction.guild.id, "music_channel_id", select.values[0].id)
        await interaction.response.send_message(f"✅ Музыка: {select.values[0].mention}", ephemeral=True)
    
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Канал YouTube уведомлений", channel_types=[discord.ChannelType.text], row=3)
    async def select_yt_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        update_config(interaction.guild.id, "notification_channel_id", select.values[0].id)
        await interaction.response.send_message(f"✅ Уведомления: {select.values[0].mention}", ephemeral=True)

    @discord.ui.button(label="🔗 YouTube", style=discord.ButtonStyle.blurple, row=4)
    async def set_yt_url(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(YouTubeURLModal())

    @discord.ui.button(label="🛠 Создать Верификацию", style=discord.ButtonStyle.green, row=4)
    async def auto_verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        await interaction.response.send_message("⚙️ Создаю верификацию...", ephemeral=True)
        
        try:
            default_role = guild.default_role
            await default_role.edit(permissions=discord.Permissions(read_messages=False, view_channels=False))
        except:
            await interaction.followup.send("⚠️ Скройте каналы для @everyone вручную.", ephemeral=True)

        verified_role = await guild.create_role(name="Verified", permissions=discord.Permissions(read_messages=True, view_channels=True, send_messages=True, connect=True, speak=True), color=discord.Color.green())
        update_config(guild.id, "verify_role_id", verified_role.id)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channels=True, read_messages=True, send_messages=False),
            verified_role: discord.PermissionOverwrite(view_channels=False),
            guild.me: discord.PermissionOverwrite(view_channels=True)
        }
        verify_channel = await guild.create_text_channel("verify", overwrites=overwrites)
        
        embed = discord.Embed(title="🛡 Верификация", description="Нажмите кнопку, чтобы получить доступ.", color=discord.Color.gold())
        await verify_channel.send(embed=embed, view=VerifyView())
        
        await interaction.followup.send(f"✅ Успешно! Роль: {verified_role.mention}.")

    @discord.ui.button(label="🎫 Создать Тикеты", style=discord.ButtonStyle.gray, row=4)
    async def auto_tickets(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        cat = await guild.create_category("Поддержка")
        update_config(guild.id, "ticket_category_id", cat.id)
        
        ticket_channel = await guild.create_text_channel("create-ticket", category=cat)
        embed = discord.Embed(title="Поддержка", description="Нажмите кнопку ниже, чтобы создать тикет.", color=discord.Color.blue())
        await ticket_channel.send(embed=embed, view=TicketStartView())
        
        await interaction.response.send_message(f"✅ Тикеты созданы.", ephemeral=True)

# --- 4. МУЗЫКА (КОМАНДА PLAY) ---

@bot.command()
async def play(ctx, *, query):
    # Проверка канала
    conf = get_config(ctx.guild.id)
    if conf and conf[5]:
        if ctx.channel.id != conf[5]:
             return await ctx.send(f"🚫 Музыка только в канале <#{conf[5]}>!", delete_after=10)

    if not ctx.author.voice:
        return await ctx.send("Зайдите в голосовой канал!")
    
    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await channel.connect()
    else:
        await ctx.voice_client.move_to(channel)

    # Сообщение о поиске
    msg = await ctx.send(f"🔎 Ищу: **{query}**...")

    async with ctx.typing():
        try:
            # Класс YTDLSource сам разберется: ссылка это или название
            player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
            
            if ctx.voice_client.is_playing():
                ctx.voice_client.stop()
            
            ctx.voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)
            
            await msg.edit(content=f'🎶 Играет: **{player.title}**')
        except Exception as e:
            await msg.edit(content=f"⚠️ Не удалось найти или воспроизвести. Попробуйте точнее.")
            print(e)

@bot.command()
async def stop(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Музыка остановлена.")

# --- СБРОС И АДМИНКА ---
@bot.command()
async def reset(ctx):
    """Сбрасывает настройки бота"""
    if ctx.author.guild_permissions.administrator or ctx.author.name in ADMINS:
        cursor.execute("DELETE FROM configs WHERE guild_id = ?", (ctx.guild.id,))
        conn.commit()
        await ctx.send("✅ Настройки сброшены! Введите !admin.")
    else:
        await ctx.send("Нет прав.")

@bot.command()
async def admin(ctx):
    if ctx.author.name in ADMINS or ctx.author.guild_permissions.administrator:
        embed = discord.Embed(title="⚙️ Админ Панель", description="Настройка бота.", color=discord.Color.dark_grey())
        await ctx.send(embed=embed, view=AdminSelect())

# --- ЗАПУСК ---
@tasks.loop(minutes=5)
async def check_updates():
    cursor.execute("SELECT guild_id, youtube_channel_url, youtube_last_video_id, notification_channel_id FROM configs")
    for conf in cursor.fetchall():
        guild_id, rss_url, last_id, notif_channel_id = conf
        if not rss_url or not notif_channel_id: continue
        try:
            feed = feedparser.parse(rss_url)
            if feed.entries:
                latest = feed.entries[0]
                if latest.yt_videoid != last_id:
                    channel = bot.get_channel(notif_channel_id)
                    if channel:
                        await channel.send(f"🚨 **Новое видео!**\n{latest.title}\n{latest.link}")
                        update_config(guild_id, "youtube_last_video_id", latest.yt_videoid)
        except: pass

@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and "Создать войс" in after.channel.name:
        guild = member.guild
        overwrites = {guild.default_role: discord.PermissionOverwrite(connect=True), member: discord.PermissionOverwrite(connect=True, manage_channels=True, move_members=True)}
        voice_channel = await guild.create_voice_channel(name=f"Комната {member.name}", category=after.channel.category, overwrites=overwrites)
        await member.move_to(voice_channel)
        cursor.execute("INSERT INTO voice_channels (voice_id, owner_id) VALUES (?, ?)", (voice_channel.id, member.id))
        conn.commit()
    if before.channel:
        cursor.execute("SELECT voice_id FROM voice_channels WHERE voice_id = ?", (before.channel.id,))
        if cursor.fetchone() and len(before.channel.members) == 0:
            await before.channel.delete()
            cursor.execute("DELETE FROM voice_channels WHERE voice_id = ?", (before.channel.id,))
            conn.commit()

@bot.event
async def on_ready():
    print(f'Бот запущен: {bot.user}')
    check_updates.start()
    bot.add_view(VerifyView())
    bot.add_view(TicketStartView())
    bot.add_view(TicketControlView())
    bot.add_view(AdminSelect())

bot.run(TOKEN)
