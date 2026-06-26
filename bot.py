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

# Pending audio queue per server: {guild_id: deque[(file, ffmpeg_options, author_id, is_final)]}
filas_audio: dict[int, deque] = {}

# How many audios each user has playing/waiting, per server: {guild_id: {user_id: count}}
# This decides whether the name needs to be announced (only when there's MORE than one active user).
contagem_ativos: dict[int, dict[int, int]] = {}

# Per-server lock, just to prevent two simultaneous voice connections/moves
locks_conexao: dict[int, asyncio.Lock] = {}

# --- Bilingual bot commands -------------------------------------------------
# The bot's Discord-facing command words and reply texts can be in English or
# Portuguese. This is a GLOBAL setting (affects every user/server at once),
# not a per-user preference. Default is English.

COMANDOS = {
    "en": {
        "help": "help",
        "voice": "voice",
        "speed": "speed",
        "volume": "volume",
        "name": "name",
        "config": "config",
        "resetconfig": "resetconfig",
    },
    "pt": {
        "help": "ajuda",
        "voice": "voz",
        "speed": "velocidade",
        "volume": "volume",
        "name": "nome",
        "config": "config",
        "resetconfig": "resetconfig",
    },
}

TEXTOS = {
    "en": {
        "help": (
            "**Available commands:**\n"
            "`{p}<text>` - speaks the text in the voice channel\n"
            "`{p}voice <language> [tld]` - changes language/accent (ex: `{p}voice en com`)\n"
            "`{p}speed <value>` - adjusts speech speed (0.5 to 2.0)\n"
            "`{p}volume <value>` - adjusts speech volume (0.1 to 2.0)\n"
            "`{p}name on` / `{p}name off` - turns your name announcement on/off when someone else is active\n"
            "`{p}config` - shows your current configuration\n"
            "`{p}resetconfig` - resets everything to default\n"
            "`{p}language en` / `{p}language pt` - changes the bot's command language (global, affects everyone)\n"
            "`{p}help` - shows this message"
        ),
        "voice_updated": "Voice updated: language=`{idioma}`, tld=`{tld}`",
        "speed_usage": "Use: `{p}speed 1.5` (values between 0.5 and 2.0)",
        "speed_invalid": "That's not a valid number. Ex: `{p}speed 1.5`",
        "speed_updated": "Speed updated to `{valor}x`",
        "speed_adjusted": "Speed updated to `{valor}x` (adjusted from `{pedido}` to stay between 0.5 and 2.0)",
        "volume_usage": "Use: `{p}volume 1.5` (values between 0.1 and 2.0)",
        "volume_invalid": "That's not a valid number. Ex: `{p}volume 1.5`",
        "volume_updated": "Volume updated to `{valor}x`",
        "volume_adjusted": "Volume updated to `{valor}x` (adjusted from `{pedido}` to stay between 0.1 and 2.0)",
        "name_usage": "Use: `{p}name on` or `{p}name off`",
        "name_updated": "Name announcement {estado}.",
        "config_header": (
            "Your current configuration:\n"
            "- language: `{idioma}`\n"
            "- tld: `{tld}`\n"
            "- speed: `{velocidade}x`\n"
            "- volume: `{volume}x`\n"
            "- name announcement: `{estado}`"
        ),
        "resetconfig_done": "Configuration reset to default.",
        "cooldown": "Hold on, wait {restante:.1f}s more before using it again.",
        "join_voice": "Join a voice channel first.",
        "generic_error": "Something went wrong generating the audio. Details were saved in the log.",
        "language_usage": "Use: `{p}language en` or `{p}language pt`",
        "language_changed": "Bot command language changed to English.",
    },
    "pt": {
        "help": (
            "**Comandos disponíveis:**\n"
            "`{p}<texto>` — fala o texto no canal de voz\n"
            "`{p}voz <idioma> [tld]` — muda idioma/sotaque (ex: `{p}voz en com`)\n"
            "`{p}velocidade <valor>` — ajusta a velocidade da fala (0.5 a 2.0)\n"
            "`{p}volume <valor>` — ajusta o volume da fala (0.1 a 2.0)\n"
            "`{p}nome on` / `{p}nome off` — liga/desliga o anúncio do seu nome quando tem mais gente ativa\n"
            "`{p}config` — mostra sua configuração atual\n"
            "`{p}resetconfig` — volta tudo ao padrão\n"
            "`{p}idioma en` / `{p}idioma pt` — muda o idioma dos comandos do bot (global, afeta todo mundo)\n"
            "`{p}ajuda` — mostra essa mensagem"
        ),
        "voice_updated": "Voz atualizada: idioma=`{idioma}`, tld=`{tld}`",
        "speed_usage": "Use: `{p}velocidade 1.5` (valores entre 0.5 e 2.0)",
        "speed_invalid": "Isso não é um número válido. Ex: `{p}velocidade 1.5`",
        "speed_updated": "Velocidade atualizada para `{valor}x`",
        "speed_adjusted": "Velocidade atualizada para `{valor}x` (ajustei de `{pedido}` pra ficar entre 0.5 e 2.0)",
        "volume_usage": "Use: `{p}volume 1.5` (valores entre 0.1 e 2.0)",
        "volume_invalid": "Isso não é um número válido. Ex: `{p}volume 1.5`",
        "volume_updated": "Volume atualizado para `{valor}x`",
        "volume_adjusted": "Volume atualizado para `{valor}x` (ajustei de `{pedido}` pra ficar entre 0.1 e 2.0)",
        "name_usage": "Use: `{p}nome on` ou `{p}nome off`",
        "name_updated": "Anúncio do nome {estado}.",
        "config_header": (
            "Sua configuração atual:\n"
            "- idioma: `{idioma}`\n"
            "- tld: `{tld}`\n"
            "- velocidade: `{velocidade}x`\n"
            "- volume: `{volume}x`\n"
            "- anúncio do nome: `{estado}`"
        ),
        "resetconfig_done": "Configuração resetada para o padrão.",
        "cooldown": "Calma aí, espera mais {restante:.1f}s pra usar de novo.",
        "join_voice": "Entre em um canal de voz.",
        "generic_error": "Deu erro ao gerar o áudio. Detalhes ficaram salvos no log.",
        "language_usage": "Use: `{p}idioma en` ou `{p}idioma pt`",
        "language_changed": "Idioma dos comandos do bot alterado para português.",
    },
}


def carregar_idioma_bot() -> str:
    if IDIOMA_BOT_FILE.exists():
        try:
            with open(IDIOMA_BOT_FILE, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if dados.get("idioma") in ("en", "pt"):
                    return dados["idioma"]
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
    texto = TEXTOS[idioma_bot][chave]
    return texto.format(p=PREFIX, **kwargs)


def estado_str(ativo: bool) -> str:
    if idioma_bot == "en":
        return "enabled" if ativo else "disabled"
    return "ativado" if ativo else "desativado"


def carregar_configs() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
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
        logger.error(f"Error in _gerar_audio_sync function: {err}", exc_info=True)
        raise


async def gerar_audio(texto: str, idioma: str, tld: str) -> Path:
    arquivo = AUDIO_DIR / f"tts_{int(time.time() * 1000)}.mp3"

    try:
        logger.info(f"Starting audio generation via gTTS (language={idioma}, tld={tld})")

        # gTTS is synchronous/blocking, so it runs in a separate thread
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _gerar_audio_sync, texto, arquivo, idioma, tld)

        logger.info(f"Audio saved successfully: {arquivo}")
        return arquivo
    except Exception as err:
        logger.error(f"Error generating audio: {err}", exc_info=True)
        raise


def limpar_audios_antigos() -> int:
    """Deletes leftover audio files in the folder. Runs when the bot shuts down
    (Ctrl+C), as a safety net in case some file wasn't deleted after playing.
    Can also be called manually via the 'limpar' terminal command."""
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

    arquivo, opcoes_ffmpeg, autor_id, eh_final = fila.popleft()
    fonte = discord.FFmpegOpusAudio(str(arquivo), executable=FFMPEG_EXE, options=opcoes_ffmpeg)

    def apos_tocar(err):
        if err:
            logger.error(f"Error playing audio on Discord: {err}")

        try:
            arquivo.unlink(missing_ok=True)
            logger.info(f"Audio deleted after playback: {arquivo}")
        except Exception as e:
            logger.error(f"Error deleting audio after playback: {e}")

        # Only decreases the user's count when their FINAL item for this turn
        # finishes (the name audio, when it exists, doesn't count for this)
        if eh_final:
            contagens = contagem_ativos.get(guild_id, {})
            if autor_id in contagens:
                contagens[autor_id] -= 1
                if contagens[autor_id] <= 0:
                    contagens.pop(autor_id, None)

        # Chains to the next item in the queue, if there is one
        tocar_proximo_da_fila(guild_id, connection)

    logger.info(f"Playing queued audio in server {guild_id}")
    connection.play(fonte, after=apos_tocar)

# Admin terminal: runs on a separate thread reading what you type into the
# console, in parallel with the bot. This is Dun's own admin tool, kept in
# Portuguese on purpose (separate from the Discord-facing bot commands above).

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
        if not linhas:
            return "(log vazio)"
        return "\n".join(linhas[-n:])
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

    # The bot isn't in that channel, nothing to do
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
        await message.reply(t("help"))
        return

    if comando == cmds["voice"]:
        novo_idioma = partes[1] if len(partes) > 1 else PADRAO["idioma"]
        novo_tld = partes[2] if len(partes) > 2 else "com"

        cfg_atual = configs_usuarios.setdefault(str(message.author.id), {})
        cfg_atual["idioma"] = novo_idioma
        cfg_atual["tld"] = novo_tld
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
        await message.reply(
            t(
                "config_header",
                idioma=cfg["idioma"],
                tld=cfg["tld"],
                velocidade=cfg["velocidade"],
                volume=cfg["volume"],
                estado=estado_str(cfg["anunciar_nome"]),
            )
        )
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
    decorrido = agora - ultima_vez
    if decorrido < COOLDOWN_SEGUNDOS:
        restante = COOLDOWN_SEGUNDOS - decorrido
        await message.reply(t("cooldown", restante=restante))
        return
    ultimo_uso[message.author.id] = agora

    canal = message.author.voice.channel if message.author.voice else None

    if not canal:
        await message.reply(t("join_voice"))
        return
    # checks if the user is in a voice channel. If not, sends an error message.
    try:
        logger.info(
            f"Message received - User: {message.author} (ID: {message.author.id}) | "
            f"Server: {message.guild.name} (ID: {message.guild.id}) | "
            f"Channel: #{message.channel.name}"
        )

        # Checks whether another user already has active audio (playing or
        # queued) in this server. If so, this new audio needs a name
        # announcement first to avoid confusion (unless the user disabled it).
        contagens = contagem_ativos.setdefault(message.guild.id, {})
        ha_outro_usuario_ativo = any(
            uid != message.author.id and qtd > 0 for uid, qtd in contagens.items()
        )
        contagens[message.author.id] = contagens.get(message.author.id, 0) + 1

        async with message.channel.typing():
            cfg = obter_config(message.author.id)
            itens_para_fila = []

            if ha_outro_usuario_ativo and cfg["anunciar_nome"]:
                velocidade_nome = min(cfg["velocidade"] * FATOR_VELOCIDADE_NOME, 2.0)
                arquivo_nome = await gerar_audio(
                    f"{message.author.display_name}:", cfg["idioma"], cfg["tld"]
                )
                itens_para_fila.append(
                    (
                        arquivo_nome,
                        _opcoes_ffmpeg(velocidade_nome, cfg["volume"]),
                        message.author.id,
                        False,
                    )
                )
                logger.info("Another user already active: adding name announcement before speech")

            arquivo_mensagem = await gerar_audio(texto, cfg["idioma"], cfg["tld"])
            itens_para_fila.append(
                (
                    arquivo_mensagem,
                    _opcoes_ffmpeg(cfg["velocidade"], cfg["volume"]),
                    message.author.id,
                    True,
                )
            )
            logger.info(f"Audio file(s) generated: {[i[0] for i in itens_para_fila]}")

            connection = await obter_conexao(message.guild, canal)

        # Joins this server's queue. If nothing is playing, it plays right
        # away; otherwise it waits for the current audio to finish and plays
        # next, without blocking or dropping anyone's message.
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
    bot.run(os.getenv("DISCORD_TOKEN"))
except Exception as err:
    # If the bot crashes for good (not a normal Ctrl+C), the reason gets
    # logged, which helps understand what happened when the .bat restarts it.
    logger.critical(f"Bot terminated by fatal error: {err}", exc_info=True)
    raise
finally:
    # Runs both on a clean shutdown (Ctrl+C / 'sair' terminal command) and on
    # a crash, making sure temporary audio files don't pile up.
    limpar_audios_antigos()