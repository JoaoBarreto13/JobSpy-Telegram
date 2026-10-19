"""
Módulo Extra para Portais de Vagas do Brasil (portais_br).

Suporte nativo aos principais portais brasileiros de empregos:
- Gupy (portal.gupy.io) — Maior ATS corporativo do Brasil
- InfoJobs (infojobs.com.br) — Um dos mais acessados portais de vagas
- Programathor (programathor.com.br) — Especializado em vagas tech/dev
- Trabalha Brasil (trabalhabrasil.com.br) — Alto volume nacional (BNE/SINE)
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from portais_br.gupy import scrape_gupy
from portais_br.infojobs import scrape_infojobs
from portais_br.programathor import scrape_programathor
from portais_br.trabalha_brasil import scrape_trabalha_brasil

logger = logging.getLogger(__name__)

AVAILABLE_BR_SITES = [
    "gupy",
    "infojobs",
    "programathor",
    "trabalha_brasil",
]

BR_SITE_DISPLAY_NAMES = {
    "gupy": "🟢 Gupy",
    "infojobs": "💼 InfoJobs",
    "programathor": "💻 Programathor",
    "trabalha_brasil": "🇧🇷 Trabalha Brasil",
}

SCRAPER_MAPPING = {
    "gupy": scrape_gupy,
    "infojobs": scrape_infojobs,
    "programathor": scrape_programathor,
    "trabalha_brasil": scrape_trabalha_brasil,
}


def scrape_br_jobs(
    site_names: str | Iterable[str] | None = None,
    search_term: str = "",
    location: str = "",
    is_remote: bool = False,
    results_wanted: int = 15,
) -> list[dict[str, Any]]:
    """
    Executa a busca concorrente nos portais brasileiros selecionados.

    :param site_names: Nome do portal ou lista de portais a pesquisar.
    :param search_term: Termo ou cargo pesquisado.
    :param location: Localização / Cidade / Estado.
    :param is_remote: Filtrar apenas vagas remotas / home office.
    :param results_wanted: Quantidade desejada de resultados por portal.
    :return: Lista unificada de vagas.
    """
    if site_names is None:
        target_sites = list(AVAILABLE_BR_SITES)
    elif isinstance(site_names, str):
        target_sites = [site_names.lower()]
    else:
        target_sites = [str(s).lower() for s in site_names]

    # Filtrar apenas os sites que este módulo atende
    active_sites = [s for s in target_sites if s in SCRAPER_MAPPING]

    if not active_sites:
        return []

    all_jobs: list[dict[str, Any]] = []

    def _run_scraper(site: str) -> list[dict[str, Any]]:
        scraper_fn = SCRAPER_MAPPING[site]
        try:
            return scraper_fn(
                search_term=search_term,
                location=location,
                is_remote=is_remote,
                results_wanted=results_wanted,
            )
        except Exception as exc:
            logger.error("Erro ao raspar portal BR '%s': %s", site, exc)
            return []

    with ThreadPoolExecutor(max_workers=len(active_sites)) as executor:
        futures = {executor.submit(_run_scraper, site): site for site in active_sites}
        for future in futures:
            site = futures[future]
            try:
                results = future.result()
                all_jobs.extend(results)
            except Exception as exc:
                logger.error("Falha ao coletar dados do site '%s': %s", site, exc)

    return all_jobs


def scrape_all_jobs(
    site_name: str | list[str] | None = None,
    search_term: str | None = None,
    location: str | None = None,
    is_remote: bool | None = False,
    job_type: str | None = None,
    results_wanted: int | None = 15,
    country_indeed: str | None = "brazil",
    hours_old: int | None = None,
    description_format: str | None = "plain",
    verbose: int | None = 0,
    **kwargs: Any,
) -> Any:
    """
    Ponto de entrada unificado: combina JobSpy (LinkedIn, Indeed, Glassdoor, etc.)
    com o módulo de portais brasileiros (Gupy, InfoJobs, Programathor, Trabalha Brasil).
    Retorna um pandas.DataFrame com todas as vagas combinadas.
    """
    import pandas as pd

    # Importação do JobPost para saber as colunas oficiais
    try:
        from jobspy.model import JobPost

        all_columns = list(JobPost.model_fields.keys())
    except Exception:
        all_columns = [
            "id",
            "site",
            "job_url",
            "job_url_direct",
            "title",
            "company",
            "location",
            "date_posted",
            "job_type",
            "salary_source",
            "interval",
            "min_amount",
            "max_amount",
            "currency",
            "is_remote",
            "description",
        ]

    # Normalizar lista de sites
    if site_name is None:
        requested_sites = None
    elif isinstance(site_name, str):
        requested_sites = [site_name.lower()]
    else:
        requested_sites = [str(s).lower() for s in site_name]

    br_sites: list[str] = []
    jobspy_sites: list[str] = []

    if requested_sites is None:
        br_sites = list(AVAILABLE_BR_SITES)
        # Portais padrão do JobSpy recomendados no Brasil
        jobspy_sites = ["linkedin", "indeed", "glassdoor", "zip_recruiter"]
    else:
        for s in requested_sites:
            if s in AVAILABLE_BR_SITES:
                br_sites.append(s)
            else:
                jobspy_sites.append(s)

    combined_rows: list[dict[str, Any]] = []
    errors: dict[str, Any] = {}
    warnings: dict[str, Any] = {}

    def _fetch_br() -> list[dict[str, Any]]:
        if not br_sites:
            return []
        return scrape_br_jobs(
            site_names=br_sites,
            search_term=search_term or "",
            location=location or "",
            is_remote=bool(is_remote),
            results_wanted=results_wanted or 15,
        )

    def _fetch_jobspy() -> pd.DataFrame:
        if not jobspy_sites:
            return pd.DataFrame(columns=all_columns)
        try:
            import re
            from jobspy import scrape_jobs

            jobspy_loc = location
            if jobspy_loc:
                jobspy_loc = re.sub(r"\bbrasil\b", "Brazil", str(jobspy_loc), flags=re.IGNORECASE)
                if jobspy_loc.strip().lower() in ("brasil", "brazil"):
                    jobspy_loc = "Brazil"

            return scrape_jobs(
                site_name=jobspy_sites,
                search_term=search_term,
                location=jobspy_loc,
                is_remote=is_remote,
                job_type=job_type,
                results_wanted=results_wanted or 15,
                country_indeed=country_indeed or "brazil",
                hours_old=hours_old,
                description_format=description_format,
                verbose=verbose,
                **kwargs,
            )
        except Exception as e:
            logger.error("Erro no JobSpy nativo: %s", e)
            errors["jobspy"] = str(e)
            return pd.DataFrame(columns=all_columns)

    with ThreadPoolExecutor(max_workers=2) as executor:
        br_future = executor.submit(_fetch_br)
        jobspy_future = executor.submit(_fetch_jobspy)

        br_results = br_future.result()
        jobspy_df = jobspy_future.result()

    if hasattr(jobspy_df, "attrs"):
        errors.update(jobspy_df.attrs.get("errors", {}))
        warnings.update(jobspy_df.attrs.get("warnings", {}))

    # Converte jobspy DataFrame em lista de dicts
    if not jobspy_df.empty:
        for _, row in jobspy_df.iterrows():
            combined_rows.append(row.to_dict())

    # Adiciona os resultados dos portais BR
    combined_rows.extend(br_results)

    # Filtro de segurança: Se o usuário especificou busca no Brasil, descarta vagas no exterior
    if location:
        import re
        is_search_in_brazil = bool(re.search(r"\bbra[sz]il\b", str(location), flags=re.IGNORECASE))
        if is_search_in_brazil:
            us_states_exclusive = {
                "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
                "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
                "MI", "MN", "MO", "NE", "NV", "NH", "NJ", "NM", "NY", "NC",
                "ND", "OH", "OK", "OR", "RI", "SD", "TN", "TX", "UT", "VT",
                "VA", "WA", "WV", "WI", "WY",
            }
            filtered_rows: list[dict[str, Any]] = []
            for item in combined_rows:
                loc_val = str(item.get("location") or "").strip()
                loc_lower = loc_val.lower()

                # Se a localização menciona explicitamente USA / Estados Unidos
                if any(kw in loc_lower for kw in ("usa", "united states", "estados unidos", "u.s.")):
                    continue

                # Se termina com sigla de estado exclusivo dos EUA (ex: "Scottsdale, AZ")
                state_match = re.search(r",\s*([A-Za-z]{2})$", loc_val)
                if state_match and state_match.group(1).upper() in us_states_exclusive:
                    continue

                filtered_rows.append(item)
            combined_rows = filtered_rows

    # Cria o DataFrame unificado
    if combined_rows:
        df = pd.DataFrame(combined_rows)
        # Garante que todas as colunas padrão existam
        for col in all_columns:
            if col not in df.columns:
                df[col] = None
        # Reordena colunas com prioridade para as principais
        df = df[all_columns]
        # Ordena por presença de data mais recente se disponível
        df = df.sort_values(by=["site", "date_posted"], ascending=[True, False]).reset_index(
            drop=True
        )
    else:
        df = pd.DataFrame(columns=all_columns)

    df.attrs = {"errors": errors, "warnings": warnings}
    return df
