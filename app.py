"""Pagina-vergelijker: hoe gelijk zijn 2-5 webpagina's echt?

Start lokaal met:  streamlit run app.py
"""
from __future__ import annotations

import json
from urllib.parse import urlparse

import altair as alt
import pandas as pd
import streamlit as st

import vergelijk as vg

st.set_page_config(page_title="Pagina-vergelijker", page_icon="🔍", layout="wide")

BLOKKEN = {"product": "Productset", "tekst": "Tekst (betekenis)",
           "intentie": "Intentie (title/H1/meta)", "letterlijk": "Letterlijke kopie"}


@st.cache_data(ttl=3600, show_spinner=False, max_entries=200)
def scrape_cached(url: str, land: str, _key: str) -> dict:
    # _key hoort niet bij de cachesleutel en wordt nergens opgeslagen
    return vg.scrape(url, _key, land)


@st.cache_data(ttl=3600, show_spinner=False, max_entries=200)
def embed_cached(teksten: tuple[str, ...], _key: str):
    return vg.gemini_embedder(_key)(list(teksten))


def secret(naam: str) -> str:
    """Key uit .streamlit/secrets.toml, of leeg als er geen secrets-bestand is."""
    try:
        return str(st.secrets.get(naam, "") or "")
    except Exception:  # geen secrets.toml
        return ""


def kort(url: str, n: int = 45) -> str:
    p = urlparse(url)
    delen = [d for d in p.path.split("/") if d]
    s = "/".join(delen[-3:]) or p.netloc or url  # bv. robotmaaiers/21187/4285
    return s if len(s) <= n else "…" + s[-(n - 1):]


def pct(x) -> str:
    return "–" if x is None else f"{x:.0%}"


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("API-keys")
    st.caption("Je keys blijven alleen in deze browsersessie. Ze worden niet opgeslagen of gelogd.")
    # Staat een key in secrets.toml, dan is invullen niet nodig; een ingevulde key gaat voor.
    fc_secret, gm_secret = secret("FIRECRAWL_API_KEY"), secret("GEMINI_API_KEY")
    fc_key = st.text_input("Firecrawl API-key", type="password", key="fc_key",
                           placeholder="✓ uit secrets.toml" if fc_secret else "",
                           help="Haal een key op firecrawl.dev → Dashboard → API Keys.") or fc_secret
    gm_key = st.text_input("Google Gemini API-key", type="password", key="gm_key",
                           placeholder="✓ uit secrets.toml" if gm_secret else "",
                           help="Haal een gratis key op aistudio.google.com → Get API key.") or gm_secret
    st.markdown("[Firecrawl-key halen](https://www.firecrawl.dev/app/api-keys) · "
                "[Gemini-key halen](https://aistudio.google.com/apikey)")

    with st.expander("Geavanceerd"):
        land = st.text_input("Ophalen vanuit land", "NL", max_chars=2,
                             help="Landcode voor Firecrawl. Sites als bol blokkeren buitenlandse bezoekers.")
        product_re = st.text_input(
            "Regex voor product-ID's in links", vg.BOL_PRODUCT_RE,
            help="De eerste groep is het ID. Standaard: bol-productpagina's (/p/<naam>/<id>).")
        st.caption("Gewichten in de totaalscore")
        gewichten = {k: st.slider(BLOKKEN[k], 0.0, 1.0, v, 0.05) for k, v in vg.GEWICHTEN.items()}
        laag, hoog = st.slider("Drempels: overlappend / dezelfde", 0.0, 1.0, vg.DREMPELS, 0.05)

# ---------------------------------------------------------------- invoer
st.title("🔍 Pagina-vergelijker")
st.write(
    "Hoeveel lijken 2 tot 5 pagina's echt op elkaar? De app vergelijkt elk blok apart: "
    "**productset**, **tekst** (betekenis via Gemini-embeddings), **intentie** (title, H1, meta) "
    "en **letterlijke kopie**. Zo telt gedeelde navigatie en footer niet mee.")

urls_tekst = st.text_area("URL's (één per regel)", height=140,
                          placeholder="https://www.bol.com/nl/nl/l/robotmaaiers/21187/\n"
                                      "https://www.bol.com/nl/nl/l/robotmaaiers/21187/4285/")
with st.expander("Pagina geblokkeerd? Upload opgeslagen HTML"):
    st.caption("Open de pagina in je browser, sla hem op (Cmd/Ctrl+S, 'Alleen HTML') en upload hem hier. "
               "Elk bestand telt als een extra pagina.")
    uploads = st.file_uploader("HTML-bestanden", type=["html", "htm"], accept_multiple_files=True)

urls = list(dict.fromkeys(u.strip() for u in urls_tekst.splitlines() if u.strip()))
aantal = len(urls) + len(uploads or [])

if st.button("Vergelijk", type="primary", disabled=aantal < 2):
    fouten = []
    if aantal > vg.MAX_PAGINAS:
        fouten.append(f"Maximaal {vg.MAX_PAGINAS} pagina's; je gaf er {aantal} op.")
    if urls and not fc_key:
        fouten.append("Vul je Firecrawl API-key in (links).")
    if not gm_key:
        fouten.append("Vul je Gemini API-key in (links).")
    if bad := [u for u in urls if not u.startswith(("http://", "https://"))]:
        fouten.append("Geen geldige URL: " + ", ".join(bad))
    for f in fouten:
        st.error(f)

    if not fouten:
        try:
            paginas = []
            with st.status("Bezig met vergelijken…", expanded=True) as status:
                for n, url in enumerate(urls, 1):
                    st.write(f"Ophalen: {url}")
                    data = scrape_cached(url, land, fc_key)
                    paginas.append(vg.uit_firecrawl(f"P{n} · {kort(url)}", url, data, product_re))
                for up in uploads or []:
                    n = len(paginas) + 1
                    html = up.getvalue().decode("utf-8", errors="replace")
                    paginas.append(vg.uit_html(f"P{n} · {kort(up.name)}", html, product_re))
                st.write("Embeddings maken en scores berekenen…")
                resultaat = vg.vergelijk(paginas, lambda t: embed_cached(tuple(t), gm_key),
                                         gewichten, (laag, hoog))
                status.update(label="Klaar", state="complete", expanded=False)
            st.session_state["res"] = {"paginas": paginas, "paren": resultaat}
        except vg.Fout as e:
            st.error(str(e))

# ---------------------------------------------------------------- resultaat
res = st.session_state.get("res")
if res:
    paginas, paren = res["paginas"], res["paren"]

    st.subheader("Pagina's")
    st.dataframe(pd.DataFrame([{
        "Pagina": p.label, "URL": p.url or "(upload)", "Title": p.title, "H1": p.h1,
        "Tekstalinea's": len(p.alineas), "Producten": len(p.producten)} for p in paginas]),
        hide_index=True, width="stretch",
        column_config={"URL": st.column_config.LinkColumn()})
    leeg = [p.label for p in paginas if not p.alineas and not p.producten]
    if leeg:
        st.warning("Weinig inhoud gevonden voor: " + ", ".join(leeg)
                   + ". Controleer of de pagina goed is opgehaald.")

    st.subheader("Totaalscore per paar")
    cellen = [{"x": p.label, "y": p.label, "score": 1.0} for p in paginas]
    for r in paren:
        if r["totaal"] is not None:
            cellen += [{"x": r["a"], "y": r["b"], "score": r["totaal"]},
                       {"x": r["b"], "y": r["a"], "score": r["totaal"]}]
    df = pd.DataFrame(cellen)
    volgorde = [p.label for p in paginas]
    basis = alt.Chart(df).encode(x=alt.X("x:N", sort=volgorde, title=None),
                                 y=alt.Y("y:N", sort=volgorde, title=None))
    heat = basis.mark_rect().encode(
        color=alt.Color("score:Q", scale=alt.Scale(domain=[0, 1], scheme="orangered"), legend=None),
        tooltip=["x", "y", alt.Tooltip("score:Q", format=".0%")])
    tekst = basis.mark_text(fontSize=14).encode(
        text=alt.Text("score:Q", format=".0%"),
        color=alt.condition("datum.score > 0.6", alt.value("white"), alt.value("black")))
    st.altair_chart((heat + tekst).properties(height=90 * len(paginas)), width="stretch")

    tabel = pd.DataFrame([{
        "Pagina A": r["a"], "Pagina B": r["b"], "Totaal": r["totaal"],
        **{BLOKKEN[k]: r[k] for k in BLOKKEN},
        "Producten gedeeld": f'{r["producten_gedeeld"]} van {min(r["producten_a"], r["producten_b"])}'
        if r["producten_a"] and r["producten_b"] else "–",
        "Oordeel": r["oordeel"]} for r in sorted(paren, key=lambda r: -(r["totaal"] or 0))])
    pct_kol = {k: st.column_config.ProgressColumn(k, min_value=0, max_value=1, format="percent")
               for k in ["Totaal", *BLOKKEN.values()]}
    st.dataframe(tabel, hide_index=True, width="stretch", column_config=pct_kol)

    st.subheader("Details per paar")
    for r in sorted(paren, key=lambda r: -(r["totaal"] or 0)):
        with st.expander(f'{r["a"]}  ↔  {r["b"]}  —  {pct(r["totaal"])}, {r["oordeel"]}'):
            c = st.columns(4)
            for col, k in zip(c, BLOKKEN):
                col.metric(BLOKKEN[k], pct(r[k]))
            if r["producten_a"] and r["producten_b"]:
                st.write(f'**Producten:** {r["producten_gedeeld"]} gedeeld '
                         f'({r["producten_a"]} op A, {r["producten_b"]} op B).')
            if r["alleen_in_a"] or r["alleen_in_b"]:
                st.write(f'**URL-verschil:** alleen in A: `{", ".join(r["alleen_in_a"]) or "–"}` · '
                         f'alleen in B: `{", ".join(r["alleen_in_b"]) or "–"}`')
            if r["top_alineas"]:
                st.write("**Meest gelijke alinea's**")
                for t in r["top_alineas"]:
                    a, b = st.columns(2)
                    a.info(t["a"])
                    b.info(t["b"])
                    st.caption(f'Gelijkenis {t["score"]:.0%}')
            else:
                st.caption("Geen tekstalinea's om te vergelijken.")

    export = [{k: v for k, v in r.items()} for r in paren]
    d1, d2 = st.columns(2)
    d1.download_button("Download JSON", json.dumps(export, ensure_ascii=False, indent=2),
                       "vergelijking.json", "application/json")
    d2.download_button("Download CSV", tabel.to_csv(index=False).encode("utf-8"),
                       "vergelijking.csv", "text/csv")

st.divider()
st.caption("Oordeel: ≥ drempel 'dezelfde' = praktisch dezelfde pagina · tussen de drempels = "
           "onderscheid aanbrengen · daaronder = verschillend genoeg. Blokken zonder inhoud op beide "
           "pagina's tellen niet mee.")
