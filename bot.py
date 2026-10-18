"""
Bot do Telegram para busca de vagas de emprego usando JobSpy.

Funciona tanto em DMs quanto em grupos.
Comandos:
    /start          - Mensagem de boas-vindas
    /ajuda          - Lista de comandos
    /buscar         - Busca rápida de vagas
    /avancada       - Busca avançada com filtros
    /sites          - Listar/selecionar sites de busca
    /alerta         - Configurar alertas automáticos
    /meusalertas    - Ver alertas configurados
    /pararalerta    - Parar um alerta
    /cancelar       - Cancelar operação em andamento
"""

from __future__ import annotations

import html
import json
import logging
import re
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatType, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import (
    ALERT_INTERVAL_MINUTES,
    AUTHORIZED_USERS,
    AVAILABLE_SITES,
    BOT_TOKEN,
    JOB_TYPES,
    MAX_RESULTS,
    SITE_DISPLAY_NAMES,
)

# ---------------------------------------------------------------------------
#  Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Estados da conversa
# ---------------------------------------------------------------------------
(
    BUSCA_TERMO,
    BUSCA_LOCAL,
    BUSCA_SITES,
    BUSCA_TIPO,
    BUSCA_REMOTO,
    BUSCA_PAIS,
    BUSCA_QTD,
    BUSCA_HORAS,
    BUSCA_CONFIRMA,
    ALERTA_TERMO,
    ALERTA_LOCAL,
    ALERTA_SITES,
    ALERTA_INTERVALO,
) = range(13)

# ---------------------------------------------------------------------------
#  Armazenamento de alertas (em memória — persistido em JSON)
# ---------------------------------------------------------------------------
ALERTS_FILE = Path(__file__).resolve().parent / "alertas.json"
# Estrutura: { "chat_id:alert_name": { ... } }
_alerts: dict[str, dict[str, Any]] = {}


def _load_alerts() -> None:
    global _alerts
    if ALERTS_FILE.exists():
        try:
            _alerts = json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            _alerts = {}


def _save_alerts() -> None:
    ALERTS_FILE.write_text(
        json.dumps(_alerts, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
#  Verificação de autorização
# ---------------------------------------------------------------------------
def _is_authorized(user_id: int) -> bool:
    if not AUTHORIZED_USERS:
        return True
    return user_id in AUTHORIZED_USERS


async def _check_auth(update: Update) -> bool:
    if update.effective_user and not _is_authorized(update.effective_user.id):
        await update.message.reply_text(
            "⛔ Você não está autorizado a usar este bot."
        )
        return False
    return True


# ---------------------------------------------------------------------------
#  Utilidades de formatação
# ---------------------------------------------------------------------------
def _escape(text: str | None) -> str:
    if not text:
        return ""
    return html.escape(str(text))


def _format_job(job: dict[str, Any], index: int) -> str:
    """Formata um job como HTML para o Telegram."""
    title = _escape(job.get("title", "Sem título"))
    company = _escape(job.get("company", "Não informada"))
    location = _escape(job.get("location", "Não informada"))
    site = _escape(job.get("site", ""))
    job_url = job.get("job_url", "")
    date_posted = job.get("date_posted", "")
    job_type = job.get("job_type", "")
    is_remote = job.get("is_remote")

    min_amount = job.get("min_amount")
    max_amount = job.get("max_amount")
    currency = job.get("currency", "")
    interval = job.get("interval", "")

    # Salário
    salary = ""
    if min_amount or max_amount:
        interval_pt = {
            "yearly": "/ano",
            "monthly": "/mês",
            "weekly": "/sem",
            "daily": "/dia",
            "hourly": "/h",
        }.get(str(interval), "")

        if min_amount and max_amount:
            salary = f"💰 {currency} {min_amount:,.0f} - {max_amount:,.0f}{interval_pt}"
        elif min_amount:
            salary = f"💰 A partir de {currency} {min_amount:,.0f}{interval_pt}"
        else:
            salary = f"💰 Até {currency} {max_amount:,.0f}{interval_pt}"

    # Tipo de vaga
    tipo = ""
    if job_type:
        tipos_pt = []
        for t in str(job_type).split(", "):
            t_lower = t.strip().lower()
            tipos_pt.append(JOB_TYPES.get(t_lower, t))
        tipo = f"📌 {', '.join(tipos_pt)}"

    # Remoto
    remoto = ""
    if is_remote:
        remoto = "🏠 Remoto"

    # Data
    data = ""
    if date_posted:
        try:
            dt = datetime.strptime(str(date_posted), "%Y-%m-%d")
            data = f"📅 {dt.strftime('%d/%m/%Y')}"
        except (ValueError, TypeError):
            data = f"📅 {date_posted}"

    # Site de origem
    site_icon = SITE_DISPLAY_NAMES.get(site, f"🔍 {site}")

    lines = [
        f"<b>{index}. {title}</b>",
        f"🏢 {company}",
        f"📍 {location}",
    ]
    if salary:
        lines.append(salary)
    if tipo:
        lines.append(tipo)
    if remoto:
        lines.append(remoto)
    if data:
        lines.append(data)
    lines.append(f"🔎 {site_icon}")
    if job_url:
        lines.append(f'🔗 <a href="{job_url}">Ver vaga</a>')

    return "\n".join(lines)


def _format_results(jobs_df: "pd.DataFrame") -> list[str]:
    """Formata o DataFrame em mensagens de até ~4000 chars (limite Telegram = 4096)."""
    import pandas as pd  # noqa: F811

    messages: list[str] = []
    current = f"🎯 <b>Encontradas {len(jobs_df)} vagas</b>\n\n"

    for i, (_, row) in enumerate(jobs_df.iterrows(), 1):
        job_text = _format_job(row.to_dict(), i) + "\n\n" + "─" * 30 + "\n\n"
        if len(current) + len(job_text) > 3900:
            messages.append(current)
            current = ""
        current += job_text

    if current.strip():
        messages.append(current)

    return messages


# ---------------------------------------------------------------------------
#  Funções de scraping (wrapper thread-safe)
# ---------------------------------------------------------------------------
async def _do_scrape(
    context: ContextTypes.DEFAULT_TYPE,
    params: dict[str, Any],
) -> "pd.DataFrame":
    """Executa o scraping em uma thread separada para não bloquear o event loop."""
    import pandas as pd  # noqa: F811

    from jobspy import scrape_jobs

    def _scrape() -> pd.DataFrame:
        return scrape_jobs(**params)

    return await context.application.create_task(
        context.application.loop.run_in_executor(None, _scrape)
    )


# ---------------------------------------------------------------------------
#  /start
# ---------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_auth(update):
        return

    is_group = update.effective_chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)
    group_note = (
        "\n\n💡 <i>Em grupos, use os comandos com / para eu identificar.</i>"
        if is_group
        else ""
    )

    await update.message.reply_text(
        "🔍 <b>JobSpy Bot</b> — Busca de Vagas de Emprego\n\n"
        "Eu busco vagas em <b>LinkedIn</b>, <b>Indeed</b>, <b>Glassdoor</b>, "
        "<b>ZipRecruiter</b>, <b>Bayt</b>, <b>Naukri</b>, <b>BDJobs</b> e "
        "<b>HelloWork</b> para você!\n\n"
        "📋 <b>Comandos disponíveis:</b>\n\n"
        "/buscar — Busca rápida de vagas\n"
        "/avancada — Busca avançada com filtros\n"
        "/alerta — Configurar alertas automáticos\n"
        "/meusalertas — Ver seus alertas\n"
        "/pararalerta — Parar um alerta\n"
        "/sites — Sites disponíveis\n"
        "/ajuda — Ajuda completa\n"
        f"{group_note}",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
#  /ajuda
# ---------------------------------------------------------------------------
async def cmd_ajuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_auth(update):
        return

    await update.message.reply_text(
        "📖 <b>Ajuda — JobSpy Bot</b>\n\n"
        "<b>🔎 Busca Rápida</b>\n"
        "<code>/buscar python developer São Paulo</code>\n"
        "Busca vagas com o termo em todos os sites.\n\n"
        "<b>🔎 Busca Avançada</b>\n"
        "<code>/avancada</code>\n"
        "Passo a passo interativo com filtros:\n"
        "• Sites específicos\n"
        "• Localização\n"
        "• Tipo de vaga (integral, estágio, etc.)\n"
        "• Remoto/presencial\n"
        "• País (Indeed/Glassdoor)\n"
        "• Quantidade de resultados\n"
        "• Vagas das últimas X horas\n\n"
        "<b>🔔 Alertas</b>\n"
        "<code>/alerta</code>\n"
        "Configure buscas automáticas periódicas.\n"
        "O bot fará a busca e enviará novas vagas.\n\n"
        "<code>/meusalertas</code> — Lista seus alertas\n"
        "<code>/pararalerta</code> — Remove um alerta\n\n"
        "<b>📌 Dicas</b>\n"
        '• Use aspas para termos exatos: <code>"software engineer"</code>\n'
        "• Use - para excluir: <code>python -junior</code>\n"
        "• Indeed busca na descrição também\n"
        "• LinkedIn tem rate limit, use com moderação\n",
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
#  /sites
# ---------------------------------------------------------------------------
async def cmd_sites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_auth(update):
        return

    lines = ["🌐 <b>Sites disponíveis para busca:</b>\n"]
    for site_key in AVAILABLE_SITES:
        display = SITE_DISPLAY_NAMES.get(site_key, site_key)
        lines.append(f"  • {display} (<code>{site_key}</code>)")

    lines.append("\n💡 Na busca avançada você pode escolher quais usar.")
    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML
    )


# ---------------------------------------------------------------------------
#  /buscar — Busca rápida
# ---------------------------------------------------------------------------
async def cmd_buscar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _check_auth(update):
        return

    if not context.args:
        await update.message.reply_text(
            "📝 <b>Uso:</b> <code>/buscar termo de busca [local]</code>\n\n"
            "<b>Exemplos:</b>\n"
            "<code>/buscar python developer</code>\n"
            "<code>/buscar engenheiro de software São Paulo</code>\n"
            '<code>/buscar "data scientist" remoto</code>',
            parse_mode=ParseMode.HTML,
        )
        return

    search_term = " ".join(context.args)
    msg = await update.message.reply_text(
        f"🔍 Buscando vagas para: <b>{_escape(search_term)}</b>\n"
        "⏳ Isso pode levar alguns segundos...",
        parse_mode=ParseMode.HTML,
    )

    try:
        from jobspy import scrape_jobs

        import asyncio

        loop = asyncio.get_event_loop()
        jobs_df = await loop.run_in_executor(
            None,
            lambda: scrape_jobs(
                search_term=search_term,
                results_wanted=min(MAX_RESULTS, 10),
                verbose=0,
                description_format="plain",
            ),
        )

        if jobs_df.empty:
            await msg.edit_text(
                f"😕 Nenhuma vaga encontrada para: <b>{_escape(search_term)}</b>\n\n"
                "💡 Tente termos diferentes ou use /avancada para mais filtros.",
                parse_mode=ParseMode.HTML,
            )
            return

        # Verificar erros dos scrapers
        errors = jobs_df.attrs.get("errors", {})
        warnings_list = jobs_df.attrs.get("warnings", {})

        messages = _format_results(jobs_df)
        await msg.delete()

        for text in messages:
            await update.effective_chat.send_message(
                text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
            )

        # Mostrar erros/avisos se houver
        if errors:
            err_lines = [f"⚠️ {site}: {err}" for site, err in errors.items()]
            await update.effective_chat.send_message(
                "⚠️ <b>Alguns sites tiveram problemas:</b>\n" + "\n".join(err_lines),
                parse_mode=ParseMode.HTML,
            )

    except Exception as e:
        logger.error("Erro na busca: %s", traceback.format_exc())
        await msg.edit_text(
            f"❌ Erro ao buscar vagas: <code>{_escape(str(e))}</code>",
            parse_mode=ParseMode.HTML,
        )


# ---------------------------------------------------------------------------
#  /avancada — Busca avançada (ConversationHandler)
# ---------------------------------------------------------------------------
async def avancada_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if not await _check_auth(update):
        return ConversationHandler.END

    context.user_data["search_params"] = {}
    await update.message.reply_text(
        "🔎 <b>Busca Avançada</b>\n\n"
        "Vamos configurar sua busca passo a passo.\n"
        "Use /cancelar a qualquer momento para sair.\n\n"
        "📝 <b>Passo 1/7:</b> Qual termo de busca?\n\n"
        "<i>Exemplo: python developer, engenheiro de dados, etc.</i>",
        parse_mode=ParseMode.HTML,
    )
    return BUSCA_TERMO


async def avancada_termo(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    context.user_data["search_params"]["search_term"] = update.message.text.strip()

    await update.message.reply_text(
        "📍 <b>Passo 2/7:</b> Qual localização?\n\n"
        "<i>Exemplo: São Paulo, New York, London</i>\n"
        "Envie <code>pular</code> para buscar em qualquer lugar.",
        parse_mode=ParseMode.HTML,
    )
    return BUSCA_LOCAL


async def avancada_local(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    text = update.message.text.strip()
    if text.lower() != "pular":
        context.user_data["search_params"]["location"] = text

    # Montar teclado de sites
    keyboard = []
    row = []
    for site_key in AVAILABLE_SITES:
        display = SITE_DISPLAY_NAMES.get(site_key, site_key)
        row.append(
            InlineKeyboardButton(f"✅ {display}", callback_data=f"site_{site_key}")
        )
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append(
        [InlineKeyboardButton("✅ Todos os sites", callback_data="site_all")]
    )
    keyboard.append(
        [InlineKeyboardButton("➡️ Confirmar seleção", callback_data="site_done")]
    )

    context.user_data["selected_sites"] = set(AVAILABLE_SITES)

    await update.message.reply_text(
        "🌐 <b>Passo 3/7:</b> Quais sites buscar?\n\n"
        "Clique para desmarcar/marcar. Todos estão selecionados.\n"
        "Depois clique em <b>Confirmar</b>.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    return BUSCA_SITES


async def avancada_sites_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data
    selected = context.user_data.get("selected_sites", set(AVAILABLE_SITES))

    if data == "site_done":
        if not selected:
            await query.answer("Selecione pelo menos 1 site!", show_alert=True)
            return BUSCA_SITES

        context.user_data["search_params"]["site_name"] = list(selected)

        # Teclado de tipo de vaga
        keyboard = []
        row = []
        for key, label in JOB_TYPES.items():
            row.append(InlineKeyboardButton(label, callback_data=f"tipo_{key}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append(
            [InlineKeyboardButton("⏭ Pular", callback_data="tipo_pular")]
        )

        await query.edit_message_text(
            "📌 <b>Passo 4/7:</b> Tipo de vaga?\n\n"
            "Selecione um tipo ou pule.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
        )
        return BUSCA_TIPO

    elif data == "site_all":
        if len(selected) == len(AVAILABLE_SITES):
            selected.clear()
        else:
            selected.update(AVAILABLE_SITES)
    elif data.startswith("site_"):
        site = data[5:]
        if site in selected:
            selected.discard(site)
        else:
            selected.add(site)

    context.user_data["selected_sites"] = selected

    # Atualizar teclado
    keyboard = []
    row = []
    for site_key in AVAILABLE_SITES:
        display = SITE_DISPLAY_NAMES.get(site_key, site_key)
        check = "✅" if site_key in selected else "⬜"
        row.append(
            InlineKeyboardButton(
                f"{check} {display}", callback_data=f"site_{site_key}"
            )
        )
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    all_check = "✅" if len(selected) == len(AVAILABLE_SITES) else "⬜"
    keyboard.append(
        [
            InlineKeyboardButton(
                f"{all_check} Todos os sites", callback_data="site_all"
            )
        ]
    )
    keyboard.append(
        [InlineKeyboardButton("➡️ Confirmar seleção", callback_data="site_done")]
    )

    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return BUSCA_SITES


async def avancada_tipo_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data
    if data != "tipo_pular":
        job_type = data[5:]
        context.user_data["search_params"]["job_type"] = job_type

    keyboard = [
        [
            InlineKeyboardButton("🏠 Sim, remoto", callback_data="remoto_sim"),
            InlineKeyboardButton("🏢 Não, presencial", callback_data="remoto_nao"),
        ],
        [InlineKeyboardButton("⏭ Pular (ambos)", callback_data="remoto_pular")],
    ]

    await query.edit_message_text(
        "🏠 <b>Passo 5/7:</b> Apenas vagas remotas?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    return BUSCA_REMOTO


async def avancada_remoto_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "remoto_sim":
        context.user_data["search_params"]["is_remote"] = True
    elif data == "remoto_nao":
        context.user_data["search_params"]["is_remote"] = False

    await query.edit_message_text(
        "🌍 <b>Passo 6/7:</b> País para Indeed/Glassdoor?\n\n"
        "Envie o nome do país em inglês (ex: <code>brazil</code>, <code>usa</code>, <code>uk</code>)\n"
        "Ou envie <code>pular</code> para usar o padrão (USA).",
        parse_mode=ParseMode.HTML,
    )
    return BUSCA_PAIS


async def avancada_pais(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    text = update.message.text.strip()
    if text.lower() != "pular":
        context.user_data["search_params"]["country_indeed"] = text.lower()

    await update.message.reply_text(
        "🔢 <b>Passo 7/7:</b> Quantos resultados? (1-50)\n\n"
        f"Envie um número ou <code>pular</code> para usar o padrão ({MAX_RESULTS}).",
        parse_mode=ParseMode.HTML,
    )
    return BUSCA_QTD


async def avancada_qtd(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    text = update.message.text.strip()
    if text.lower() != "pular":
        try:
            qtd = max(1, min(50, int(text)))
            context.user_data["search_params"]["results_wanted"] = qtd
        except ValueError:
            await update.message.reply_text(
                "❌ Número inválido. Envie um número de 1 a 50:"
            )
            return BUSCA_QTD

    # Montar resumo e confirmar
    params = context.user_data["search_params"]
    summary_lines = ["🔎 <b>Resumo da busca:</b>\n"]
    summary_lines.append(
        f"📝 Termo: <b>{_escape(params.get('search_term', 'Qualquer'))}</b>"
    )
    summary_lines.append(
        f"📍 Local: <b>{_escape(params.get('location', 'Qualquer'))}</b>"
    )

    sites = params.get("site_name", AVAILABLE_SITES)
    sites_display = [SITE_DISPLAY_NAMES.get(s, s) for s in sites]
    summary_lines.append(f"🌐 Sites: {', '.join(sites_display)}")

    if "job_type" in params:
        summary_lines.append(
            f"📌 Tipo: {JOB_TYPES.get(params['job_type'], params['job_type'])}"
        )
    if "is_remote" in params:
        summary_lines.append(
            f"🏠 Remoto: {'Sim' if params['is_remote'] else 'Não'}"
        )
    if "country_indeed" in params:
        summary_lines.append(
            f"🌍 País: {_escape(params['country_indeed']).title()}"
        )
    summary_lines.append(
        f"🔢 Resultados: {params.get('results_wanted', MAX_RESULTS)}"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Buscar!", callback_data="confirma_sim"),
            InlineKeyboardButton("❌ Cancelar", callback_data="confirma_nao"),
        ]
    ]

    await update.message.reply_text(
        "\n".join(summary_lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    return BUSCA_CONFIRMA


async def avancada_confirma_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "confirma_nao":
        await query.edit_message_text("❌ Busca cancelada.")
        return ConversationHandler.END

    params = context.user_data.get("search_params", {})
    params.setdefault("results_wanted", MAX_RESULTS)
    params["verbose"] = 0
    params["description_format"] = "plain"

    await query.edit_message_text(
        "🔍 Buscando vagas...\n⏳ Isso pode levar alguns segundos..."
    )

    try:
        from jobspy import scrape_jobs

        import asyncio

        loop = asyncio.get_event_loop()
        jobs_df = await loop.run_in_executor(None, lambda: scrape_jobs(**params))

        if jobs_df.empty:
            await query.edit_message_text(
                "😕 Nenhuma vaga encontrada com esses filtros.\n"
                "💡 Tente expandir os critérios com /avancada"
            )
            return ConversationHandler.END

        errors = jobs_df.attrs.get("errors", {})

        messages = _format_results(jobs_df)
        await query.edit_message_text(messages[0], parse_mode=ParseMode.HTML,
                                       disable_web_page_preview=True)
        for text in messages[1:]:
            await update.effective_chat.send_message(
                text, parse_mode=ParseMode.HTML, disable_web_page_preview=True
            )

        if errors:
            err_lines = [f"⚠️ {site}: {err}" for site, err in errors.items()]
            await update.effective_chat.send_message(
                "⚠️ <b>Problemas em alguns sites:</b>\n" + "\n".join(err_lines),
                parse_mode=ParseMode.HTML,
            )

    except Exception as e:
        logger.error("Erro na busca avançada: %s", traceback.format_exc())
        await query.edit_message_text(
            f"❌ Erro: <code>{_escape(str(e))}</code>",
            parse_mode=ParseMode.HTML,
        )

    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Operação cancelada.")
    context.user_data.clear()
    return ConversationHandler.END


# ---------------------------------------------------------------------------
#  /alerta — Alertas automáticos (ConversationHandler)
# ---------------------------------------------------------------------------
async def alerta_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if not await _check_auth(update):
        return ConversationHandler.END

    context.user_data["alert_params"] = {}

    await update.message.reply_text(
        "🔔 <b>Configurar Alerta de Vagas</b>\n\n"
        "Vou configurar uma busca automática para você.\n"
        "Use /cancelar para sair.\n\n"
        "📝 <b>Passo 1/4:</b> Qual termo de busca para o alerta?\n\n"
        "<i>Exemplo: python developer, data engineer</i>",
        parse_mode=ParseMode.HTML,
    )
    return ALERTA_TERMO


async def alerta_termo(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    context.user_data["alert_params"]["search_term"] = update.message.text.strip()

    await update.message.reply_text(
        "📍 <b>Passo 2/4:</b> Localização para o alerta?\n\n"
        "Envie <code>pular</code> para qualquer lugar.",
        parse_mode=ParseMode.HTML,
    )
    return ALERTA_LOCAL


async def alerta_local(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    text = update.message.text.strip()
    if text.lower() != "pular":
        context.user_data["alert_params"]["location"] = text

    # Sites
    keyboard = []
    row = []
    for site_key in AVAILABLE_SITES:
        display = SITE_DISPLAY_NAMES.get(site_key, site_key)
        row.append(
            InlineKeyboardButton(f"✅ {display}", callback_data=f"asite_{site_key}")
        )
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append(
        [InlineKeyboardButton("✅ Todos", callback_data="asite_all")]
    )
    keyboard.append(
        [InlineKeyboardButton("➡️ Confirmar", callback_data="asite_done")]
    )

    context.user_data["alert_selected_sites"] = set(AVAILABLE_SITES)

    await update.message.reply_text(
        "🌐 <b>Passo 3/4:</b> Sites para o alerta?\n"
        "Clique para marcar/desmarcar.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    return ALERTA_SITES


async def alerta_sites_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data
    selected = context.user_data.get("alert_selected_sites", set(AVAILABLE_SITES))

    if data == "asite_done":
        if not selected:
            await query.answer("Selecione pelo menos 1 site!", show_alert=True)
            return ALERTA_SITES

        context.user_data["alert_params"]["site_name"] = list(selected)

        await query.edit_message_text(
            f"⏱ <b>Passo 4/4:</b> Intervalo do alerta em minutos?\n\n"
            f"Mínimo: {ALERT_INTERVAL_MINUTES} min\n"
            f"Envie um número (ex: <code>60</code> para 1 hora, <code>1440</code> para 1 dia).",
            parse_mode=ParseMode.HTML,
        )
        return ALERTA_INTERVALO

    elif data == "asite_all":
        if len(selected) == len(AVAILABLE_SITES):
            selected.clear()
        else:
            selected.update(AVAILABLE_SITES)
    elif data.startswith("asite_"):
        site = data[6:]
        if site in selected:
            selected.discard(site)
        else:
            selected.add(site)

    context.user_data["alert_selected_sites"] = selected

    # Atualizar teclado
    keyboard = []
    row = []
    for site_key in AVAILABLE_SITES:
        display = SITE_DISPLAY_NAMES.get(site_key, site_key)
        check = "✅" if site_key in selected else "⬜"
        row.append(
            InlineKeyboardButton(
                f"{check} {display}", callback_data=f"asite_{site_key}"
            )
        )
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    all_check = "✅" if len(selected) == len(AVAILABLE_SITES) else "⬜"
    keyboard.append(
        [InlineKeyboardButton(f"{all_check} Todos", callback_data="asite_all")]
    )
    keyboard.append(
        [InlineKeyboardButton("➡️ Confirmar", callback_data="asite_done")]
    )

    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ALERTA_SITES


async def alerta_intervalo(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    text = update.message.text.strip()
    try:
        intervalo = max(ALERT_INTERVAL_MINUTES, int(text))
    except ValueError:
        await update.message.reply_text(
            f"❌ Número inválido. Envie um número (mínimo {ALERT_INTERVAL_MINUTES}):"
        )
        return ALERTA_INTERVALO

    params = context.user_data["alert_params"]
    chat_id = update.effective_chat.id

    # Gerar nome do alerta
    term = params.get("search_term", "geral")
    alert_name = re.sub(r"[^a-zA-Z0-9]", "_", term)[:20]
    alert_key = f"{chat_id}:{alert_name}"

    # Salvar alerta
    alert_data = {
        "chat_id": chat_id,
        "params": params,
        "interval_minutes": intervalo,
        "name": alert_name,
        "search_term": params.get("search_term", ""),
        "created_at": datetime.now().isoformat(),
        "seen_urls": [],
    }
    _alerts[alert_key] = alert_data
    _save_alerts()

    # Agendar job
    context.job_queue.run_repeating(
        _alert_job,
        interval=intervalo * 60,
        first=10,
        chat_id=chat_id,
        name=alert_key,
        data=alert_data,
    )

    sites = params.get("site_name", AVAILABLE_SITES)
    sites_display = [SITE_DISPLAY_NAMES.get(s, s) for s in sites]

    await update.message.reply_text(
        "✅ <b>Alerta configurado!</b>\n\n"
        f"📝 Termo: <b>{_escape(params.get('search_term', 'Qualquer'))}</b>\n"
        f"📍 Local: <b>{_escape(params.get('location', 'Qualquer'))}</b>\n"
        f"🌐 Sites: {', '.join(sites_display)}\n"
        f"⏱ Intervalo: a cada <b>{intervalo} minutos</b>\n\n"
        "🔔 Você receberá novas vagas automaticamente!\n"
        "Use /meusalertas para ver seus alertas.\n"
        "Use /pararalerta para remover.",
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


async def _alert_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job que executa periodicamente para enviar novas vagas."""
    job = context.job
    alert_data = job.data
    chat_id = alert_data["chat_id"]
    params = dict(alert_data["params"])
    params["verbose"] = 0
    params["description_format"] = "plain"
    params.setdefault("results_wanted", 10)
    params.setdefault("hours_old", alert_data["interval_minutes"] * 2 // 60 or 24)

    try:
        from jobspy import scrape_jobs

        import asyncio

        loop = asyncio.get_event_loop()
        jobs_df = await loop.run_in_executor(None, lambda: scrape_jobs(**params))

        if jobs_df.empty:
            return

        # Filtrar vagas já vistas
        seen = set(alert_data.get("seen_urls", []))
        new_jobs = jobs_df[~jobs_df["job_url"].isin(seen)]

        if new_jobs.empty:
            return

        # Atualizar vistas (manter últimas 500)
        new_urls = new_jobs["job_url"].tolist()
        all_seen = list(seen | set(new_urls))
        alert_data["seen_urls"] = all_seen[-500:]
        _alerts[job.name] = alert_data
        _save_alerts()

        # Enviar
        header = (
            f"🔔 <b>Alerta: {_escape(alert_data.get('search_term', ''))}</b>\n"
            f"📊 {len(new_jobs)} nova(s) vaga(s) encontrada(s)!\n\n"
        )
        messages = _format_results(new_jobs)
        messages[0] = header + messages[0]

        for text in messages:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )

    except Exception as e:
        logger.error("Erro no alerta %s: %s", job.name, traceback.format_exc())


# ---------------------------------------------------------------------------
#  /meusalertas
# ---------------------------------------------------------------------------
async def cmd_meusalertas(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_auth(update):
        return

    chat_id = update.effective_chat.id
    user_alerts = {
        k: v for k, v in _alerts.items() if v.get("chat_id") == chat_id
    }

    if not user_alerts:
        await update.message.reply_text(
            "📭 Você não tem alertas configurados.\n"
            "Use /alerta para criar um!"
        )
        return

    lines = ["🔔 <b>Seus alertas:</b>\n"]
    for key, alert in user_alerts.items():
        name = alert.get("name", "?")
        term = _escape(alert.get("search_term", "?"))
        interval = alert.get("interval_minutes", "?")
        location = _escape(alert.get("params", {}).get("location", "Qualquer"))
        created = alert.get("created_at", "?")
        try:
            created_dt = datetime.fromisoformat(created)
            created = created_dt.strftime("%d/%m/%Y %H:%M")
        except (ValueError, TypeError):
            pass

        lines.append(
            f"📌 <b>{name}</b>\n"
            f"   Termo: {term}\n"
            f"   Local: {location}\n"
            f"   Intervalo: {interval} min\n"
            f"   Criado em: {created}\n"
        )

    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML
    )


# ---------------------------------------------------------------------------
#  /pararalerta
# ---------------------------------------------------------------------------
async def cmd_pararalerta(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not await _check_auth(update):
        return

    chat_id = update.effective_chat.id
    user_alerts = {
        k: v for k, v in _alerts.items() if v.get("chat_id") == chat_id
    }

    if not user_alerts:
        await update.message.reply_text("📭 Você não tem alertas para remover.")
        return

    keyboard = []
    for key, alert in user_alerts.items():
        name = alert.get("name", "?")
        term = alert.get("search_term", "?")
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"🗑 {name} ({term})", callback_data=f"delalerta_{key}"
                )
            ]
        )
    keyboard.append(
        [InlineKeyboardButton("❌ Cancelar", callback_data="delalerta_cancel")]
    )

    await update.message.reply_text(
        "🗑 <b>Qual alerta deseja remover?</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )


async def pararalerta_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "delalerta_cancel":
        await query.edit_message_text("✅ Nenhum alerta removido.")
        return

    alert_key = data[len("delalerta_"):]

    # Remover job do scheduler
    jobs = context.job_queue.get_jobs_by_name(alert_key)
    for job in jobs:
        job.schedule_removal()

    # Remover do armazenamento
    if alert_key in _alerts:
        del _alerts[alert_key]
        _save_alerts()

    await query.edit_message_text("✅ Alerta removido com sucesso!")


# ---------------------------------------------------------------------------
#  Restaurar alertas ao iniciar
# ---------------------------------------------------------------------------
async def _restore_alerts(application: Application) -> None:
    """Restaura alertas salvos ao iniciar o bot."""
    _load_alerts()
    for key, alert_data in _alerts.items():
        try:
            application.job_queue.run_repeating(
                _alert_job,
                interval=alert_data.get("interval_minutes", 60) * 60,
                first=60,  # Espera 1 min antes do primeiro check
                chat_id=alert_data["chat_id"],
                name=key,
                data=alert_data,
            )
            logger.info("Alerta restaurado: %s", key)
        except Exception:
            logger.error("Erro ao restaurar alerta %s", key, exc_info=True)


# ---------------------------------------------------------------------------
#  main
# ---------------------------------------------------------------------------
def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN == "SEU_TOKEN_AQUI":
        print(
            "❌ Configure o token do bot!\n"
            "1. Copie .env.example para .env\n"
            "2. Coloque o token do @BotFather em TELEGRAM_BOT_TOKEN\n"
        )
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # ConversationHandler — Busca Avançada
    avancada_handler = ConversationHandler(
        entry_points=[CommandHandler("avancada", avancada_start)],
        states={
            BUSCA_TERMO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, avancada_termo)
            ],
            BUSCA_LOCAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, avancada_local)
            ],
            BUSCA_SITES: [
                CallbackQueryHandler(avancada_sites_callback, pattern=r"^site_")
            ],
            BUSCA_TIPO: [
                CallbackQueryHandler(avancada_tipo_callback, pattern=r"^tipo_")
            ],
            BUSCA_REMOTO: [
                CallbackQueryHandler(avancada_remoto_callback, pattern=r"^remoto_")
            ],
            BUSCA_PAIS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, avancada_pais)
            ],
            BUSCA_QTD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, avancada_qtd)
            ],
            BUSCA_CONFIRMA: [
                CallbackQueryHandler(
                    avancada_confirma_callback, pattern=r"^confirma_"
                )
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        per_chat=True,
    )

    # ConversationHandler — Alertas
    alerta_handler = ConversationHandler(
        entry_points=[CommandHandler("alerta", alerta_start)],
        states={
            ALERTA_TERMO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, alerta_termo)
            ],
            ALERTA_LOCAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, alerta_local)
            ],
            ALERTA_SITES: [
                CallbackQueryHandler(alerta_sites_callback, pattern=r"^asite_")
            ],
            ALERTA_INTERVALO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, alerta_intervalo)
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        per_chat=True,
    )

    # Registrar handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ajuda", cmd_ajuda))
    app.add_handler(CommandHandler("help", cmd_ajuda))
    app.add_handler(CommandHandler("sites", cmd_sites))
    app.add_handler(CommandHandler("buscar", cmd_buscar))
    app.add_handler(CommandHandler("meusalertas", cmd_meusalertas))
    app.add_handler(CommandHandler("pararalerta", cmd_pararalerta))
    app.add_handler(
        CallbackQueryHandler(pararalerta_callback, pattern=r"^delalerta_")
    )
    app.add_handler(avancada_handler)
    app.add_handler(alerta_handler)

    # Restaurar alertas ao iniciar
    app.post_init = _restore_alerts

    logger.info("🤖 Bot iniciado!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
