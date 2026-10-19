# 🤖 JobSpy Telegram Bot

<p align="center">
  <b>Bot do Telegram para busca e monitoramento automático de vagas de emprego</b><br>
  Integração direta com os maiores <b>Portais Brasileiros</b> (Gupy, InfoJobs, Programathor, Trabalha Brasil) e o agregador <b>JobSpy</b> (LinkedIn, Indeed, Glassdoor, ZipRecruiter).
</p>

---

## ✨ Funcionalidades

- 🇧🇷 **Módulo Nativo para Portais Brasileiros:** Busca em tempo real na Gupy, InfoJobs, Programathor e Trabalha Brasil.
- 🔓 **Sem Necessidade de Chaves de API de Vagas:** Não requer contas pagas nem tokens de API de nenhum dos portais de emprego. Apenas o token gratuito do Telegram Bot é necessário!
- 💬 **Funciona em DMs e Grupos:** Use em conversas privadas ou adicione ao grupo da sua comunidade.
- ⚡ **Busca Rápida (`/buscar`):** Pesquise vagas em segundos em múltiplos portais ao mesmo tempo.
- 🔍 **Busca Avançada Interativa (`/avancada`):** Menu passo a passo com botões interativos para filtrar:
  - Portais de vagas específicos (marque/desmarque individualmente)
  - Localização (cidade, estado ou país)
  - Regime de trabalho (Remoto / Presencial / Híbrido)
  - Tipo de vaga (Integral, Estágio, Contrato PJ, etc.)
  - País (para Indeed / Glassdoor, padrão Brasil)
  - Quantidade de resultados
- 🔔 **Alertas Automáticos (`/alerta`):** Monitoramento periódico em segundo plano. O bot busca vagas no intervalo definido e notifica apenas sobre **novas vagas** encontradas (com anti-duplicação inteligente).
- 💾 **Persistência de Alertas:** Seus alertas ficam salvos e são retomados automaticamente mesmo se o bot for reiniciado.

---

## 🌐 Portais Suportados

> [!NOTE]
> **Todos os portais abaixo funcionam sem chaves de API pagas ou cadastro.** As consultas são feitas de forma direta e transparente.

### 🇧🇷 Portais Brasileiros (Módulo `portais_br`)
| Portal | Ícone | Cobertura / Observação | Requer Chave de API? |
|---|:---:|---|:---:|
| **Gupy** | 🟢 | Maior plataforma corporativa de ATS e vagas do Brasil (`portal.gupy.io`). | ❌ Não |
| **InfoJobs** | 💼 | Um dos maiores e mais populares portais de vagas e currículos no país (`infojobs.com.br`). | ❌ Não |
| **Programathor** | 💻 | Focado em tecnologia, desenvolvimento de software e dados — PJ/CLT (`programathor.com.br`). | ❌ Não |
| **Trabalha Brasil** | 🇧🇷 | Alto volume em todo o Brasil integrado ao BNE / SINE (`trabalhabrasil.com.br`). | ❌ Não |

### 🌐 Portais Globais (com suporte ao Brasil)
| Portal | Ícone | Cobertura / Observação | Requer Chave de API? |
|---|:---:|---|:---:|
| **LinkedIn** | 🔗 | Vagas nacionais e internacionais. | ❌ Não |
| **Indeed** | 📋 | Busca no Indeed Brasil (`country_indeed="brazil"`). | ❌ Não |
| **Glassdoor** | 🪟 | Suporte no Brasil com avaliações e faixas salariais. | ❌ Não |
| **ZipRecruiter** | ⚡ | Focado em vagas internacionais (EUA/Canadá/Remoto). | ❌ Não |

---

## 🚀 Instalação e Configuração

### 1. Pré-requisitos
- **Python 3.10+** instalado.

### 2. Instalar as Dependências

```bash
pip install -U python-jobspy "python-telegram-bot[job-queue]" python-dotenv httpx
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

Copie o arquivo de exemplo `.env.example` para `.env` e insira o seu token do bot:

```bash
cp .env.example .env   # No Windows (PowerShell): copy .env.example .env
```

Abra o arquivo `.env` e defina apenas o seu `TELEGRAM_BOT_TOKEN`:
```env
TELEGRAM_BOT_TOKEN=SEU_TOKEN_AQUI
```
*(As demais configurações como `MAX_RESULTS` e `DEFAULT_COUNTRY` já vêm pré-configuradas com os padrões recomendados).*

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
├── portais_br/        # Módulo extra para portais brasileiros (Gupy, InfoJobs, etc.)
│   ├── gupy.py            # Coletor Gupy (portal.gupy.io)
│   ├── infojobs.py        # Coletor InfoJobs (infojobs.com.br)
│   ├── programathor.py    # Coletor Programathor (programathor.com.br)
│   └── trabalha_brasil.py # Coletor Trabalha Brasil (trabalhabrasil.com.br)
├── jobspy/            # Módulo de scraping JobSpy (LinkedIn, Indeed, etc.)
├── .env               # Configuração local (Tokens e parâmetros)
├── .env.example       # Modelo de configuração
├── alertas.json       # Armazenamento de alertas e histórico (gerado automaticamente)
└── pyproject.toml     # Dependências e metadados do projeto
```

---

## 📜 Licença

Distribuído sob a licença **MIT**. Consulte `LICENSE` para mais informações.
