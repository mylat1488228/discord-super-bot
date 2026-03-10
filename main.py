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
    social_yt_id TEXT, 
    contest_channel_id INTEGER,
    media_channel_id INTEGER,
    last_video_id TEXT
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

# --- СИСТЕМА ПРАВ (ПО ТВОЕМУ ТЗ) ---

# 1. Каналы, где можно писать (New Players, Chat, Ticket, Music, Create menus)
def get_write_perms(guild):
    c = get_config(guild.id)
    verified = guild.get_role(c[1]) if c and c[1] else None
    
    # Новички не видят. Верифицированные видят и пишут.
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True)
    }
    if verified:
        overwrites[verified] = discord.PermissionOverwrite(
            view_channel=True, 
            read_messages=True, 
            send_messages=True, # Разрешено писать
            read_message_history=True,
            attach_files=True,
            embed_links=True
        )
    return overwrites

# 2. Каналы только для чтения (Rules, News, Partners)
def get_read_only_perms(guild):
    c = get_config(guild.id)
    verified = guild.get_role(c[1]) if c and c[1] else None
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, read_messages=True, send_messages=True)
    }
    if verified:
        overwrites[verified] = discord.PermissionOverwrite(
            view_channel=True, 
            read_messages=True, 
            send_messages=False, # Писать нельзя
            read_message_history=True,
            add_reactions=True # Реакции можно
        )
    return overwrites

# 3. Голосовые каналы
def get_voice_perms(guild):
    c = get_config(guild.id)
    verified = guild.get_role(c[1]) if c and c[1] else None
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, connect=True)
    }
    if verified:
        overwrites[verified] = discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            speak=True,
            stream=True
        )
    return overwrites

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
        if not url.startswith("http"): url = f"scsearch:{url}"
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
            if not c or not c[14]: return await i.response.send_message("❌ Не настроено.", ephemeral=True)
            cat = i.guild.get_channel(c[14])
            try: lim = int(self.v_limit.value) if self.v_limit.value else 0
            except: lim = 0
            
            # ПРАВА: БОТ ПОЛУЧАЕТ ПОЛНЫЙ ДОСТУП, ЧТОБЫ МОДЕРИРОВАТЬ
            ow = {
                i.guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True),
                i.user: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, move_members=True),
                i.guild.me: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, move_members=True)
            }
            
            vc = await i.guild.create_voice_channel(name=self.v_name.value, category=cat, user_limit=lim, overwrites=ow)
            cursor.execute("INSERT INTO voice_channels (voice_id, owner_id) VALUES (?, ?)", (vc.id, i.user.id)); conn.commit()
            if i.user.voice: await i.user.move_to(vc)
            await i.response.send_message(embed=discord.Embed(title=f"🔊 {self.v_name.value}", color=discord.Color.gold()), view=PrivateVoiceControl(vc), ephemeral=True)
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
            except: await i.response.send_message("❌ Ошибка прав. Поднимите роль бота выше роли Verified.", ephemeral=True)
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

# --- АДМИН ПАНЕЛЬ ---
class SocialsModal(discord.ui.Modal, title="Настройки"):
    yt_id = discord.ui.TextInput(label="YouTube Channel ID", required=False)
    async def on_submit(self, i): 
        cursor.execute("UPDATE configs SET social_yt_id=? WHERE guild_id=?", (self.yt_id.value, i.guild.id)); conn.commit()
        await i.response.send_message("✅ ID сохранен!", ephemeral=True)

class AdminSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    # 0. КАНАЛЫ (ПРАВА НАСТРОЕНЫ)
    @discord.ui.button(label="📁 Создать Основные Каналы", style=discord.ButtonStyle.success, row=0)
    async def b_create_all(self, i, b):
        await i.response.defer(ephemeral=True)
        guild = i.guild
        write_perms = get_write_perms(guild)
        read_perms = get_read_only_perms(guild)
        voice_perms = get_voice_perms(guild)

        # Категории
        cat_info = await guild.create_category("INFO")
        cat_voice = await guild.create_category("VOICES")
        
        # Текстовые (Read Only)
        await guild.create_text_channel("ʀᴜʟᴇ📜", category=cat_info, overwrites=read_perms)
        await guild.create_text_channel("ᴀɴɴᴏᴜɴᴄᴇᴍᴇɴᴛ📒", category=cat_info, overwrites=read_perms)
        await guild.create_text_channel("ᴘᴀʀᴛɴᴇʀs🤝", category=cat_info, overwrites=read_perms)
        
        # Текстовые (Write)
        np = await guild.create_text_channel("ɴᴇᴡ-ᴘʟᴀʏᴇʀs", category=cat_info, overwrites=write_perms)
        update_config(guild.id, "welcome_channel_id", np.id) # Авто-настройка приветствий
        await guild.create_text_channel("ᴄᴏᴍᴍᴜɴɪᴄᴀᴛɪᴏɴ📕", category=cat_info, overwrites=write_perms)
        
        # Голосовые
        for x in range(1, 4):
            await guild.create_voice_channel(f"ᴠᴏɪsᴇs {x}🍀", category=cat_voice, overwrites=voice_perms)
            
        await i.followup.send("✅ Все основные каналы созданы и настроены!", ephemeral=True)

    @discord.ui.button(label="🎵 Создать Чат Музыки", style=discord.ButtonStyle.blurple, row=1)
    async def b_mc(self, i, b): ch=await i.guild.create_text_channel("ᴍᴜsɪᴄ🎶", overwrites=get_write_perms(i.guild)); update_config(i.guild.id, "music_text_channel_id", ch.id); await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)
    
    @discord.ui.button(label="📺 Создать Медиа", style=discord.ButtonStyle.danger, row=1)
    async def b_md(self, i, b): ch=await i.guild.create_text_channel("📺┃медиа", overwrites=get_read_only_perms(i.guild)); update_config(i.guild.id, "media_channel_id", ch.id); await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)

    @discord.ui.button(label="🎉 Создать Конкурсы", style=discord.ButtonStyle.secondary, row=1)
    async def b_cn(self, i, b): ch=await i.guild.create_text_channel("🎉┃конкурсы", overwrites=get_read_only_perms(i.guild)); update_config(i.guild.id, "contest_channel_id", ch.id); await i.response.send_message(f"✅ {ch.mention}", ephemeral=True)

    # 1. МЕНЮ
    @discord.ui.button(label="🔊 Меню Приваток", style=discord.ButtonStyle.secondary, row=2)
    async def b_pv(self, i, b):
        c=await i.guild.create_category("🔊 Приватные Комнаты"); update_config(i.guild.id, "pvoice_category_id", c.id)
        ch=await i.guild.create_text_channel("create-room", overwrites=get_write_perms(i.guild)); await ch.send(embed=discord.Embed(title="🔊 Личный Войс", color=discord.Color.fuchsia()), view=PrivateVoiceView()); await i.response.send_message("✅", ephemeral=True)
    
    @discord.ui.button(label="🏪 Меню Рынка", style=discord.ButtonStyle.secondary, row=2)
    async def b_mm(self, i, b): ch=await i.guild.create_text_channel("create-ad", overwrites=get_write_perms(i.guild)); await ch.send(embed=discord.Embed(title="🏪 Рынок", color=discord.Color.orange()), view=MarketSelectView()); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🎉 Начать Конкурс", style=discord.ButtonStyle.secondary, row=2)
    async def b_sg(self, i, b): await i.response.send_modal(ContestCreateModal())

    # 2. НАСТРОЙКА
    @discord.ui.button(label="🏪 Каналы Рынков", style=discord.ButtonStyle.gray, row=3)
    async def b_mk(self, i, b):
        cat = await i.guild.create_category("🛒 РЫНОК")
        ft = await i.guild.create_text_channel("🧡┃рынок-ft", category=cat, overwrites=get_read_only_perms(i.guild))
        hw = await i.guild.create_text_channel("💙┃рынок-hw", category=cat, overwrites=get_read_only_perms(i.guild))
        cursor.execute("UPDATE configs SET market_ft_channel_id=?, market_hw_channel_id=? WHERE guild_id=?", (ft.id, hw.id, i.guild.id)); conn.commit()
        await i.response.send_message("✅ Каналы рынков созданы!", ephemeral=True)

    @discord.ui.button(label="⚙️ YouTube ID", style=discord.ButtonStyle.gray, row=3)
    async def b_yt(self, i, b): await i.response.send_modal(SocialsModal())

    @discord.ui.button(label="🎫 Тикеты", style=discord.ButtonStyle.primary, row=3)
    async def b_t(self, i, b): 
        c=await i.guild.create_category("📩 Support")
        # Логи скрыты
        l=await i.guild.create_text_channel("ticket-logs", category=c); update_config(i.guild.id, "ticket_log_channel_id", l.id)
        # Меню тикетов открыто для верифицированных
        update_config(i.guild.id, "ticket_category_id", c.id); ch=await i.guild.create_text_channel("tickets", category=c, overwrites=get_write_perms(i.guild)); await ch.send(embed=discord.Embed(title="Тикеты"), view=TicketStartView()); await i.response.send_message("✅", ephemeral=True)

    @discord.ui.button(label="🛠 Верификация", style=discord.ButtonStyle.green, row=4)
    async def b_v(self, i, b):
        # 1. Роль
        r=await i.guild.create_role(name="Verified", color=discord.Color.green(), permissions=discord.Permissions(view_channel=True, read_messages=True, send_messages=True, connect=True, speak=True)); update_config(i.guild.id, "verify_role_id", r.id)
        
        # 2. Канал (Только для новичков)
        ow = {
            i.guild.default_role: discord.PermissionOverwrite(view_channel=True, read_messages=True, read_message_history=True, send_messages=False),
            r: discord.PermissionOverwrite(view_channel=False),
            i.guild.me: discord.PermissionOverwrite(view_channel=True)
        }
        ch=await i.guild.create_text_channel("verify", overwrites=ow); await ch.send(embed=discord.Embed(title="Верификация", view=VerifyView())); await i.response.send_message("✅", ephemeral=True)
        
        # 3. Изоляция (Everyone не видит ничего, кроме verify)
        try: await i.guild.default_role.edit(permissions=discord.Permissions(read_messages=False, view_channel=False))
        except: pass

class ContestJoinView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="🎉 Участвовать", style=discord.ButtonStyle.success, custom_id="join_contest")
    async def join(self, i, b): await i.response.send_message("✅ Вы записаны!", ephemeral=True)

class ContestCreateModal(discord.ui.Modal, title="Создание Конкурса"):
    c_title = discord.ui.TextInput(label="Приз")
    c_desc = discord.ui.TextInput(label="Условия", style=discord.TextStyle.paragraph)
    c_img = discord.ui.TextInput(label="Ссылка на картинку", required=False)
    async def on_submit(self, i):
        c = get_config(i.guild.id)
        if not c or not c[16]: return await i.response.send_message("❌ Канал конкурсов не создан.", ephemeral=True)
        ch = i.guild.get_channel(c[16])
        emb = discord.Embed(title=f"🎉 КОНКУРС: {self.c_title.value}", description=self.c_desc.value, color=discord.Color.fuchsia())
        if self.c_img.value: emb.set_image(url=self.c_img.value)
        emb.set_footer(text=f"Создал: {i.user.name}")
        await ch.send(embed=emb, view=ContestJoinView())
        await i.response.send_message("✅ Конкурс опубликован!", ephemeral=True)

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
    try:
        if not i.guild.voice_client: await i.user.voice.channel.connect()
    except: pass
    
    try: 
        player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
        if i.guild.voice_client.is_playing(): i.guild.voice_client.stop()
        i.guild.voice_client.play(player)
        await i.followup.send(f"🎶 **{player.title}**")
    except asyncio.TimeoutError:
        await i.followup.send("⏳ Тайм-аут загрузки.")
    except Exception as e:
        await i.followup.send(f"❌ Ошибка: {e}")

@bot.tree.command(name="top", description="Топ 100")
async def top_ru(i: discord.Interaction):
    await slash_play(i, "Топ 100 русских песен 2024 микс")

@tasks.loop(minutes=5)
async def tasks_loop():
    cursor.execute("SELECT guild_id, stats_category_id, social_yt_id, media_channel_id, last_video_id FROM configs")
    for row in cursor.fetchall():
        guild = bot.get_guild(row[0])
        if not guild: continue

        # 1. Stats
        if row[1]:
            try:
                cat = guild.get_channel(row[1])
                st_ft = (await asyncio.wait_for((await JavaServer.async_lookup(FUNTIME_IP)).async_status(), 2.0)).players.online
                st_hw = (await asyncio.wait_for((await JavaServer.async_lookup(HOLYWORLD_IP)).async_status(), 2.0)).players.online
                names = [f"💎 Souls Visuals", f"👥 Людей: {guild.member_count}", f"🧡 FT: {st_ft}", f"💙 HW: {st_hw}"]
                for i, c in enumerate(cat.voice_channels):
                    if i < 4: await c.edit(name=names[i])
            except: pass

        # 2. YouTube
        if row[2] and row[3]:
            try:
                feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={row[2]}")
                if feed.entries:
                    latest = feed.entries[0]
                    if latest.yt_videoid != row[4]:
                        ch = guild.get_channel(row[3])
                        await ch.send(f"🎥 **Новое видео!**\n{latest.title}\n{latest.link}")
                        cursor.execute("UPDATE configs SET last_video_id=? WHERE guild_id=?", (latest.yt_videoid, row[0]))
                        conn.commit()
            except: pass

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
    tasks_loop.start()
    bot.add_view(VerifyView()); bot.add_view(TicketStartView()); bot.add_view(TicketControlView()); bot.add_view(AdminSelect()); bot.add_view(MarketSelectView()); bot.add_view(PrivateVoiceView()); bot.add_view(ContestJoinView())

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel:
        cursor.execute("SELECT voice_id FROM voice_channels WHERE voice_id = ?", (before.channel.id,))
        if cursor.fetchone() and len(before.channel.members) == 0:
            await before.channel.delete(); cursor.execute("DELETE FROM voice_channels WHERE voice_id = ?", (before.channel.id,)); conn.commit()

@bot.event
async def on_member_join(member):
    c=get_config(member.guild.id)
    # Если канал приветствий настроен (автоматом в b_create_all)
    if c and c[8]: 
        ch=member.guild.get_channel(c[8])
        if ch: 
            # КРАСИВОЕ ТЕКСТОВОЕ ПРИВЕТСТВИЕ БЕЗ ФОТО
            embed = discord.Embed(
                title=f"Добро пожаловать, {member.name}!",
                description=f"🎉 Рады видеть тебя на сервере **{member.guild.name}**!\n"
                            f"Не забудь прочитать правила и пройти верификацию.",
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Участник #{len(member.guild.members)}")
            await ch.send(f"{member.mention}", embed=embed)

@bot.command()
async def setup(ctx):
    if ctx.author.name not in ADMINS:
        return await ctx.send("⛔ Только Создатель бота.")
    if not ctx.guild.me.guild_permissions.administrator:
        return await ctx.send("❌ Дайте мне права АДМИНИСТРАТОРА!")
    try:
        cat = await ctx.guild.create_category("BOT SETTINGS")
        try: await cat.set_permissions(ctx.guild.default_role, read_messages=False)
        except: pass
        ch = await ctx.guild.create_text_channel("admin-panel", category=cat)
        await ch.send(embed=discord.Embed(title="⚙️ Админ Панель", description="Главное меню"), view=AdminSelect())
        await ctx.send(f"✅ Панель создана: {ch.mention}")
    except Exception as e: await ctx.send(f"Ошибка: {e}")

@bot.command()
async def fixmenus(ctx):
    if ctx.author.name not in ADMINS: return
    await ctx.send("🔧 Чиним права...")
    for ch_name in ["create-ad", "create-room", "shop", "tickets", "music-cmd", "поиск-ивентов"]:
        ch = discord.utils.get(ctx.guild.text_channels, name=ch_name)
        if ch: await ch.set_permissions(ctx.guild.default_role, view_channel=True, read_messages=True, read_message_history=True, send_messages=False)
    await ctx.send("✅ Готово!")

@bot.command()
async def reset(ctx):
    if ctx.author.name not in ADMINS: return
    cursor.execute("DELETE FROM configs WHERE guild_id=?", (ctx.guild.id,)); conn.commit(); await ctx.send("✅ Сброс")

@bot.command()
async def admin(ctx):
    if ctx.author.name in ADMINS: await ctx.send(embed=discord.Embed(title="⚙️ Админ Панель"), view=AdminSelect())

bot.run(TOKEN)
