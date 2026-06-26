# TTS Bot

Feito por Dunhill.
Discord: Duhill

Bot de Discord que converte texto em voz e fala dentro do canal. Feito em Python, usando a voz do Google Tradutor (gTTS).

## Como funciona

Manda uma mensagem no chat começando com `}` e o bot fala isso no canal de voz onde você está. Cada pessoa tem sua própria configuração de voz, velocidade e volume, salva automaticamente.

Se duas pessoas usarem o bot ao mesmo tempo, as falas entram numa fila e tocam em sequência, sem travar ou cortar a mensagem de ninguém. Quando isso acontece, o bot anuncia o nome de quem está falando antes da mensagem, pra não ficar confuso quem é quem.

## Instalação

1. Instala as dependências:
```
pip install -r requirements.txt
```

2. Cria um arquivo `.env` na pasta do projeto com o token do bot:
```
DISCORD_TOKEN=seu_token_aqui
```

3. Roda o bot:
```
iniciar_bot.bat
```

Não precisa instalar ffmpeg separado, já vem embutido por uma das dependências.

## Comandos no Discord

Por padrão os comandos do bot são em inglês. Dá pra trocar pra português com `}language pt` (ou `}idioma pt`, funciona dos dois jeitos). É uma configuração global, troca pra todo mundo no servidor de uma vez, não é por usuário.

**Em inglês (padrão):**
- `}<text>` — fala o texto no canal de voz
- `}voice <language> [tld]` — muda idioma e sotaque, ex: `}voice en com` pra inglês
- `}speed <value>` — velocidade da fala, de 0.5 a 2.0
- `}volume <value>` — volume da fala, de 0.1 a 2.0
- `}name on` / `}name off` — liga ou desliga o anúncio do seu nome quando tem mais gente usando o bot ao mesmo tempo
- `}config` — mostra sua configuração atual
- `}resetconfig` — volta tudo pro padrão
- `}language en` / `}language pt` — muda o idioma dos comandos do bot (global)
- `}help` — mostra essa lista dentro do Discord

**Em português** (depois de `}language pt`):
- `}<texto>`, `}voz <idioma> [tld]`, `}velocidade <valor>`, `}volume <valor>`, `}nome on/off`, `}config`, `}resetconfig`, `}idioma en/pt`, `}ajuda`

Tem um cooldown de 3.5 segundos por pessoa entre uma fala e outra, pra evitar spam.

## Comandos no terminal

Enquanto o bot está rodando, dá pra digitar comandos direto no terminal onde ele está aberto:

- `ajuda` — lista os comandos
- `cls` — limpa a tela
- `status` — mostra uptime e quantos canais de voz estão conectados
- `fila` — mostra quantos áudios estão esperando em cada servidor
- `limpar` — apaga os áudios temporários que sobraram na pasta
- `desconectar` — desconecta o bot de todos os canais de voz
- `logs` — mostra as últimas 10 linhas do log
- `sair` — encerra o bot

## Subir o bot sozinho se ele cair

O arquivo `iniciar_bot.bat` reinicia o bot automaticamente se ele cair por qualquer erro. Em vez de rodar `python bot.py` direto, roda esse `.bat`.

Pra ele subir sozinho depois de uma queda de luz, precisa configurar o Windows pra logar automaticamente e abrir o `.bat` no login (Task Scheduler). Isso fica fora do bot em si, é configuração do sistema.

## Estrutura de arquivos

- `bot.py` — the bot
- `requirements.txt` — Python dependencies
- `.env` — bot token (don't share this file with anyone)
- `configs_usuarios.json` — each user's configuration (created automatically)
- `bot_language.json` — the bot's current command language, en or pt (created automatically)
- `audios/` — temporary generated audio files, deleted right after playing
- `logs/` — bot log, with automatic rotation (max 5MB per file, keeps up to 5 old ones)