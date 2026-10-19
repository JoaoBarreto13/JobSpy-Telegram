"""
Módulo de integração com o InfoJobs Brasil (infojobs.com.br).
Um dos maiores e mais tradicionais portais de vagas e currículos do Brasil.
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

BASE_URL = "https://www.infojobs.com.br"


def _slugify(text: str) -> str:
    """Converte texto em slug amigável para URLs do InfoJobs."""
    nfkd = unicodedata.normalize("NFKD", text)
    cleaned = "".join([c for c in nfkd if not unicodedata.combining(c)])
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", "", cleaned).strip().lower()
    return re.sub(r"[\s-]+", "-", cleaned)


def _parse_salary(salary_text: str) -> tuple[float | None, float | None]:
    """Extrai valores mínimos e máximos de salários informados no padrão InfoJobs."""
    if not salary_text or "combinar" in salary_text.lower():
        return None, None

    # Exemplo: R$ 3.000,00 a R$ 5.000,00 ou R$ 4.500,00
    cleaned = re.sub(r"[^\d,\-a]", "", salary_text)
    numbers = re.findall(r"\d+(?:\.\d+)*(?:,\d+)?", salary_text)
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
    """Normaliza abreviações comuns de TI para os nomes formais que o InfoJobs indexa."""
    term = re.sub(r"\bdev\b", "desenvolvedor", term, flags=re.IGNORECASE)
    term = re.sub(r"\bjr\b", "junior", term, flags=re.IGNORECASE)
    term = re.sub(r"\bsr\b", "senior", term, flags=re.IGNORECASE)
    return term


def scrape_infojobs(
    search_term: str = "",
    location: str = "",
    is_remote: bool = False,
    results_wanted: int = 15,
) -> list[dict[str, Any]]:
    """
    Busca vagas no portal InfoJobs Brasil.

    :param search_term: Termo ou cargo pesquisado.
    :param location: Localização (cidade ou estado).
    :param is_remote: Se True, busca vagas com filtro de Home Office.
    :param results_wanted: Quantidade máxima de vagas a retornar.
    :return: Lista de vagas formatadas.
    """
    norm_term = _normalize_query(search_term) if search_term else ""
    slug = _slugify(norm_term) if norm_term else "empregos"

    if location and not is_remote:
        loc_slug = _slugify(location)
        path = f"/vagas-de-emprego-{slug}-em-{loc_slug}.aspx"
    else:
        path = f"/vagas-de-emprego-{slug}.aspx"

    url = f"{BASE_URL}{path}"
    params: dict[str, str] = {}
    if is_remote:
        params["ol"] = "1"  # Filtro InfoJobs para Home Office

    jobs: list[dict[str, Any]] = []

    try:
        with httpx.Client(
            headers=HEADERS, follow_redirects=True, timeout=12.0
        ) as client:
            response = client.get(url, params=params)
            if response.status_code != 200:
                logger.warning(
                    "InfoJobs retornou HTTP %s para %s", response.status_code, url
                )
                return jobs

            raw_html = response.text

            # Encontrar cada bloco de vaga pelo padrão de ID
            card_matches = re.finditer(
                r'<div[^>]*\bid="vacancy(\d+)"[^>]*data-href="([^"]+)"[^>]*>(.*?)'
                r"(?=<div[^>]*\bid=\"vacancy|\Z)",
                raw_html,
                re.DOTALL,
            )

            for m in card_matches:
                v_id = m.group(1)
                v_href = m.group(2)
                card_content = m.group(3)

                # Título
                title_m = re.search(
                    r'<h2[^>]*class="[^"]*js_vacancyTitle[^"]*"[^>]*>(.*?)</h2>',
                    card_content,
                    re.DOTALL,
                )
                title = (
                    html.unescape(
                        re.sub(r"<[^>]+>", "", title_m.group(1)).strip()
                    )
                    if title_m
                    else "Vaga no InfoJobs"
                )

                # Data de publicação
                date_m = re.search(r'data-value="([^"]+)"', card_content)
                date_posted = ""
                if date_m:
                    try:
                        date_posted = date_m.group(1)[:10].replace("/", "-")
                    except Exception:
                        date_posted = ""

                # Empresa
                comp_m = re.search(
                    r'<a[^>]*class="text-body[^"]*"[^>]*href="https://www\.infojobs\.com\.br/empresa-[^"]*"[^>]*>(.*?)</a>',
                    card_content,
                    re.DOTALL,
                )
                company = "Confidencial"
                if comp_m:
                    comp_text = html.unescape(
                        " ".join(re.sub(r"<[^>]+>", " ", comp_m.group(1)).split())
                    ).strip()
                    company = (
                        re.split(r"Este selo indica|Verificada", comp_text)[0].strip()
                        or "Confidencial"
                    )

                # Localização
                loc_m = re.search(
                    r'<div class="mb-8">(.*?)</div>', card_content, re.DOTALL
                )
                loc_text = "Brasil"
                if loc_m:
                    loc_clean = html.unescape(
                        " ".join(re.sub(r"<[^>]+>", " ", loc_m.group(1)).split())
                    ).strip()
                    loc_text = re.split(r",\s*\d+\s*Km", loc_clean)[0].strip()

                card_lower = card_content.lower()
                job_is_remote = is_remote or (
                    "home office" in card_lower or "remoto" in card_lower
                )
                if job_is_remote and "remoto" not in loc_text.lower():
                    loc_text += " (Home Office)"

                # Salário
                salary_m = re.search(
                    r"icon-money.*?</div>\s*([^<]+)", card_content, re.DOTALL
                )
                salary_text = salary_m.group(1).strip() if salary_m else ""
                min_amount, max_amount = _parse_salary(salary_text)

                # Descrição
                desc_m = re.search(
                    r'<div class="text-medium">\s*(.*?)\s*</div>',
                    card_content,
                    re.DOTALL,
                )
                desc = (
                    html.unescape(
                        " ".join(re.sub(r"<[^>]+>", " ", desc_m.group(1)).split())
                    )
                    if desc_m
                    else ""
                )

                # Filtro de relevância para evitar resultados espúrios do motor de busca do InfoJobs
                if norm_term:
                    keywords = [
                        w for w in re.split(r"\s+", norm_term.lower()) if len(w) > 2
                    ]
                    main_keywords = [
                        w
                        for w in keywords
                        if w not in ("junior", "pleno", "senior", "estagio")
                    ]
                    job_text_all = f"{title} {desc}".lower()
                    if main_keywords and not any(
                        k[:4] in job_text_all for k in main_keywords
                    ):
                        continue

                job_url = urljoin(BASE_URL, v_href)

                jobs.append(
                    {
                        "id": f"infojobs_{v_id}",
                        "site": "infojobs",
                        "title": title,
                        "company": company,
                        "location": loc_text,
                        "date_posted": date_posted,
                        "job_url": job_url,
                        "job_url_direct": job_url,
                        "is_remote": job_is_remote,
                        "description": desc,
                        "min_amount": min_amount,
                        "max_amount": max_amount,
                        "currency": "BRL" if (min_amount or max_amount) else None,
                        "interval": "monthly"
                        if (min_amount or max_amount)
                        else None,
                        "salary_source": "infojobs"
                        if (min_amount or max_amount)
                        else None,
                    }
                )

                if len(jobs) >= results_wanted:
                    break

    except Exception as exc:
        logger.error("Erro ao raspar InfoJobs: %s", exc)

    return jobs
