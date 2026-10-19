"""
Módulo de integração com a Gupy (portal.gupy.io).
A Gupy é a maior plataforma de recrutamento e seleção corporativa do Brasil.
Utiliza o endpoint público oficial de busca de vagas em JSON do Portal Gupy.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

BASE_API_URL = "https://portal.gupy.io/api/job-search/jobs"


def scrape_gupy(
    search_term: str = "",
    location: str = "",
    is_remote: bool = False,
    results_wanted: int = 15,
) -> list[dict[str, Any]]:
    """
    Busca vagas no Portal Gupy via API pública.

    :param search_term: Palavra-chave ou cargo pesquisado.
    :param location: Cidade, estado ou região desejada.
    :param is_remote: Se True, filtra apenas vagas remotas / home office.
    :param results_wanted: Quantidade máxima de resultados a retornar.
    :return: Lista de dicionários representando as vagas encontradas.
    """
    params: dict[str, Any] = {
        "jobName": search_term.strip() if search_term else "",
        "limit": min(results_wanted * 2, 50),
        "offset": 0,
    }

    if is_remote:
        params["workplaceType"] = "remote"

    req_headers = dict(HEADERS)
    if search_term:
        req_headers["Referer"] = (
            f"https://portal.gupy.io/job-search/term={quote(search_term)}"
        )
    else:
        req_headers["Referer"] = "https://portal.gupy.io/job-search"

    jobs: list[dict[str, Any]] = []

    try:
        with httpx.Client(headers=req_headers, timeout=12.0) as client:
            response = client.get(BASE_API_URL, params=params)
            if response.status_code != 200:
                logger.warning(
                    "Gupy respondeu com status HTTP %s", response.status_code
                )
                return jobs

            payload = response.json()
            data = payload.get("data", [])

            for item in data:
                city = (item.get("city") or "").strip()
                state = (item.get("state") or "").strip()
                workplace_type = (item.get("workplaceType") or "").lower()

                # Localização amigável
                loc_parts = [p for p in (city, state) if p]
                if loc_parts:
                    loc_str = ", ".join(loc_parts)
                    if workplace_type == "remote":
                        loc_str += " (Remoto)"
                    elif workplace_type == "hybrid":
                        loc_str += " (Híbrido)"
                elif workplace_type == "remote":
                    loc_str = "Remoto (Brasil)"
                else:
                    loc_str = "Brasil"

                item_is_remote = workplace_type == "remote"

                # Filtragem de localização se especificada
                if location:
                    loc_low = location.strip().lower()
                    text_to_check = f"{loc_str} {item.get('description', '')}".lower()
                    if loc_low == "remoto":
                        if not item_is_remote and "remoto" not in text_to_check:
                            continue
                    elif loc_low not in text_to_check:
                        continue

                # Data de publicação
                pub_date_raw = item.get("publishedDate")
                date_posted = ""
                if pub_date_raw:
                    try:
                        dt = datetime.fromisoformat(
                            pub_date_raw.replace("Z", "+00:00")
                        )
                        date_posted = dt.strftime("%Y-%m-%d")
                    except Exception:
                        date_posted = str(pub_date_raw)[:10]

                # Mapeamento do tipo de vaga Gupy
                gupy_type = (item.get("type") or "").lower()
                job_type = "fulltime"
                if "internship" in gupy_type or "estagio" in gupy_type:
                    job_type = "internship"
                elif "temporary" in gupy_type or "temporario" in gupy_type:
                    job_type = "temporary"
                elif "legal_entity" in gupy_type or "pj" in gupy_type:
                    job_type = "contract"

                job_id = str(item.get("id", ""))
                job_url = item.get("jobUrl") or (
                    f"https://portal.gupy.io/job-search/job?id={job_id}"
                )

                job = {
                    "id": f"gupy_{job_id}",
                    "site": "gupy",
                    "title": (item.get("name") or "Vaga na Gupy").strip(),
                    "company": (
                        item.get("careerPageName") or "Empresa na Gupy"
                    ).strip(),
                    "location": loc_str,
                    "date_posted": date_posted,
                    "job_url": job_url,
                    "job_url_direct": job_url,
                    "job_type": job_type,
                    "is_remote": item_is_remote,
                    "company_logo": item.get("careerPageLogo") or "",
                    "description": item.get("description") or "",
                    "min_amount": None,
                    "max_amount": None,
                    "currency": "BRL",
                    "interval": None,
                    "salary_source": None,
                }

                jobs.append(job)
                if len(jobs) >= results_wanted:
                    break

    except Exception as exc:
        logger.error("Erro ao raspar Gupy: %s", exc)

    return jobs
