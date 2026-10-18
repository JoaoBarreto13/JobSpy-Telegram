# 🤖 JobSpy Telegram Bot

<p align="center">
  <b>Bot do Telegram para busca e monitoramento automático de vagas de emprego</b><br>
  Integração direta com o agregador <b>JobSpy</b> — busca no LinkedIn, Indeed, Glassdoor, ZipRecruiter e mais.
</p>

---

## ✨ Funcionalidades

- 💬 **Funciona em DMs e Grupos:** Use em conversas privadas ou adicione ao grupo da sua comunidade.
- ⚡ **Busca Rápida (`/buscar`):** Pesquise vagas em segundos com apenas um comando.
- 🔍 **Busca Avançada Interativa (`/avancada`):** Menu passo a passo com botões interativos para filtrar:
  - Portais de vagas específicos
  - Localização
  - Regime de trabalho (Remoto / Presencial)
  - Tipo de vaga (Integral, Estágio, Contrato, etc.)
  - País (para Indeed / Glassdoor)
  - Quantidade de resultados
- 🔔 **Alertas Automáticos (`/alerta`):** Monitoramento periódico em segundo plano. O bot busca vagas no intervalo definido e notifica apenas sobre **novas vagas** encontradas (anti-duplicação).
- 💾 **Persistência de Alertas:** Seus alertas ficam salvos e são retomados mesmo se o bot for reiniciado.

---

## 🌐 Portais Suportados

| Portal | Ícone | Cobertura / Observação |
|---|---|---|
| **LinkedIn** | 🔗 | Busca global. Rate limit agressivo (evite requisições excessivas). |
| **Indeed** | 📋 | Excelente estabilidade e suporte a dezenas de países. |
| **Glassdoor** | 🪟 | Suporte internacional e avaliações. |
| **ZipRecruiter** | ⚡ | Focado em EUA e Canadá. |
| **Bayt** | 🌍 | Focado no Oriente Médio e Norte da África. |
| **Naukri** | 🇮🇳 | Vagas na Índia. |
| **BDJobs** | 🇧🇩 | Vagas em Bangladesh. |
| **HelloWork** | 🇫🇷 | Vagas na França. |

---

## 🚀 Instalação e Configuração

### 1. Pré-requisitos
- **Python 3.10+** instalado.

### 2. Instalar as Dependências

```bash
pip install -U python-jobspy "python-telegram-bot[job-queue]" python-dotenv
```

*(Se estiver rodando a partir do código fonte deste repositório, garanta que as dependências do `pyproject.toml` também estejam satisfeitas).*

---

### 3. Criar o Bot no Telegram

1. Inicie uma conversa com o [@BotFather](https://t.me/BotFather) no Telegram.
2. Envie o comando `/newbot`.
3. Escolha o nome e o username do seu bot (ex: `meu_jobspy_bot`).
4. Guarde o **Token de Acesso** gerado (ex: `123456789:ABCdefGHI...`).

> [!TIP]
> **Para usar em Grupos:**  
> No [@BotFather](https://t.me/BotFather), envie `/setprivacy` → selecione seu bot → escolha **Disable**. Isso permite que o bot leia mensagens e comandos dentro de grupos.

---

### 4. Configurar Variáveis de Ambiente

Crie ou edite o arquivo `.env` na raiz do projeto (use o `.env.example` como base):

```env
# Token gerado pelo @BotFather (obrigatório)
TELEGRAM_BOT_TOKEN=SEU_TOKEN_AQUI

# IDs de usuários permitidos (opcional, separados por vírgula).
# Deixe em branco para permitir que qualquer pessoa/grupo use o bot.
AUTHORIZED_USERS=

# Intervalo mínimo padrão para alertas em minutos (padrão recomendado: 20 a 30)
ALERT_INTERVAL_MINUTES=20

# Limite máximo de resultados por busca
MAX_RESULTS=15
```

---

### 5. Iniciar o Bot

```bash
python bot.py
```

---

## 📋 Comandos Disponíveis

| Comando | Descrição |
|---|---|
| `/start` | Mensagem de boas-vindas e introdução ao bot |
| `/ajuda` | Manual com todos os comandos e sintaxes |
| `/buscar <termo> [local]` | Busca rápida de vagas |
| `/avancada` | Inicia o assistente interativo de busca com filtros |
| `/alerta` | Configura um alerta periódico para novas vagas |
| `/meusalertas` | Lista todos os seus alertas ativos no chat atual |
| `/pararalerta` | Menu para cancelar/remover um alerta |
| `/sites` | Exibe os portais de busca disponíveis e status |
| `/cancelar` | Cancela qualquer operação interativa em andamento |

---

## 💡 Exemplos de Uso

### Busca Rápida:
```plaintext
/buscar desenvolvedor python São Paulo
/buscar "data scientist" remoto
/buscar frontend react
```

### Dicas de Sintaxe para Melhores Resultados:
- **Termo exato:** Use aspas duplas: `/"software engineer"/`
- **Excluir palavras:** Use o sinal `-`: `python -junior`
- **Combinações:** `fullstack (node OR python) remoto`

---

## 📁 Estrutura do Projeto

```plaintext
JobSpy-Telegram/
├── bot.py             # Código principal do bot Telegram
├── config.py          # Configurações e variáveis de ambiente
├── jobspy/            # Módulo de scraping do JobSpy
├── .env               # Configuração local (Tokens e parâmetros)
├── .env.example       # Modelo de configuração
├── alertas.json       # Armazenamento de alertas e histórico (gerado automaticamente)
└── pyproject.toml     # Dependências e metadados do projeto
```

---

## 📜 Licença

Distribuído sob a licença **MIT**. Consulte `LICENSE` para mais informações.
