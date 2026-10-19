"""
Módulo de integração com o Trabalha Brasil (trabalhabrasil.com.br).
Conectado ao Banco Nacional de Empregos (BNE) e SINE, é um dos maiores portais públicos de vagas do país.
"""

from __future__ import annotations

import html
import logging
import re
import unicodedata
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

BASE_URL = "https://www.trabalhabrasil.com.br"


def _slugify(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    cleaned = "".join([c for c in nfkd if not unicodedata.combining(c)])
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", "", cleaned).strip().lower()
    return re.sub(r"[\s-]+", "-", cleaned)


def _parse_salary(text: str) -> tuple[float | None, float | None]:
    if not text or "combinar" in text.lower():
        return None, None
    numbers = re.findall(r"\d+(?:\.\d+)*(?:,\d+)?", text)
    floats: list[float] = []
    for num in numbers:
        try:
            val = float(num.replace(".", "").replace(",", "."))
            floats.append(val)
        except ValueError:
            pass
    if len(floats) >= 2:
        return min(floats[0], floats[1]), max(floats[0], floats[1])
    elif len(floats) == 1:
        return floats[0], floats[0]
    return None, None


def _normalize_query(term: str) -> str:
    """Normaliza termos comuns para nomes de cargos compatíveis com o Trabalha Brasil."""
    term = re.sub(r"\bdev\b", "desenvolvedor", term, flags=re.IGNORECASE)
    term = re.sub(r"\bjr\b", "junior", term, flags=re.IGNORECASE)
    term = re.sub(r"\bsr\b", "senior", term, flags=re.IGNORECASE)
    return term


def scrape_trabalha_brasil(
    search_term: str = "",
    location: str = "",
    is_remote: bool = False,
    results_wanted: int = 15,
) -> list[dict[str, Any]]:
    """
    Busca vagas no Trabalha Brasil.

    :param search_term: Termo ou profissão buscada.
    :param location: Localização desejada.
    :param is_remote: Se True, filtra vagas remotas.
    :param results_wanted: Quantidade máxima de vagas.
    :return: Lista de vagas encontradas.
    """
    norm_term = _normalize_query(search_term) if search_term else ""
    slug = _slugify(norm_term) if norm_term else ""
    url = f"{BASE_URL}/vagas-de-emprego/{slug}" if slug else f"{BASE_URL}/vagas-de-emprego"

    jobs: list[dict[str, Any]] = []

    try:
        with httpx.Client(
            headers=HEADERS, follow_redirects=True, timeout=12.0
        ) as client:
            response = client.get(url)
            if response.status_code != 200:
                logger.warning(
                    "Trabalha Brasil retornou HTTP %s para %s",
                    response.status_code,
                    url,
                )
                return jobs

            raw_html = response.text

            # Encontra cards de vagas
            card_matches = re.finditer(
                r'<a\s+[^>]*href="(/vagas-de-emprego-em-[^"]+/(\d+))"[^>]*>(.*?)</a>',
                raw_html,
                re.DOTALL,
            )

            for m in card_matches:
                v_href, v_id, content = m.group(1), m.group(2), m.group(3)

                # Limpa tags e SVGs
                clean_content = re.sub(r"<svg.*?</svg>", "", content, flags=re.DOTALL)
                clean_text = " ".join(
                    re.sub(r"<[^>]+>", " ", clean_content).split()
                )

                # Título
                title_m = re.search(
                    r'<h2[^>]*class="[^"]*job-title[^"]*"[^>]*>\s*(?:Vaga de)?\s*(.*?)\s*</h2>',
                    content,
                    re.DOTALL,
                )
                if title_m:
                    title = html.unescape(
                        re.sub(r"<[^>]+>", "", title_m.group(1)).strip()
                    )
                else:
                    # Fallback pelo texto
                    t_m = re.search(r"Vaga de\s+(.*?)\s+(?:[A-Z0-9][a-z0-9]+|R\$)", clean_text)
                    title = t_m.group(1).strip() if t_m else "Vaga Trabalha Brasil"

                # Empresa
                comp_m = re.search(
                    r'<p[^>]*class="[^"]*job-company[^"]*"[^>]*>(.*?)</p>',
                    clean_content,
                    re.DOTALL,
                )
                company = (
                    html.unescape(
                        re.sub(r"<[^>]+>", "", comp_m.group(1)).strip()
                    )
                    if comp_m
                    else "Empresa via Trabalha Brasil"
                )

                # Localização do slug da URL (ex: belo-horizonte-mg)
                loc_slug_m = re.search(r"/vagas-de-emprego-em-([^/]+)/", v_href)
                loc_str = "Brasil"
                if loc_slug_m:
                    parts = loc_slug_m.group(1).split("-")
                    if len(parts) >= 2:
                        uf = parts[-1].upper()
                        city = " ".join(p.capitalize() for p in parts[:-1])
                        loc_str = f"{city} - {uf}"
                    else:
                        loc_str = parts[0].capitalize()

                job_is_remote = "remoto" in clean_text.lower() or "home office" in clean_text.lower()
                if is_remote and not job_is_remote:
                    continue

                if location:
                    loc_low = location.strip().lower()
                    if loc_low in ("brasil", "brazil"):
                        pass  # Trabalha Brasil é 100% Brasil
                    elif loc_low == "remoto":
                        if not job_is_remote:
                            continue
                    elif loc_low not in loc_str.lower() and loc_low not in clean_text.lower():
                        continue

                # Salário
                min_amount, max_amount = None, None
                salary_m = re.search(r"R\$\s*[\d\.,]+(?:\s*(?:a|até)\s*R\$\s*[\d\.,]+)?", clean_text)
                if salary_m:
                    min_amount, max_amount = _parse_salary(salary_m.group(0))

                job_url = urljoin(BASE_URL, v_href)

                jobs.append(
                    {
                        "id": f"tb_{v_id}",
                        "site": "trabalha_brasil",
                        "title": title,
                        "company": company,
                        "location": loc_str,
                        "date_posted": "",
                        "job_url": job_url,
                        "job_url_direct": job_url,
                        "is_remote": job_is_remote,
                        "description": clean_text,
                        "min_amount": min_amount,
                        "max_amount": max_amount,
                        "currency": "BRL" if (min_amount or max_amount) else None,
                        "interval": "monthly"
                        if (min_amount or max_amount)
                        else None,
                        "salary_source": "trabalha_brasil"
                        if (min_amount or max_amount)
                        else None,
                    }
                )

                if len(jobs) >= results_wanted:
                    break

    except Exception as exc:
        logger.error("Erro ao raspar Trabalha Brasil: %s", exc)

    return jobs
