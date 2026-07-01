"""
TTS Bot - Discord text-to-speech bot
Made by Dunhill
"""

import os
import json
import time
import asyncio
import logging
import threading
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path

import discord
from discord.ext import commands
from gtts import gTTS
from dotenv import load_dotenv
import imageio_ffmpeg

load_dotenv()

PREFIX = '}'
COOLDOWN_SEGUNDOS = 3.5
FATOR_VELOCIDADE_NOME = 1.3  # the name is spoken faster than the rest of the message

# How long (in seconds) a user is considered "active" for name announcement purposes.
# If more than this time has passed since their last TTS message, their name won't
# be announced when another user speaks — they're considered out of the conversation.
TIMEOUT_INATIVIDADE_NOME = 120.0

# Project base directory (where this bot.py file is located)
BASE_DIR = Path(__file__).parent

# Directory where generated audio files are stored (tts_*.mp3)
AUDIO_DIR = BASE_DIR / "audios"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Logging configuration
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "bot.log"

# Path to the bundled ffmpeg binary (no manual install or PATH needed)
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# File handler with rotation (max 5MB per file, keeps up to 5 old files)
file_handler = RotatingFileHandler(
    LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
file_handler.setLevel(logging.DEBUG)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Log message format
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S"
)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)

# discord.py has its own internal logger, which by default uses a different
# format and prints routine connection details straight to the console. We
# route it through the same file/format as our own log, but keep the console
# clean by only showing warnings or worse from it.
discord_logger = logging.getLogger("discord")
discord_logger.setLevel(logging.INFO)
discord_logger.addHandler(file_handler)

discord_console_handler = logging.StreamHandler()
discord_console_handler.setLevel(logging.WARNING)
discord_console_handler.setFormatter(formatter)
discord_logger.addHandler(discord_console_handler)

# Default voice (Google Translate, female, pt-BR), default speed, volume and name announcement
PADRAO = {
    "idioma": "pt",
    "tld": "com.br",
    "velocidade": 1.0,
    "volume": 1.0,
    "anunciar_nome": True,
}

# File where each user's configuration is saved
CONFIG_FILE = BASE_DIR / "configs_usuarios.json"

# File where the global bot command language is saved (not per-user)
IDIOMA_BOT_FILE = BASE_DIR / "bot_language.json"

# Embed accent color
COR_EMBED = discord.Color(0x5865F2)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# Marks when the process started, to calculate uptime for the terminal "status" command
inicio_processo = time.monotonic()

# Ensures the terminal thread is only created once, even if the bot reconnects
_terminal_iniciado = False

# Per-user cooldown tracking: {user_id: timestamp of last use}
ultimo_uso: dict[int, float] = {}

# Pending audio queue per server: {guild_id: deque[(file, ffmpeg_options)]}
filas_audio: dict[int, deque] = {}

# Tracks when each user last sent a TTS message per server: {guild_id: {user_id: monotonic_timestamp}}
# Used to decide whether to announce the speaker's name — if another user spoke
# within TIMEOUT_INATIVIDADE_NOME seconds, they count as "active" in the conversation.
ultimo_tts: dict[int, dict[int, float]] = {}

# Per-server lock to prevent simultaneous voice connections/moves
locks_conexao: dict[int, asyncio.Lock] = {}

# Bilingual bot commands
# The bot's Discord-facing command words and reply texts can be in English or
# Portuguese. This is a GLOBAL setting (affects every user/server at once),
# not a per-user preference. Default is English.

COMANDOS = {
    "en": {
        "help":        "help",
        "voice":       "voice",
        "speed":       "speed",
        "volume":      "volume",
        "name":        "name",
        "config":      "config",
        "resetconfig": "resetconfig",
    },
    "pt": {
        "help":        "ajuda",
        "voice":       "voz",
        "speed":       "velocidade",
        "volume":      "volume",
        "name":        "nome",
        "config":      "config",
        "resetconfig": "resetconfig",
    },
}

TEXTOS = {
    "en": {
        "voice_updated":   "Voice updated: language=`{idioma}`, tld=`{tld}`",
        "speed_usage":     "Use: `{p}speed 1.5` (values between 0.5 and 2.0)",
        "speed_invalid":   "That's not a valid number. Ex: `{p}speed 1.5`",
        "speed_updated":   "Speed updated to `{valor}x`",
        "speed_adjusted":  "Speed updated to `{valor}x` (adjusted from `{pedido}` to stay between 0.5 and 2.0)",
        "volume_usage":    "Use: `{p}volume 1.5` (values between 0.1 and 2.0)",
        "volume_invalid":  "That's not a valid number. Ex: `{p}volume 1.5`",
        "volume_updated":  "Volume updated to `{valor}x`",
        "volume_adjusted": "Volume updated to `{valor}x` (adjusted from `{pedido}` to stay between 0.1 and 2.0)",
        "name_usage":      "Use: `{p}name on` or `{p}name off`",
        "name_updated":    "Name announcement {estado}.",
        "resetconfig_done":"Configuration reset to default.",
        "cooldown":        "Hold on, wait {restante:.1f}s more before using it again.",
        "join_voice":      "Join a voice channel first.",
        "generic_error":   "Something went wrong generating the audio. Details were saved in the log.",
        "language_usage":  "Use: `{p}language en` or `{p}language pt`",
        "language_changed":"Bot command language changed to English.",
    },
    "pt": {
        "voice_updated":   "Voz atualizada: idioma=`{idioma}`, tld=`{tld}`",
        "speed_usage":     "Use: `{p}velocidade 1.5` (valores entre 0.5 e 2.0)",
        "speed_invalid":   "Isso não é um número válido. Ex: `{p}velocidade 1.5`",
        "speed_updated":   "Velocidade atualizada para `{valor}x`",
        "speed_adjusted":  "Velocidade atualizada para `{valor}x` (ajustei de `{pedido}` pra ficar entre 0.5 e 2.0)",
        "volume_usage":    "Use: `{p}volume 1.5` (valores entre 0.1 e 2.0)",
        "volume_invalid":  "Isso não é um número válido. Ex: `{p}volume 1.5`",
        "volume_updated":  "Volume atualizado para `{valor}x`",
        "volume_adjusted": "Volume atualizado para `{valor}x` (ajustei de `{pedido}` pra ficar entre 0.1 e 2.0)",
        "name_usage":      "Use: `{p}nome on` ou `{p}nome off`",
        "name_updated":    "Anúncio do nome {estado}.",
        "resetconfig_done":"Configuração resetada para o padrão.",
        "cooldown":        "Calma aí, espera mais {restante:.1f}s pra usar de novo.",
        "join_voice":      "Entre em um canal de voz.",
        "generic_error":   "Deu erro ao gerar o áudio. Detalhes ficaram salvos no log.",
        "language_usage":  "Use: `{p}idioma en` ou `{p}idioma pt`",
        "language_changed":"Idioma dos comandos do bot alterado para português.",
    },
}


def carregar_idioma_bot() -> str:
    if IDIOMA_BOT_FILE.exists():
        try:
            with open(IDIOMA_BOT_FILE, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if dados.get("idioma") in ("en", "pt"):
                    return dados["idioma"]
        except json.JSONDecodeError:
            logger.info("bot_language.json is empty or invalid, using default language.")
        except Exception as err:
            logger.error(f"Error loading bot language: {err}", exc_info=True)
    return "en"


def salvar_idioma_bot() -> None:
    try:
        with open(IDIOMA_BOT_FILE, "w", encoding="utf-8") as f:
            json.dump({"idioma": idioma_bot}, f, ensure_ascii=False, indent=2)
    except Exception as err:
        logger.error(f"Error saving bot language: {err}", exc_info=True)


# Global UI language for Discord-facing bot commands and replies
idioma_bot: str = carregar_idioma_bot()


def t(chave: str, **kwargs) -> str:
    """Looks up a Discord-facing string in the currently active bot language."""
    return TEXTOS[idioma_bot][chave].format(p=PREFIX, **kwargs)


def estado_str(ativo: bool) -> str:
    if idioma_bot == "en":
        return "enabled" if ativo else "disabled"
    return "ativado" if ativo else "desativado"


def criar_embed_ajuda() -> discord.Embed:
    p = PREFIX
    if idioma_bot == "en":
        embed = discord.Embed(title="TTS Bot - Commands", color=COR_EMBED)
        embed.add_field(name="TTS",      value=f"`{p}<text>` - speaks the text in the voice channel", inline=False)
        embed.add_field(name="Voice",    value=f"`{p}voice <language> [tld]` - changes language/accent\nex: `{p}voice en com` for English, `{p}voice pt com.br` for Brazilian Portuguese", inline=False)
        embed.add_field(name="Speed",    value=f"`{p}speed <value>` - speech speed from 0.5 to 2.0", inline=False)
        embed.add_field(name="Volume",   value=f"`{p}volume <value>` - speech volume from 0.1 to 2.0", inline=False)
        embed.add_field(name="Name",     value=f"`{p}name on` / `{p}name off` - toggles name announcement when others are active", inline=False)
        embed.add_field(name="Config",   value=f"`{p}config` - shows your settings\n`{p}resetconfig` - resets everything to default", inline=False)
        embed.add_field(name="Language", value=f"`{p}language en` / `{p}language pt` - changes bot command language (global, affects everyone)", inline=False)
    else:
        embed = discord.Embed(title="TTS Bot - Comandos", color=COR_EMBED)
        embed.add_field(name="TTS",      value=f"`{p}<texto>` - fala o texto no canal de voz", inline=False)
        embed.add_field(name="Voz",      value=f"`{p}voz <idioma> [tld]` - muda idioma/sotaque\nex: `{p}voz en com` pra inglês, `{p}voz pt com.br` pra português", inline=False)
        embed.add_field(name="Velocidade",value=f"`{p}velocidade <valor>` - velocidade da fala de 0.5 a 2.0", inline=False)
        embed.add_field(name="Volume",   value=f"`{p}volume <valor>` - volume da fala de 0.1 a 2.0", inline=False)
        embed.add_field(name="Nome",     value=f"`{p}nome on` / `{p}nome off` - liga/desliga anúncio do nome quando outros estão ativos", inline=False)
        embed.add_field(name="Config",   value=f"`{p}config` - mostra sua configuração\n`{p}resetconfig` - volta tudo ao padrão", inline=False)
        embed.add_field(name="Idioma",   value=f"`{p}idioma en` / `{p}idioma pt` - muda o idioma dos comandos do bot (global, afeta todo mundo)", inline=False)
    embed.set_footer(text="TTS Bot by Dunhill")
    return embed


def criar_embed_config(cfg: dict, user: discord.Member) -> discord.Embed:
    if idioma_bot == "en":
        embed = discord.Embed(title="Your configuration", color=COR_EMBED)
        embed.add_field(name="Language",          value=f"`{cfg['idioma']}`",                             inline=True)
        embed.add_field(name="TLD",               value=f"`{cfg['tld']}`",                                inline=True)
        embed.add_field(name="Speed",             value=f"`{cfg['velocidade']}x`",                        inline=True)
        embed.add_field(name="Volume",            value=f"`{cfg['volume']}x`",                            inline=True)
        embed.add_field(name="Name announcement", value=f"`{estado_str(cfg['anunciar_nome'])}`",           inline=True)
    else:
        embed = discord.Embed(title="Sua configuração", color=COR_EMBED)
        embed.add_field(name="Idioma",            value=f"`{cfg['idioma']}`",                             inline=True)
        embed.add_field(name="TLD",               value=f"`{cfg['tld']}`",                                inline=True)
        embed.add_field(name="Velocidade",        value=f"`{cfg['velocidade']}x`",                        inline=True)
        embed.add_field(name="Volume",            value=f"`{cfg['volume']}x`",                            inline=True)
        embed.add_field(name="Anúncio do nome",   value=f"`{estado_str(cfg['anunciar_nome'])}`",           inline=True)
    embed.set_footer(text=f"{user.display_name}  |  TTS Bot by Dunhill")
    return embed


def carregar_configs() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.info("configs_usuarios.json is empty or invalid, starting with no saved configs.")
        except Exception as err:
            logger.error(f"Error loading user configs: {err}", exc_info=True)
    return {}


def salvar_configs() -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(configs_usuarios, f, ensure_ascii=False, indent=2)
    except Exception as err:
        logger.error(f"Error saving user configs: {err}", exc_info=True)


# Configurations loaded into memory, by user_id (string)
configs_usuarios: dict = carregar_configs()


def obter_config(user_id: int) -> dict:
    cfg = configs_usuarios.get(str(user_id), {})
    return {**PADRAO, **cfg}


def _opcoes_ffmpeg(velocidade: float, volume: float):
    filtros = []
    if velocidade != 1.0:
        filtros.append(f"atempo={velocidade}")
    if volume != 1.0:
        filtros.append(f"volume={volume}")
    if not filtros:
        return None
    return f"-filter:a {','.join(filtros)}"


def _gerar_audio_sync(texto: str, arquivo: Path, idioma: str, tld: str) -> None:
    try:
        tts = gTTS(text=texto, lang=idioma, tld=tld)
        tts.save(str(arquivo))
    except Exception as err:
        logger.error(f"Error in _gerar_audio_sync: {err}", exc_info=True)
        raise


async def gerar_audio(texto: str, idioma: str, tld: str) -> Path:
    arquivo = AUDIO_DIR / f"tts_{int(time.time() * 1000)}.mp3"
    try:
        logger.info(f"Starting audio generation via gTTS (language={idioma}, tld={tld})")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _gerar_audio_sync, texto, arquivo, idioma, tld)
        logger.info(f"Audio saved successfully: {arquivo}")
        return arquivo
    except Exception as err:
        logger.error(f"Error generating audio: {err}", exc_info=True)
        raise


def limpar_audios_antigos() -> int:
    """Deletes leftover audio files in the folder. Runs on shutdown as a safety
    net in case some file wasn't deleted after playing. Also callable from the
    terminal via the 'limpar' command."""
    apagados = 0
    for arquivo in AUDIO_DIR.glob("tts_*.mp3"):
        try:
            arquivo.unlink()
            apagados += 1
        except Exception as err:
            logger.error(f"Error deleting {arquivo}: {err}")
    logger.info(f"Cleanup complete: {apagados} audio file(s) deleted.")
    return apagados


async def obter_conexao(guild: discord.Guild, canal: discord.VoiceChannel) -> discord.VoiceClient:
    """Connects (or moves) the bot to the voice channel, protected by a lock to
    prevent two simultaneous requests from trying to connect at the same time."""
    lock = locks_conexao.setdefault(guild.id, asyncio.Lock())
    async with lock:
        connection = guild.voice_client
        if connection is None:
            connection = await canal.connect()
            logger.info(f"Bot connected to voice channel: {canal.name}")
        elif connection.channel.id != canal.id:
            await connection.move_to(canal)
            logger.info(f"Bot moved to channel: {canal.name}")
        return connection


def tocar_proximo_da_fila(guild_id: int, connection: discord.VoiceClient) -> None:
    """Plays the next audio in this server's queue, if there's anything waiting."""
    fila = filas_audio.get(guild_id)
    if not fila:
        return

    arquivo, opcoes_ffmpeg = fila.popleft()
    fonte = discord.FFmpegOpusAudio(str(arquivo), executable=FFMPEG_EXE, options=opcoes_ffmpeg)

    def apos_tocar(err):
        if err:
            logger.error(f"Error playing audio on Discord: {err}")
        try:
            arquivo.unlink(missing_ok=True)
            logger.info(f"Audio deleted after playback: {arquivo}")
        except Exception as e:
            logger.error(f"Error deleting audio after playback: {e}")
        tocar_proximo_da_fila(guild_id, connection)

    logger.info(f"Playing queued audio in server {guild_id}")
    connection.play(fonte, after=apos_tocar)


# ---------------------------------------------------------------------------
# Admin terminal: runs on a separate thread reading what you type into the
# console, in parallel with the bot. Kept in Portuguese on purpose — this is
# Dun's own admin tool, separate from the Discord-facing commands.
# ---------------------------------------------------------------------------

AJUDA_TERMINAL = (
    "Comandos do terminal:\n"
    "  ajuda        - mostra essa lista\n"
    "  cls          - limpa a tela do terminal\n"
    "  status       - uptime e quantos canais de voz estão conectados\n"
    "  fila         - mostra quantos áudios estão esperando em cada servidor\n"
    "  limpar       - apaga os áudios temporários que sobraram na pasta\n"
    "  desconectar  - desconecta o bot de todos os canais de voz\n"
    "  logs         - mostra as últimas 10 linhas do bot.log\n"
    "  sair         - encerra o bot"
)


def _tail_log(n: int = 10) -> str:
    try:
        linhas = LOG_FILE.read_text(encoding="utf-8").splitlines()
        return "\n".join(linhas[-n:]) if linhas else "(log vazio)"
    except Exception as err:
        return f"Erro ao ler o log: {err}"


def _formatar_uptime(segundos: float) -> str:
    horas, resto = divmod(int(segundos), 3600)
    minutos, seg = divmod(resto, 60)
    return f"{horas}h {minutos}m {seg}s"


async def _desconectar_todos_canais() -> int:
    canais = list(bot.voice_clients)
    for vc in canais:
        await vc.disconnect(force=True)
    return len(canais)


def _rodar_no_loop(coro, timeout: float = 10.0):
    """Runs a coroutine on the bot's event loop from the terminal thread."""
    future = asyncio.run_coroutine_threadsafe(coro, bot.loop)
    return future.result(timeout=timeout)


def imprimir_banner() -> None:
    largura = 44
    print("=" * largura)
    print(" TTS Bot - by Dunhill")
    print(f" Connected as: {bot.user}")
    print("=" * largura)


def thread_terminal() -> None:
    print(AJUDA_TERMINAL)
    while True:
        try:
            entrada = input("> ").strip().lower()
        except EOFError:
            break

        if not entrada:
            continue

        if entrada in ("ajuda", "help"):
            print(AJUDA_TERMINAL)

        elif entrada in ("cls", "clear"):
            os.system("cls" if os.name == "nt" else "clear")

        elif entrada == "status":
            uptime = _formatar_uptime(time.monotonic() - inicio_processo)
            print(f"Bot: {bot.user}\nUptime: {uptime}\nCanais de voz conectados: {len(bot.voice_clients)}")

        elif entrada == "fila":
            tem_algo = False
            for guild_id, fila in filas_audio.items():
                if fila:
                    tem_algo = True
                    print(f"Servidor {guild_id}: {len(fila)} áudio(s) na fila")
            if not tem_algo:
                print("Nenhuma fila ativa.")

        elif entrada == "limpar":
            apagados = limpar_audios_antigos()
            print(f"{apagados} áudio(s) temporário(s) apagado(s).")

        elif entrada == "desconectar":
            try:
                qtd = _rodar_no_loop(_desconectar_todos_canais())
                print(f"Bot desconectado de {qtd} canal(is) de voz.")
            except Exception as err:
                print(f"Erro ao desconectar: {err}")

        elif entrada == "logs":
            print(_tail_log())

        elif entrada in ("sair", "parar", "exit", "quit"):
            print("Encerrando o bot...")
            try:
                _rodar_no_loop(bot.close())
            except Exception as err:
                print(f"Erro ao encerrar: {err}")
            break

        else:
            print(f"Comando '{entrada}' não reconhecido. Digite 'ajuda' pra ver a lista.")


@bot.event
async def on_ready():
    global _terminal_iniciado
    logger.info(f"{bot.user} is online")

    if not _terminal_iniciado:
        _terminal_iniciado = True
        imprimir_banner()
        threading.Thread(target=thread_terminal, daemon=True).start()


@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
):
    # Only relevant when someone LEAVES a channel (before.channel existed)
    if member.bot or before.channel is None:
        return

    canal_anterior = before.channel
    connection = canal_anterior.guild.voice_client

    if connection is None or connection.channel.id != canal_anterior.id:
        return

    membros_humanos = [m for m in canal_anterior.members if not m.bot]
    if not membros_humanos:
        await connection.disconnect()
        logger.info(f"Bot disconnected from empty channel: {canal_anterior.name}")


@bot.event
async def on_message(message: discord.Message):
    global idioma_bot

    if message.author.bot:
        return
    if not message.guild:
        return
    if not message.content.startswith(PREFIX):
        return

    texto = message.content[len(PREFIX):].strip()
    if not texto:
        return

    partes = texto.split(maxsplit=2)
    comando = partes[0].lower()
    cmds = COMANDOS[idioma_bot]

    # Language switch always works under both spellings, no matter which
    # language is currently active, so nobody gets locked out of switching back.
    if comando in ("language", "idioma"):
        opcao = partes[1].lower() if len(partes) > 1 else None
        if opcao not in ("en", "pt"):
            await message.reply(t("language_usage"))
            return
        idioma_bot = opcao
        salvar_idioma_bot()
        await message.reply(t("language_changed"))
        return

    # --- Configuration commands (not subject to cooldown) ---

    if comando == cmds["help"]:
        await message.reply(embed=criar_embed_ajuda())
        return

    if comando == cmds["voice"]:
        novo_idioma = partes[1] if len(partes) > 1 else PADRAO["idioma"]
        novo_tld    = partes[2] if len(partes) > 2 else "com"
        cfg_atual = configs_usuarios.setdefault(str(message.author.id), {})
        cfg_atual["idioma"] = novo_idioma
        cfg_atual["tld"]    = novo_tld
        salvar_configs()
        await message.reply(t("voice_updated", idioma=novo_idioma, tld=novo_tld))
        return

    if comando == cmds["speed"]:
        if len(partes) < 2:
            await message.reply(t("speed_usage"))
            return
        try:
            valor_pedido = float(partes[1])
        except ValueError:
            await message.reply(t("speed_invalid"))
            return
        valor = max(0.5, min(2.0, valor_pedido))
        cfg_atual = configs_usuarios.setdefault(str(message.author.id), {})
        cfg_atual["velocidade"] = valor
        salvar_configs()
        if valor != valor_pedido:
            await message.reply(t("speed_adjusted", valor=valor, pedido=valor_pedido))
        else:
            await message.reply(t("speed_updated", valor=valor))
        return

    if comando == cmds["volume"]:
        if len(partes) < 2:
            await message.reply(t("volume_usage"))
            return
        try:
            valor_pedido = float(partes[1])
        except ValueError:
            await message.reply(t("volume_invalid"))
            return
        valor = max(0.1, min(2.0, valor_pedido))
        cfg_atual = configs_usuarios.setdefault(str(message.author.id), {})
        cfg_atual["volume"] = valor
        salvar_configs()
        if valor != valor_pedido:
            await message.reply(t("volume_adjusted", valor=valor, pedido=valor_pedido))
        else:
            await message.reply(t("volume_updated", valor=valor))
        return

    if comando == cmds["name"]:
        opcao = partes[1].lower() if len(partes) > 1 else None
        if opcao not in ("on", "off"):
            await message.reply(t("name_usage"))
            return
        cfg_atual = configs_usuarios.setdefault(str(message.author.id), {})
        cfg_atual["anunciar_nome"] = opcao == "on"
        salvar_configs()
        await message.reply(t("name_updated", estado=estado_str(opcao == "on")))
        return

    if comando == cmds["config"]:
        cfg = obter_config(message.author.id)
        await message.reply(embed=criar_embed_config(cfg, message.author))
        return

    if comando == cmds["resetconfig"]:
        configs_usuarios.pop(str(message.author.id), None)
        salvar_configs()
        await message.reply(t("resetconfig_done"))
        return

    # --- From here on it's normal audio generation ---

    # Anti-spam cooldown
    agora = time.monotonic()
    ultima_vez = ultimo_uso.get(message.author.id, 0.0)
    if agora - ultima_vez < COOLDOWN_SEGUNDOS:
        await message.reply(t("cooldown", restante=COOLDOWN_SEGUNDOS - (agora - ultima_vez)))
        return
    ultimo_uso[message.author.id] = agora

    canal = message.author.voice.channel if message.author.voice else None
    if not canal:
        await message.reply(t("join_voice"))
        return

    try:
        logger.info(
            f"Message received - User: {message.author} (ID: {message.author.id}) | "
            f"Server: {message.guild.name} (ID: {message.guild.id}) | "
            f"Channel: #{message.channel.name}"
        )

        # Name announcement decision: check if any OTHER user spoke within the
        # inactivity timeout window. If yes, they're still part of the
        # conversation and the speaker's name should be announced.
        # We check BEFORE updating our own timestamp so two simultaneous
        # messages both see each other correctly.
        tts_por_servidor = ultimo_tts.setdefault(message.guild.id, {})
        agora_mono = time.monotonic()
        ha_outro_usuario_ativo = any(
            uid != message.author.id and (agora_mono - ts) < TIMEOUT_INATIVIDADE_NOME
            for uid, ts in tts_por_servidor.items()
        )
        tts_por_servidor[message.author.id] = agora_mono

        async with message.channel.typing():
            cfg = obter_config(message.author.id)
            itens_para_fila = []

            if ha_outro_usuario_ativo and cfg["anunciar_nome"]:
                velocidade_nome = min(cfg["velocidade"] * FATOR_VELOCIDADE_NOME, 2.0)
                arquivo_nome = await gerar_audio(
                    f"{message.author.display_name}:", cfg["idioma"], cfg["tld"]
                )
                itens_para_fila.append((arquivo_nome, _opcoes_ffmpeg(velocidade_nome, cfg["volume"])))
                logger.info("Another user active within timeout: adding name announcement before speech")

            arquivo_mensagem = await gerar_audio(texto, cfg["idioma"], cfg["tld"])
            itens_para_fila.append((arquivo_mensagem, _opcoes_ffmpeg(cfg["velocidade"], cfg["volume"])))
            logger.info(f"Audio file(s) generated: {[i[0] for i in itens_para_fila]}")

            connection = await obter_conexao(message.guild, canal)

        fila = filas_audio.setdefault(message.guild.id, deque())
        fila.extend(itens_para_fila)

        if not connection.is_playing():
            tocar_proximo_da_fila(message.guild.id, connection)

        await message.add_reaction("🔊")
        logger.info("Audio added to playback queue")

    except Exception as err:
        logger.error(f"Error processing message: {err}", exc_info=True)
        await message.reply(t("generic_error"))


try:
    bot.run(os.getenv("DISCORD_TOKEN"), log_handler=None)
except Exception as err:
    # If the bot crashes for good (not a normal Ctrl+C), the reason gets
    # logged, which helps understand what happened when the .bat restarts it.
    logger.critical(f"Bot terminated by fatal error: {err}", exc_info=True)
    raise
finally:
    # Runs both on a clean shutdown (Ctrl+C / 'sair') and on a crash,
    # making sure temporary audio files don't pile up.
    limpar_audios_antigos()