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

# --- КОНФИГУРАЦИЯ RAILWAY ---
# Токен берется из переменных окружения (настроим на сайте)
TOKEN = os.getenv("DISCORD_TOKEN")

# Админы (впиши сюда точные ники)
ADMINS = ["defaultpeople", "anyachkaaaaa"]

# --- НАСТРОЙКИ INTENTS ---
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command('help')

# --- БАЗА ДАННЫХ (С СОХРАНЕНИЕМ НА RAILWAY VOLUME) ---
# Проверяем, подключен ли Volume в папку /app/data
if os.path.exists("/app/data"):
    DB_PATH = "/app/data/server_data.db"
    print("Используется постоянное хранилище Railway (/app/data)")
else:
    DB_PATH = "server_data.db"
    print("Используется локальное хранилище (тестовый режим)")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Создаем таблицы
cursor.execute('''CREATE TABLE IF NOT EXISTS tickets (
    channel_id INTEGER PRIMARY KEY,
    author_id INTEGER,
    status TEXT,
    timestamp DATETIME
)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS configs (
    guild_id INTEGER PRIMARY KEY,
    verify_role_id INTEGER,
    ticket_category_id INTEGER,
    ticket_log_channel_id INTEGER,
    support_role_id INTEGER,
    youtube_channel_url TEXT,
    notification_channel_id INTEGER,
    welcome_channel_id INTEGER
)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS voice_channels (
    voice_id INTEGER PRIMARY KEY,
    owner_id INTEGER
)''')
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
                await interaction.user.add_roles(role)
                await interaction.response.send_message(f"Вы успешно верифицированы! Роль {role.name} выдана.", ephemeral=True)
            else:
                await interaction.response.send_message("Ошибка: Роль верификации не найдена.", ephemeral=True)
        else:
            await interaction.response.send_message("Неверный код. Попробуйте снова.", ephemeral=True)

class VerifyView(discord.ui.View):
    def __init__(self, role_id):
        super().__init__(timeout=None)
        self.role_id = role_id

    @discord.ui.button(label="Верификация", style=discord.ButtonStyle.green, custom_id="verify_btn")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        code = str(random.randint(1000, 9999))
        await interaction.response.send_modal(VerifyModal(code, self.role_id))

# --- 2. ТИКЕТЫ ---

class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Закрыть тикет", style=discord.ButtonStyle.red, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cursor.execute("SELECT support_role_id, ticket_log_channel_id FROM configs WHERE guild_id = ?", (interaction.guild.id,))
        res = cursor.fetchone()
        support_role_id = res[0] if res else None
        log_channel_id = res[1] if res else None

        has_role = False
        if support_role_id:
            role = interaction.guild.get_role(support_role_id)
            if role and role in interaction.user.roles:
                has_role = True
        
        cursor.execute("SELECT author_id FROM tickets WHERE channel_id = ?", (interaction.channel.id,))
        ticket_data = cursor.fetchone()
        
        if not ticket_data:
            return await interaction.response.send_message("Это не канал тикета.", ephemeral=True)

        if interaction.user.id == ticket_data[0] or has_role or interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Тикет будет закрыт и удален через 5 секунд...")
            
            if log_channel_id:
                log_channel = interaction.guild.get_channel(log_channel_id)
                if log_channel:
                    messages = [message async for message in interaction.channel.history(limit=100)]
                    content = "\n".join([f"{m.author.name}: {m.content}" for m in reversed(messages)])
                    log_file_path = f"/tmp/log_{interaction.channel.name}.txt"
                    with open(log_file_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    await log_channel.send(f"Тикет {interaction.channel.name} закрыт пользователем {interaction.user.name}", file=discord.File(log_file_path))
                    os.remove(log_file_path)

            await asyncio.sleep(5)
            await interaction.channel.delete()
            cursor.execute("DELETE FROM tickets WHERE channel_id = ?", (interaction.channel.id,))
            conn.commit()
        else:
            await interaction.response.send_message("У вас нет прав закрыть этот тикет.", ephemeral=True)

class TicketStartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📩 Создать тикет", style=discord.ButtonStyle.blurple, custom_id="create_ticket_btn")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        cursor.execute("SELECT ticket_category_id, support_role_id FROM configs WHERE guild_id = ?", (interaction.guild.id,))
        res = cursor.fetchone()
        if not res or not res[0]:
            return await interaction.response.send_message("Система тикетов не настроена!", ephemeral=True)
        
        category = interaction.guild.get_channel(res[0])
        support_role = interaction.guild.get_role(res[1]) if res[1] else None

        cursor.execute("SELECT COUNT(*) FROM tickets")
        count = cursor.fetchone()[0] + 1
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{count}",
            category=category,
            overwrites=overwrites
        )

        cursor.execute("INSERT INTO tickets (channel_id, author_id, status, timestamp) VALUES (?, ?, ?, ?)", 
                       (channel.id, interaction.user.id, 'open', datetime.datetime.now()))
        conn.commit()

        embed = discord.Embed(title=f"Тикет #{count}", description="Опишите вашу проблему. Поддержка скоро ответит.\nВы желаете открыть тикет? (Уже открыт)", color=discord.Color.blue())
        await channel.send(f"{interaction.user.mention}", embed=embed, view=TicketControlView())
        await interaction.response.send_message(f"Тикет создан: {channel.mention}", ephemeral=True)

# --- 3. ПРИВАТНЫЕ ВОЙСЫ ---

class VoiceControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒/🔓", style=discord.ButtonStyle.gray, custom_id="vm_lock")
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice: return
        channel = interaction.user.voice.channel
        cursor.execute("SELECT owner_id FROM voice_channels WHERE voice_id = ?", (channel.id,))
        res = cursor.fetchone()
        if res and res[0] == interaction.user.id:
            current = channel.overwrites_for(interaction.guild.default_role).connect
            new_perm = False if current is None or current is True else True
            await channel.set_permissions(interaction.guild.default_role, connect=new_perm)
            status = "открыт" if new_perm else "закрыт"
            await interaction.response.send_message(f"Канал теперь {status} для всех.", ephemeral=True)
        else:
            await interaction.response.send_message("Вы не владелец.", ephemeral=True)

# --- 4. МУЗЫКА ---

@bot.command()
async def play(ctx, *, url):
    if not ctx.author.voice:
        return await ctx.send("Зайдите в голосовой канал!")
    
    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await channel.connect()
    else:
        await ctx.voice_client.move_to(channel)

    async with ctx.typing():
        try:
            player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
            if ctx.voice_client.is_playing():
                ctx.voice_client.stop()
            ctx.voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)
            await ctx.send(f'🎶 Играет: **{player.title}**')
        except Exception as e:
            await ctx.send(f"Ошибка воспроизведения: {e}")

@bot.command()
async def stop(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Музыка остановлена.")

# --- 5. АДМИН ПАНЕЛЬ ---

class AdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Настроить Тикеты", style=discord.ButtonStyle.primary)
    async def setup_tickets(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        cat = await guild.create_category("Поддержка")
        log_channel = await guild.create_text_channel("ticket-logs", category=cat)
        ticket_channel = await guild.create_text_channel("create-ticket", category=cat)
        
        cursor.execute("INSERT OR REPLACE INTO configs (guild_id, ticket_category_id, ticket_log_channel_id) VALUES (?, ?, ?)",
                       (guild.id, cat.id, log_channel.id))
        conn.commit()

        embed = discord.Embed(title="Поддержка", description="Нажмите кнопку ниже, чтобы создать тикет.", color=discord.Color.blue())
        await ticket_channel.send(embed=embed, view=TicketStartView())
        await interaction.response.send_message(f"Система тикетов создана!", ephemeral=True)

    @discord.ui.button(label="Настроить Верификацию", style=discord.ButtonStyle.green)
    async def setup_verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        role = await guild.create_role(name="Верифнутый", color=discord.Color.green())
        
        cursor.execute("UPDATE configs SET verify_role_id = ? WHERE guild_id = ?", (role.id, guild.id))
        if cursor.rowcount == 0:
             cursor.execute("INSERT INTO configs (guild_id, verify_role_id) VALUES (?, ?)", (guild.id, role.id))
        conn.commit()

        channel = await guild.create_text_channel("verify")
        embed = discord.Embed(title="Верификация", description="Нажмите кнопку, чтобы получить доступ.", color=discord.Color.gold())
        await channel.send(embed=embed, view=VerifyView(role.id))
        await interaction.response.send_message(f"Система верификации создана.", ephemeral=True)

@bot.event
async def on_guild_join(guild):
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True)
    }
    for member in guild.members:
        if member.name in ADMINS:
            overwrites[member] = discord.PermissionOverwrite(read_messages=True)

    cat = await guild.create_category("BOT SETTINGS", overwrites=overwrites)
    chan = await guild.create_text_channel("admin-panel", category=cat)
    embed = discord.Embed(title="Админ Панель", description="Управление функциями бота", color=discord.Color.dark_red())
    await chan.send(embed=embed, view=AdminPanelView())

# --- 6. ОБЩИЕ СОБЫТИЯ ---

@bot.event
async def on_message(message):
    if message.author.bot: return
    invites = ["discord.gg/", "discord.com/invite", "t.me/"]
    if any(x in message.content for x in invites):
        if not message.author.guild_permissions.administrator:
            await message.delete()
            await message.channel.send(f"{message.author.mention}, реклама запрещена!", delete_after=5)
            return
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    cursor.execute("SELECT welcome_channel_id FROM configs WHERE guild_id = ?", (member.guild.id,))
    res = cursor.fetchone()
    if res and res[0]:
        channel = member.guild.get_channel(res[0])
        if channel:
            embed = discord.Embed(title="Добро пожаловать!", description=f"Привет, {member.mention}! Рады видеть тебя на сервере.", color=discord.Color.purple())
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(f"{member.mention}", embed=embed)

@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and after.channel.name == "➕ Создать войс":
        guild = member.guild
        category = after.channel.category
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(connect=True),
            member: discord.PermissionOverwrite(connect=True, manage_channels=True, move_members=True)
        }
        voice_channel = await guild.create_voice_channel(name=f"Комната {member.name}", category=category, overwrites=overwrites)
        await member.move_to(voice_channel)
        cursor.execute("INSERT INTO voice_channels (voice_id, owner_id) VALUES (?, ?)", (voice_channel.id, member.id))
        conn.commit()

    if before.channel:
        cursor.execute("SELECT voice_id FROM voice_channels WHERE voice_id = ?", (before.channel.id,))
        if cursor.fetchone():
            if len(before.channel.members) == 0:
                await before.channel.delete()
                cursor.execute("DELETE FROM voice_channels WHERE voice_id = ?", (before.channel.id,))
                conn.commit()

@tasks.loop(minutes=10)
async def check_socials_and_tickets():
    cursor.execute("SELECT channel_id, timestamp FROM tickets WHERE status = 'open'")
    tickets = cursor.fetchall()
    now = datetime.datetime.now()
    for ticket in tickets:
        try:
            t_time = datetime.datetime.strptime(ticket[1], '%Y-%m-%d %H:%M:%S.%f')
            if (now - t_time).total_seconds() > 172800:
                channel = bot.get_channel(ticket[0])
                if channel:
                    await channel.send("Тикет закрыт из-за неактивности (48ч).")
                    await asyncio.sleep(2)
                    await channel.delete()
                    cursor.execute("DELETE FROM tickets WHERE channel_id = ?", (ticket[0],))
        except:
            continue
    conn.commit()

@bot.event
async def on_ready():
    print(f'Бот запущен: {bot.user}')
    check_socials_and_tickets.start()
    bot.add_view(VerifyView(0)) 
    bot.add_view(TicketStartView())
    bot.add_view(TicketControlView())
    bot.add_view(AdminPanelView())

@bot.command()
async def set_welcome(ctx):
    if ctx.author.guild_permissions.administrator:
        cursor.execute("UPDATE configs SET welcome_channel_id = ? WHERE guild_id = ?", (ctx.channel.id, ctx.guild.id))
        if cursor.rowcount == 0:
             cursor.execute("INSERT INTO configs (guild_id, welcome_channel_id) VALUES (?, ?)", (ctx.guild.id, ctx.channel.id))
        conn.commit()
        await ctx.send("Этот канал установлен для приветствий!")

@bot.command()
async def admin_menu(ctx):
    if ctx.author.name in ADMINS:
         await ctx.send("Панель управления:", view=AdminPanelView())

if TOKEN is None:
    print("ОШИБКА: Токен не найден в переменных окружения!")
else:
    bot.run(TOKEN)
