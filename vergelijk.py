"""Vergelijk de inhoud van 2-5 webpagina's, per blok in plaats van in één score.

Blokken: intentie (title/H1/meta), redactionele tekst, letterlijke kopie,
productset (ID's uit productlinks) en het verschil in URL-onderdelen.
Geen Streamlit-code hier, zodat het ook als los script of in tests werkt.
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import parse_qsl, urlparse

import numpy as np
import requests
from bs4 import BeautifulSoup

FIRECRAWL_URL = "https://api.firecrawl.dev/v2/scrape"
GEMINI_MODEL = "gemini-embedding-001"
BOL_PRODUCT_RE = r"/p/[^/?#]+/(\d{6,})"

GEWICHTEN = {"product": 0.4, "tekst": 0.3, "intentie": 0.2, "letterlijk": 0.1}
DREMPELS = (0.65, 0.85)
MAX_PAGINAS = 5
MAX_ALINEAS = 150
MIN_WOORDEN = 8
# Gemini-cosines liggen ook voor ongerelateerde Nederlandse tekst rond 0,70.
# We schalen [EMB_VLOER, 1] naar [0, 1], zodat 0% echt "niets gemeen" betekent.
EMB_VLOER = 0.70

# Tekens dat Firecrawl op een botmuur of lege pagina stuitte
BOTMUUR = re.compile(r"captcha|access denied|are you a robot|verify you are human|"
                     r"ben je een robot|toegang geweigerd|just a moment", re.I)

Embedder = Callable[[list[str]], np.ndarray]


class Fout(Exception):
    """Fout met een melding in gewone taal, voor de gebruiker."""


@dataclass
class Pagina:
    label: str
    url: str = ""
    title: str = ""
    meta: str = ""
    h1: str = ""
    alineas: list[str] = field(default_factory=list)
    producten: list[str] = field(default_factory=list)  # volgorde zoals op de pagina

    @property
    def intentie(self) -> str:
        return " | ".join(x for x in (self.title, self.h1, self.meta) if x)

    @property
    def tekst(self) -> str:
        return "\n".join(self.alineas)


# ---------------------------------------------------------------- ophalen

def scrape(url: str, key: str, timeout: int = 120) -> dict:
    """Haal een pagina op via Firecrawl. Geeft {markdown, html, rawHtml, metadata}."""
    if not key:
        raise Fout("Vul eerst je Firecrawl API-key in.")
    try:
        r = requests.post(
            FIRECRAWL_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={"url": url, "formats": ["markdown", "html", "rawHtml"],
                  "onlyMainContent": True, "timeout": timeout * 1000},
            timeout=timeout + 15,
        )
    except requests.RequestException as e:
        raise Fout(f"Firecrawl is niet bereikbaar ({e.__class__.__name__}).") from e
    if r.status_code == 401:
        raise Fout("Je Firecrawl API-key klopt niet.")
    if r.status_code == 402:
        raise Fout("Je Firecrawl-tegoed is op.")
    if r.status_code == 429:
        raise Fout("Firecrawl: te veel verzoeken tegelijk. Probeer het over een minuut opnieuw.")
    if r.status_code >= 400:
        raise Fout(f"Firecrawl gaf fout {r.status_code} voor {url}: {r.text[:200]}")
    data = (r.json() or {}).get("data") or {}
    md = data.get("markdown") or ""
    status = (data.get("metadata") or {}).get("statusCode")
    if status and int(status) >= 400:
        raise Fout(f"De pagina gaf status {status}: {url}")
    if len(md) < 200 or BOTMUUR.search(md[:3000]):
        raise Fout(f"Geen bruikbare inhoud voor {url}; waarschijnlijk een botmuur. "
                   "Sla de pagina op in je browser en upload het HTML-bestand.")
    return data


# ---------------------------------------------------------------- blokken

def _schoon(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def product_ids(html: str, regex: str) -> list[str]:
    """Unieke product-ID's in de volgorde waarin ze op de pagina staan."""
    pat = re.compile(regex)
    gezien: dict[str, None] = {}
    for href in re.findall(r'href="([^"]+)"', html or ""):
        m = pat.search(href)
        if m:
            gezien.setdefault(m.group(1) if m.groups() else m.group(0), None)
    return list(gezien)


def _md_alineas(md: str, product_re: str) -> list[str]:
    """Tekstalinea's uit markdown, zonder productkaarten, menu's en linklijsten."""
    pat = re.compile(product_re)
    uit = []
    for blok in re.split(r"\n\s*\n", md):
        regels = []
        for regel in blok.splitlines():
            links = re.findall(r"\[([^\]]*)\]\(([^)]*)\)", regel)
            if any(pat.search(u) for _, u in links):
                continue  # productkaart
            regel = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", regel)          # afbeeldingen
            zonder = re.sub(r"\[([^\]]*)\]\([^)]*\)", "", regel)
            if links and len(_schoon(zonder)) < 0.5 * len(_schoon(regel)):
                continue  # vooral links: navigatie
            regel = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", regel)
            regel = re.sub(r"^[#>*\-\s\d.|]+", "", regel).replace("**", "").replace("|", " ")
            if regel.strip():
                regels.append(regel)
        tekst = _schoon(" ".join(regels))
        if len(tekst.split()) >= MIN_WOORDEN and "€" not in tekst[:40]:
            uit.append(tekst)
    return _uniek(uit)[:MAX_ALINEAS]


def _html_alineas(soup: BeautifulSoup, product_re: str) -> list[str]:
    """Fallback voor geüploade HTML: tekstblokken zonder boilerplate en productkaarten."""
    pat = re.compile(product_re)
    for t in soup(["script", "style", "noscript", "svg", "header", "nav", "footer", "form", "iframe"]):
        t.decompose()
    for a in soup.find_all("a", href=True):
        if pat.search(a["href"]):
            a.decompose()
    uit = []
    for el in soup.find_all(["p", "li", "h2", "h3", "h4", "dt", "dd", "td", "summary"]):
        if el.find(["p", "li", "div"]):
            continue  # alleen bladen, anders dubbel
        tekst = _schoon(el.get_text(" "))
        if len(tekst.split()) >= MIN_WOORDEN:
            uit.append(tekst)
    return _uniek(uit)[:MAX_ALINEAS]


def _uniek(xs: list[str]) -> list[str]:
    return list(dict.fromkeys(xs))


def _kop(soup: BeautifulSoup) -> tuple[str, str, str]:
    title = _schoon(soup.title.get_text()) if soup.title else ""
    meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    h1 = soup.find("h1")
    return title, _schoon(meta.get("content", "")) if meta else "", _schoon(h1.get_text(" ")) if h1 else ""


def uit_firecrawl(label: str, url: str, data: dict, product_re: str = BOL_PRODUCT_RE) -> Pagina:
    raw = data.get("rawHtml") or data.get("html") or ""
    title, meta, h1 = _kop(BeautifulSoup(raw, "html.parser"))
    md_meta = data.get("metadata") or {}
    producten = product_ids(data.get("html") or "", product_re) or product_ids(raw, product_re)
    return Pagina(label=label, url=url,
                  title=title or _schoon(md_meta.get("title", "")),
                  meta=meta or _schoon(md_meta.get("description", "")),
                  h1=h1, alineas=_md_alineas(data.get("markdown") or "", product_re),
                  producten=producten)


def uit_html(label: str, html: str, product_re: str = BOL_PRODUCT_RE, url: str = "") -> Pagina:
    soup = BeautifulSoup(html, "html.parser")
    title, meta, h1 = _kop(soup)
    if not url:
        can = soup.find("link", rel="canonical") or soup.find("meta", property="og:url")
        url = (can.get("href") or can.get("content") or "") if can else ""
    producten = product_ids(html, product_re)
    return Pagina(label=label, url=url, title=title, meta=meta, h1=h1,
                  alineas=_html_alineas(soup, product_re), producten=producten)


# ---------------------------------------------------------------- embeddings

def gemini_embedder(key: str, dim: int = 768) -> Embedder:
    """Embedder op Gemini; batches van 100, vectoren genormaliseerd."""
    if not key:
        raise Fout("Vul eerst je Gemini API-key in.")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)

    def embed(teksten: list[str]) -> np.ndarray:
        vecs = []
        for i in range(0, len(teksten), 100):
            try:
                res = client.models.embed_content(
                    model=GEMINI_MODEL, contents=teksten[i:i + 100],
                    config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY",
                                                    output_dimensionality=dim))
            except Exception as e:  # SDK gooit verschillende fouttypes
                msg = str(e)
                if "API_KEY_INVALID" in msg or "API key not valid" in msg:
                    raise Fout("Je Gemini API-key klopt niet.") from e
                if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                    raise Fout("Gemini: limiet bereikt. Probeer het over een minuut opnieuw.") from e
                raise Fout(f"Gemini gaf een fout: {msg[:200]}") from e
            vecs.extend(e.values for e in res.embeddings)
        return _norm(np.array(vecs, dtype=np.float32))

    return embed


def _schaal(cos):
    return np.clip((cos - EMB_VLOER) / (1 - EMB_VLOER), 0, 1)


def _norm(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(n == 0, 1, n)


# ---------------------------------------------------------------- scores

def shingles(tekst: str, n: int = 5) -> set[str]:
    w = re.findall(r"\w+", tekst.lower())
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def jaccard(a: set, b: set) -> float | None:
    if not a and not b:
        return None
    return len(a & b) / len(a | b)


def url_delen(url: str) -> set[str]:
    p = urlparse(url)
    delen = {d for d in re.split(r"[/+]", p.path) if d}
    delen |= {f"{k}={v}" for k, v in parse_qsl(p.query)}
    return delen


def oordeel(score: float | None, drempels: tuple[float, float] = DREMPELS) -> str:
    if score is None:
        return "geen inhoud om te vergelijken"
    if score >= drempels[1]:
        return "praktisch dezelfde pagina"
    if score >= drempels[0]:
        return "sterk overlappend: onderscheid aanbrengen"
    return "verschillend genoeg"


def vergelijk(paginas: list[Pagina], embed: Embedder, gewichten: dict | None = None,
              drempels: tuple[float, float] = DREMPELS) -> list[dict]:
    """Alle paren vergelijken. Eén embedding-call voor alle teksten samen."""
    if not 2 <= len(paginas) <= MAX_PAGINAS:
        raise Fout(f"Geef 2 tot {MAX_PAGINAS} pagina's op.")
    gewichten = gewichten or GEWICHTEN

    teksten, plek = [], {}
    for i, p in enumerate(paginas):
        if p.intentie:
            plek[(i, "int")] = len(teksten)
            teksten.append(p.intentie)
        plek[(i, "al")] = (len(teksten), len(teksten) + len(p.alineas))
        teksten.extend(p.alineas)
    vec = embed(teksten) if teksten else np.zeros((0, 1))

    def alinea_vec(i):
        a, b = plek[(i, "al")]
        return vec[a:b]

    uit = []
    for i, j in itertools.combinations(range(len(paginas)), 2):
        A, B = paginas[i], paginas[j]
        r: dict = {"a": A.label, "b": B.label, "url_a": A.url, "url_b": B.url}

        # intentie
        r["intentie"] = (float(_schaal(vec[plek[(i, "int")]] @ vec[plek[(j, "int")]]))
                         if (i, "int") in plek and (j, "int") in plek else None)

        # tekst: gemiddelde van documentvector-cosine en zachte alinea-overlap
        va, vb = alinea_vec(i), alinea_vec(j)
        if len(va) and len(vb):
            sim = _schaal(va @ vb.T)
            doc = float(_schaal((_norm(va.mean(0, keepdims=True)) @ _norm(vb.mean(0, keepdims=True)).T)[0, 0]))
            zacht = float((sim.max(1).mean() + sim.max(0).mean()) / 2)
            r["tekst"] = (doc + zacht) / 2
            r["tekst_doc"], r["tekst_alinea"] = doc, zacht
            r["top_alineas"] = _top_paren(sim, A.alineas, B.alineas)
        else:
            r["tekst"] = None
            r["top_alineas"] = []

        r["letterlijk"] = jaccard(shingles(A.tekst), shingles(B.tekst))

        pa, pb = set(A.producten), set(B.producten)
        r["product"] = jaccard(pa, pb)
        r["producten_gedeeld"], r["producten_a"], r["producten_b"] = len(pa & pb), len(pa), len(pb)

        ua, ub = url_delen(A.url), url_delen(B.url)
        r["alleen_in_a"], r["alleen_in_b"] = sorted(ua - ub), sorted(ub - ua)

        r["totaal"] = _gewogen(r, gewichten)
        r["oordeel"] = oordeel(r["totaal"], drempels)
        uit.append(r)
    return uit


def _gewogen(r: dict, gewichten: dict) -> float | None:
    """Gewogen gemiddelde; lege blokken tellen niet mee, de rest wordt herschaald."""
    paren = [(gewichten[k], r[k]) for k in gewichten if r.get(k) is not None and gewichten[k] > 0]
    tot = sum(g for g, _ in paren)
    return sum(g * v for g, v in paren) / tot if tot else None


def _top_paren(sim: np.ndarray, a: list[str], b: list[str], n: int = 3) -> list[dict]:
    """De n meest gelijke alineaparen, elke alinea hooguit één keer."""
    uit, gebruikt_a, gebruikt_b = [], set(), set()
    for k in np.argsort(sim, axis=None)[::-1]:
        i, j = divmod(int(k), sim.shape[1])
        if i in gebruikt_a or j in gebruikt_b:
            continue
        uit.append({"score": float(sim[i, j]), "a": a[i], "b": b[j]})
        gebruikt_a.add(i)
        gebruikt_b.add(j)
        if len(uit) == n:
            break
    return uit
