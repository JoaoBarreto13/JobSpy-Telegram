"""
Módulo de integração com o Programathor (programathor.com.br).
O maior portal brasileiro especializado em vagas de tecnologia e programação.
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

BASE_URL = "https://programathor.com.br"


def scrape_programathor(
    search_term: str = "",
    location: str = "",
    is_remote: bool = False,
    results_wanted: int = 15,
) -> list[dict[str, Any]]:
    """
    Busca vagas no portal Programathor.

    :param search_term: Linguagem ou cargo tecnológico (ex: python, react).
    :param location: Localização ou região.
    :param is_remote: Se True, filtra apenas oportunidades remotas.
    :param results_wanted: Quantidade máxima de vagas a retornar.
    :return: Lista de vagas formatadas.
    """
    url = f"{BASE_URL}/jobs"
    params: dict[str, str] = {}
    if search_term:
        params["q"] = search_term.strip()

    jobs: list[dict[str, Any]] = []

    try:
        with httpx.Client(
            headers=HEADERS, follow_redirects=True, timeout=12.0
        ) as client:
            response = client.get(url, params=params)
            if response.status_code != 200:
                logger.warning(
                    "Programathor retornou HTTP %s para %s", response.status_code, url
                )
                return jobs

            raw_html = response.text

            # Encontra os blocos de vaga com links /jobs/\d+-
            job_blocks = re.findall(
                r'<a\s+[^>]*href="(/jobs/\d+-[^"]+)"[^>]*>(.*?)</a>',
                raw_html,
                re.DOTALL,
            )

            for href, content in job_blocks:
                title_m = re.search(r"<h3[^>]*>(.*?)</h3>", content, re.DOTALL)
                if not title_m:
                    continue
                title = html.unescape(title_m.group(1).strip())

                # Extrai empresa pelo ícone de maleta (fa-briefcase)
                comp_m = re.search(
                    r"<i[^>]*class=['\"][^'\"]*fa-briefcase[^'\"]*['\"][^>]*></i>\s*([^<]+)",
                    content,
                )
                company = (
                    html.unescape(comp_m.group(1).strip())
                    if comp_m
                    else "Empresa na Programathor"
                )

                # Extrai localização pelo ícone de mapa (fa-map-marker-alt)
                loc_m = re.search(
                    r"<i[^>]*class=['\"][^'\"]*fa-map-marker-alt[^'\"]*['\"][^>]*></i>\s*([^<]+)",
                    content,
                )
                loc_str = (
                    html.unescape(loc_m.group(1).strip())
                    if loc_m
                    else ("Remoto" if "remoto" in content.lower() else "Brasil")
                )

                # Extrai regime de contratação (PJ / CLT)
                contract_m = re.search(
                    r"<i[^>]*class=['\"][^'\"]*fa-file-alt[^'\"]*['\"][^>]*></i>\s*([^<]+)",
                    content,
                )
                contract_type = contract_m.group(1).strip() if contract_m else ""

                # Extrai senioridade (Júnior, Pleno, Sênior)
                seniority_m = re.search(
                    r"<i[^>]*class=['\"][^'\"]*fa-chart-bar[^'\"]*['\"][^>]*></i>\s*([^<]+)",
                    content,
                )
                seniority = seniority_m.group(1).strip() if seniority_m else ""

                # Tags de tecnologias
                tags = [
                    html.unescape(t.strip())
                    for t in re.findall(
                        r"<span[^>]*class=['\"][^'\"]*tag-list[^'\"]*['\"][^>]*>([^<]+)</span>",
                        content,
                    )
                    if t.strip()
                ]

                job_is_remote = is_remote or ("remoto" in loc_str.lower())
                if is_remote and not job_is_remote:
                    continue

                # Filtragem de localidade se especificada
                if location:
                    loc_low = location.strip().lower()
                    if loc_low == "remoto":
                        if not job_is_remote:
                            continue
                    elif (
                        loc_low not in loc_str.lower()
                        and loc_low not in content.lower()
                    ):
                        continue

                # Mapeamento do tipo de vaga
                job_type = "fulltime"
                if "pj" in contract_type.lower():
                    job_type = "contract"
                elif "estágio" in title.lower() or "estagio" in title.lower():
                    job_type = "internship"

                # Descrição sumarizada
                desc_parts = []
                if seniority:
                    desc_parts.append(f"Nível: {seniority}")
                if contract_type:
                    desc_parts.append(f"Contrato: {contract_type}")
                if tags:
                    desc_parts.append(f"Stack: {', '.join(tags)}")
                description = " | ".join(desc_parts)

                job_url = urljoin(BASE_URL, href)
                v_id_m = re.search(r"/jobs/(\d+)", href)
                v_id = v_id_m.group(1) if v_id_m else href

                jobs.append(
                    {
                        "id": f"programathor_{v_id}",
                        "site": "programathor",
                        "title": title,
                        "company": company,
                        "location": loc_str,
                        "date_posted": "",
                        "job_url": job_url,
                        "job_url_direct": job_url,
                        "job_type": job_type,
                        "is_remote": job_is_remote,
                        "description": description,
                        "skills": tags,
                        "min_amount": None,
                        "max_amount": None,
                        "currency": "BRL",
                        "interval": None,
                        "salary_source": None,
                    }
                )

                if len(jobs) >= results_wanted:
                    break

    except Exception as exc:
        logger.error("Erro ao raspar Programathor: %s", exc)

    return jobs
