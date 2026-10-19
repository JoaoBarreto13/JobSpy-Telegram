"""
Configurações do bot do Telegram para JobSpy.
Carrega variáveis de ambiente do arquivo .env
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Carrega .env do mesmo diretório
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

# Token do bot (obrigatório)
BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

# IDs de usuários autorizados (vazio = qualquer um pode usar)
_raw_users = os.getenv("AUTHORIZED_USERS", "")
AUTHORIZED_USERS: set[int] = (
    {int(uid.strip()) for uid in _raw_users.split(",") if uid.strip()}
    if _raw_users
    else set()
)

# Intervalo mínimo entre alertas em minutos
ALERT_INTERVAL_MINUTES: int = int(os.getenv("ALERT_INTERVAL_MINUTES", "30"))

# Máximo de resultados por busca
MAX_RESULTS: int = int(os.getenv("MAX_RESULTS", "15"))

# Sites disponíveis para busca (JobSpy + Portais Brasileiros)
AVAILABLE_SITES = [
    "gupy",
    "infojobs",
    "programathor",
    "trabalha_brasil",
    "linkedin",
    "indeed",
    "glassdoor",
    "zip_recruiter",
]

# Mapeamento de nomes amigáveis para sites
SITE_DISPLAY_NAMES = {
    "gupy": "🟢 Gupy",
    "infojobs": "💼 InfoJobs",
    "programathor": "💻 Programathor",
    "trabalha_brasil": "🇧🇷 Trabalha Brasil",
    "linkedin": "🔗 LinkedIn",
    "indeed": "📋 Indeed",
    "glassdoor": "🪟 Glassdoor",
    "zip_recruiter": "⚡ ZipRecruiter",
    "bayt": "🌍 Bayt",
    "naukri": "🇮🇳 Naukri",
    "bdjobs": "🇧🇩 BDJobs",
    "hellowork": "🇫🇷 HelloWork",
}

# País padrão para busca no Indeed/Glassdoor
DEFAULT_COUNTRY = os.getenv("DEFAULT_COUNTRY", "brazil")

# Tipos de vaga disponíveis
JOB_TYPES = {
    "fulltime": "Tempo integral",
    "parttime": "Meio período",
    "contract": "Contrato",
    "temporary": "Temporário",
    "internship": "Estágio",
    "perdiem": "Por dia",
    "other": "Outro",
    "volunteer": "Voluntário",
}
