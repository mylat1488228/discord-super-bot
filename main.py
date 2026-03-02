import discord
from discord.ext import commands, tasks
from discord import app_commands
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
from mcstatus import JavaServer

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("DISCORD_TOKEN")
ADMINS = ["defaultpeople", "anyachkaaaaa"] 
FUNTIME_IP = "play.funtime.su"
HOLYWORLD_IP = "mc.holyworld.ru"
SERVER_NAME = "Souls Visuals" # Название твоего сервера для статы

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
    youtube_channel_url TEXT,
    youtube_last_video_id TEXT,
    notification_channel_id INTEGER,
    welcome_channel_id INTEGER,
    leave_channel_id INTEGER,
    market_ft_channel_id INTEGER,
    market_hw_channel_id INTEGER,
    stats_category_id INTEGER,
    pvoice_category_id INTEGER,
    shop_category_id INTEGER,
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

# ==========================================
# 1. ЖИВАЯ СТАТИСТИКА (СВЕРХУ)
# ==========================================
@tasks.loop(minutes=5)
async def update_stats_loop():
    cursor.execute("SELECT guild_id, stats_category_id FROM configs")
    rows = cursor.fetchall()
    for row in rows:
        guild_id, cat_id = row
        if not cat_id: continue
        try:
            guild = bot.get_guild(guild_id)
            if not guild: continue
            
            # Получаем онлайн серверов
            try: 
                s_ft = await JavaServer.async_lookup(FUNTIME_IP)
                st_ft = await s_ft.async_status()
                ft_online = st_ft.players.online
            except: ft_online = "Off"

            try:
                s_hw = await JavaServer.async_lookup(HOLYWORLD_IP)
                st_hw = await s_hw.async_status()
                hw_online = st_hw.players.online
            except: hw_online = "Off"

            # Названия каналов
            ch_names = [
                f"💎 {SERVER_NAME}",
                f"👥 Людей: {guild.member_count}",
                f"🧡 FT: {ft_online}",
                f"💙 HW: {hw_online}"
            ]

            category = guild.get_channel(cat_id)
            if category:
                # Проходим по каналам в категории и обновляем их
                for i, channel in enumerate(category.voice_channels):
                    if i < len(ch_names) and channel.name != ch_names[i]:
                        await channel.edit(name=ch_names[i])
        except Exception as e: print(f"Stats Error: {e}")

# ==========================================
# 2. КОНКУРСЫ (GIVEAWAY)
# ==========================================

class ContestView(discord.ui.View):
    def __init__(self, buttons_data):
        super().__init__(timeout=None)
        # buttons_data = [{"label": "YouTube", "url": "..."}, ...]
        for btn in buttons_data:
            self.add_item(discord.ui.Button(label=btn['label'], url=btn['url']))

    @discord.ui.button(label="🎉 Участвовать", style=discord.ButtonStyle.blurple, custom_id="join_contest")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Логика участия (простая: просто пишет в ответ)
        # В идеале нужно писать в БД, но для простоты:
        await interaction.response.send_message(f"✅ Вы записаны в участники!", ephemeral=True)

class ContestCreateModal(discord.ui.Modal, title="Создание Конкурса"):
    c_title = discord.ui.TextInput(label="Название", max_length=50)
    c_desc = discord.ui.TextInput(label="Условия и Призы", style=discord.TextStyle.paragraph)
    c_photo = discord.ui.TextInput(label="Ссылка на фото", required=False)
    
    # Ссылки (можно ввести одну для теста, для множества нужно сложное меню, упростим)
    c_link_name = discord.ui.TextInput(label="Название кнопки (например YouTube)", required=False)
    c_link_url = discord.ui.TextInput(label="Ссылка", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title=f"🎉 {self.c_title.value}", description=self.c_desc.value, color=discord.Color.fuchsia())
        if self.c_photo.value: embed.set_image(url=self.c_photo.value)
        embed.set_footer(text="Нажмите кнопку ниже, чтобы участвовать!")
        
        btns = []
        if self.c_link_name.value and self.c_link_url.value:
            btns.append({"label": self.c_link_name.value, "url": self.c_link_url.value})
            
        await interaction.channel.send(embed=embed, view=ContestView(btns))
        await interaction.response.send_message("✅ Конкурс опубликован!", ephemeral=True)

# ==========================================
# 3. МАГАЗИН (SHOP SYSTEM)
# ==========================================

class ShopControlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    @discord.ui.button(label="✅ Оплатил", style=discord.ButtonStyle.green)
    async def paid(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"{interaction.user.mention} сообщил об оплате! Ожидайте администратора.", allowed_mentions=discord.AllowedMentions(users=True))

    @discord.ui.button(label="🔒 Закрыть сделку", style=discord.ButtonStyle.red)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.guild_permissions.administrator:
            await interaction.channel.delete()
        else:
            await interaction.response.send_message("Только админ может закрыть сделку.", ephemeral=True)

async def create_shop_channel(interaction, product_name, price):
    # Проверка на включенную платежку
    conf = get_config(interaction.guild.id)
    # conf[16] = payments_enabled (1 or 0)
    if conf and conf[16] == 0:
        return await interaction.response.send_message("⛔ Платежная система временно отключена администрацией.", ephemeral=True)

    guild = interaction.guild
    # Категория для заказов (ищем по имени или создаем)
    cat = discord.utils.get(guild.categories, name="🛒 Заказы")
    if not cat: cat = await guild.create_category("🛒 Заказы")
    
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        guild.me: discord.PermissionOverwrite(read_messages=True),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    
    # Создаем приватный канал
    ch_name = f"buy-{interaction.user.name}"[:20]
    ch = await guild.create_text_channel(ch_name, category=cat, overwrites=overwrites)
    
    embed = discord.Embed(title="🧾 СЧЕТ НА ОПЛАТУ", color=discord.Color.green())
    embed.add_field(name="Товар", value=product_name)
    embed.add_field(name="К оплате", value=price)
    embed.add_field(name="Реквизиты", value="Карта: `0000 0000 0000 0000` (Сбер)\nНик: `Admin`", inline=False)
    embed.set_footer(text="После оплаты прикрепите скриншот и нажмите кнопку.")
    
    await ch.send(f"{interaction.user.mention}", embed=embed, view=ShopControlView())
    await interaction.response.send_message(f"✅ Для оплаты перейдите в канал: {ch.mention}", ephemeral=True)

# --- VIEWS ДЛЯ МАГАЗИНА ---
class ShopAdsView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="1 день (без пинга) - 50р", style=discord.ButtonStyle.secondary)
    async def b1(self, i, b): await create_shop_channel(i, "Реклама 1 день (без пинга)", "50 RUB")
    @discord.ui.button(label="1 день (с пингом) - 100р", style=discord.ButtonStyle.primary)
    async def b2(self, i, b): await create_shop_channel(i, "Реклама 1 день (с пингом)", "100 RUB")
    @discord.ui.button(label="3 дня - 200р", style=discord.ButtonStyle.secondary)
    async def b3(self, i, b): await create_shop_channel(i, "Реклама 3 дня", "200 RUB")
    @discord.ui.button(label="Неделя - 400р", style=discord.ButtonStyle.primary)
    async def b4(self, i, b): await create_shop_channel(i, "Реклама Неделя", "400 RUB")

class ShopBotView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Полный бот - 1000р", style=discord.ButtonStyle.success)
    async def b1(self, i, b): await create_shop_channel(i, "Полный Бот", "1000 RUB")
    @discord.ui.button(label="Лайт версия - 500р", style=discord.ButtonStyle.secondary)
    async def b2(self, i, b): await create_shop_channel(i, "Лайт Бот", "500 RUB")

class ShopServerView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Полная (с ботом) - 1500р", style=discord.ButtonStyle.danger)
    async def b1(self, i, b): await create_shop_channel(i, "Настройка Full + Bot", "1500 RUB")
    @discord.ui.button(label="Без бота - 800р", style=discord.ButtonStyle.primary)
    async def b2(self, i, b): await create_shop_channel(i, "Настройка (без бота)", "800 RUB")
    @discord.ui.button(label="Только чаты - 300р", style=discord.ButtonStyle.secondary)
    async def b3(self, i, b): await create_shop_channel(i, "Настройка (только чаты)", "300 RUB")

class ShopCategorySelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.select(placeholder="Выберите категорию", min_values=1, max_values=1, options=[
        discord.SelectOption(label="Реклама", description="Пиар вашего проекта", emoji="📢"),
        discord.SelectOption(label="Бот", description="Покупка/Аренда бота", emoji="🤖"),
        discord.SelectOption(label="Настройка сервера", description="Оформление под ключ", emoji="⚙️"),
        discord.SelectOption(label="КФГ / Визуалы", description="Конфиги для читов", emoji="🎮")
    ])
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.Select):
        val = select.values[0]
        if val == "Реклама":
            await interaction.response.send_message("📢 **Выберите тариф рекламы:**", view=ShopAdsView(), ephemeral=True)
        elif val == "Бот":
            await interaction.response.send_message("🤖 **Выберите версию бота:**", view=ShopBotView(), ephemeral=True)
        elif val == "Настройка сервера":
            await interaction.response.send_message("⚙️ **Тип настройки:**", view=ShopServerView(), ephemeral=True)
        else:
            await create_shop_channel(interaction, f"Запрос: {val}", "Договорная")

# ==========================================
# 4. АДМИН ПАНЕЛЬ (ОБНОВЛЕННАЯ)
# ==========================================
class AdminSelect(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    # ROW 0
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Канал РЫНКА FunTime", channel_types=[discord.ChannelType.text], row=0)
    async def s_ft(self, i, s): update_config(i.guild.id, "market_ft_channel_id", s.values[0].id); await i.response.send_message("✅", ephemeral=True)
    
    # ROW 1
    @discord.ui.select(cls=discord.ui.ChannelSelect, placeholder="Канал РЫНКА HolyWorld", channel_types=[discord.ChannelType.text], row=1)
    async def s_hw(self, i, s): update_config(i.guild.id, "market_hw_channel_id", s.values[0].id); await i.response.send_message("✅", ephemeral=True)

    # ROW 2 (Buttons)
    @discord.ui.button(label="📈 Создать Статы (Сверху)", style=discord.ButtonStyle.blurple, row=2)
    async def btn_stats(self, i, b):
        overwrites = {i.guild.default_role: discord.PermissionOverwrite(connect=False, view_channel=True)}
        cat = await i.guild.create_category("📊 СТАТИСТИКА", overwrites=overwrites, position=0)
        await i.guild.create_voice_channel(f"💎 {SERVER_NAME}", category=cat)
        await i.guild.create_voice_channel("👥 Загрузка...", category=cat)
        await i.guild.create_voice_channel("🧡 FT: Загрузка...", category=cat)
        await i.guild.create_voice_channel("💙 HW: Загрузка...", category=cat)
        update_config(i.guild.id, "stats_category_id", cat.id)
        await i.response.send_message("✅ Статистика создана вверху!", ephemeral=True)

    @discord.ui.button(label="🎉 Создать Конкурс", style=discord.ButtonStyle.gray, row=2)
    async def btn_give(self, i, b):
        await i.response.send_modal(ContestCreateModal())

    @discord.ui.button(label="🛒 Создать Магазин", style=discord.ButtonStyle.success, row=2)
    async def btn_shop(self, i, b):
        ch = await i.guild.create_text_channel("shop")
        await ch.send(embed=discord.Embed(title="🛒 Магазин Услуг", description="Выберите категорию ниже:", color=discord.Color.dark_theme()), view=ShopCategorySelect())
        await i.response.send_message(f"✅ Магазин создан: {ch.mention}", ephemeral=True)

    # ROW 3
    @discord.ui.button(label="🛑 Платежи ВКЛ/ВЫКЛ", style=discord.ButtonStyle.danger, row=3)
    async def btn_pay_toggle(self, i, b):
        c = get_config(i.guild.id)
        new_val = 0 if c and c[16] == 1 else 1
        update_config(i.guild.id, "payments_enabled", new_val)
        status = "ВКЛЮЧЕНЫ" if new_val == 1 else "ВЫКЛЮЧЕНЫ"
        await i.response.send_message(f"💳 Платежи теперь **{status}**", ephemeral=True)
    
    @discord.ui.button(label="🛠 Верификация", style=discord.ButtonStyle.green, row=3)
    async def btn_ver(self, i, b): 
        r=await i.guild.create_role(name="Verified", color=discord.Color.green()); update_config(i.guild.id, "verify_role_id", r.id)
        ow={i.guild.default_role:discord.PermissionOverwrite(read_messages=True, send_messages=False), r:discord.PermissionOverwrite(read_messages=False), i.guild.me:discord.PermissionOverwrite(read_messages=True)}
        ch=await i.guild.create_text_channel("verify", overwrites=ow); await ch.send(embed=discord.Embed(title="Верификация"), view=VerifyView()); await i.response.send_message("✅", ephemeral=True)

# --- ПРОСТЫЕ VIEWS ---
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

# --- СИСТЕМА ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()
    update_stats_loop.start()
    bot.add_view(VerifyView()); bot.add_view(TicketStartView()); bot.add_view(TicketControlView()); bot.add_view(AdminSelect()); bot.add_view(ShopCategorySelect())

@bot.event
async def on_guild_join(guild):
    try:
        ow = {guild.default_role: discord.PermissionOverwrite(read_messages=False), guild.me: discord.PermissionOverwrite(read_messages=True)}
        cat = await guild.create_category("BOT SETTINGS", overwrites=ow)
        ch = await guild.create_text_channel("admin-panel", category=cat)
        await ch.send(embed=discord.Embed(title="⚙️ Админ Панель"), view=AdminSelect())
    except: pass

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

# --- ОСТАЛЬНОЕ (Музыка, Слеш) ---
@bot.tree.command(name="play", description="Музыка")
async def slash_play(i: discord.Interaction, query: str):
    await i.response.defer(); 
    if not i.user.voice: return await i.followup.send("Войс!")
    if not i.guild.voice_client: await i.user.voice.channel.connect()
    try: p=await YTDLSource.from_url(query, loop=bot.loop, stream=True); i.guild.voice_client.play(p); await i.followup.send(f"🎶 {p.title}")
    except: await i.followup.send("Ошибка")

@bot.tree.command(name="top", description="Топ чарт")
async def slash_top(i: discord.Interaction):
    await i.response.defer()
    if not i.user.voice: return await i.followup.send("Войс!")
    if not i.guild.voice_client: await i.user.voice.channel.connect()
    try: p=await YTDLSource.from_url("Топ 100 русских хитов 2024 микс", loop=bot.loop, stream=True); i.guild.voice_client.play(p); await i.followup.send(f"🔥 {p.title}")
    except: await i.followup.send("Ошибка")

# --- СОБЫТИЯ КАРТИНОК ---
@bot.event
async def on_member_join(member):
    c=get_config(member.guild.id)
    if c and c[9]: 
        ch=member.guild.get_channel(c[9])
        if ch: await ch.send(f"Привет {member.mention}", file=await create_banner(member, "WELCOME", "welcome_bg.png"))

@bot.event
async def on_member_remove(member):
    c=get_config(member.guild.id)
    if c and c[10]: 
        ch=member.guild.get_channel(c[10])
        if ch: await ch.send(f"Пока...", file=await create_banner(member, "GOODBYE", "goodbye_bg.png"))

bot.run(TOKEN)
