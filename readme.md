# TTS Bot

Criado por Dunhill.
Discord: Duhill

Um bot de Discord que converte texto em fala e reproduz a mensagem no canal de voz. O projeto foi desenvolvido em Python e usa o serviço de voz do Google Translate via gTTS.

## Como funciona

Envie uma mensagem no chat começando com `}` e o bot irá falar essa mensagem no canal de voz em que você estiver. Cada usuário pode ter sua própria configuração de voz, velocidade e volume, salva automaticamente.

Se mais de uma pessoa usar o bot ao mesmo tempo, as solicitações entram em uma fila e são reproduzidas em ordem, sem interromper a fala de ninguém. Nesse caso, o bot anuncia o nome do usuário antes da mensagem para facilitar a identificação.

## Requisitos

- Python 3.8 ou superior
- Um token de bot do Discord
- Conexão com a internet

## Instalação

1. Abra a pasta do projeto.
2. Instale as dependências:

```bash
pip install -r requirements.txt
```

3. Crie um arquivo `.env` na raiz do projeto com o seguinte conteúdo:

```env
DISCORD_TOKEN=seu_token_aqui
```

4. Inicie o bot com:

```bash
iniciar_bot.bat
```

> Você não precisa instalar o ffmpeg separadamente, pois isso já é tratado por uma das dependências.

## Como usar

No Discord, envie uma mensagem começando com `}` para fazer o bot falar. Exemplo:

```text
}Olá, mundo!
```

## Comandos no Discord

Por padrão, os comandos aparecem em inglês. Você pode trocar para português com:

```text
}language pt
```

ou

```text
}idioma pt
```

### Comandos em inglês (padrão)

- `}<text>` — fala o texto no canal de voz
- `}voice <language> [tld]` — altera o idioma e o sotaque, por exemplo: `}voice en com`
- `}speed <value>` — altera a velocidade da fala, de 0.5 a 2.0
- `}volume <value>` — altera o volume, de 0.1 a 2.0
- `}name on` / `}name off` — ativa ou desativa o anúncio do seu nome quando outra pessoa estiver usando o bot
- `}config` — mostra sua configuração atual
- `}resetconfig` — restaura os valores padrão
- `}language en` / `}language pt` — troca o idioma dos comandos do bot de forma global
- `}help` — mostra a lista de comandos no Discord

### Comandos em português

Depois de usar `}language pt`, os comandos passam a ser:

- `}<texto>`
- `}voz <idioma> [tld]`
- `}velocidade <valor>`
- `}volume <valor>`
- `}nome on/off`
- `}config`
- `}resetconfig`
- `}idioma en/pt`
- `}ajuda`

Existe também um cooldown de 3,5 segundos por usuário entre uma mensagem e a próxima para evitar spam.

## Comandos no terminal

Enquanto o bot estiver rodando, você pode usar os seguintes comandos diretamente no terminal:

- `ajuda` — lista os comandos disponíveis
- `cls` — limpa a tela
- `status` — mostra o tempo de atividade e quantos canais de voz estão conectados
- `fila` — mostra quantas mensagens estão aguardando em cada servidor
- `limpar` — remove arquivos temporários de áudio que ficaram na pasta
- `desconectar` — desconecta o bot de todos os canais de voz
- `logs` — mostra as últimas 10 linhas do log
- `sair` — encerra o bot

## Reinicialização automática

O arquivo `iniciar_bot.bat` reinicia o bot automaticamente caso ele pare inesperadamente. Para que ele suba sozinho após reinicialização do sistema ou queda de energia, você pode configurar o Windows para abrir esse arquivo no login, por exemplo com o Agendador de Tarefas.

## Estrutura de arquivos

- `bot.py` — arquivo principal do bot
- `requirements.txt` — dependências do projeto
- `.env` — token do bot, que deve ser mantido em segredo
- `configs_usuarios.json` — configurações de cada usuário, criadas automaticamente
- `bot_language.json` — idioma atual dos comandos, criado automaticamente
- `audios/` — arquivos temporários de áudio gerados pelo bot
- `logs/` — arquivos de log com rotação automática