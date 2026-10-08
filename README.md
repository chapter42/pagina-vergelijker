# Pagina-vergelijker

Hoeveel lijken 2 tot 5 webpagina's echt op elkaar? Deze Streamlit-app vergelijkt pagina's **per blok** in plaats van in één score. Zo telt gedeelde navigatie, footer en template niet mee.

| Blok | Hoe | Standaardgewicht |
|---|---|---|
| **Productset** | Jaccard op product-ID's uit productlinks (regex aanpasbaar; standaard bol.com `/p/<naam>/<id>`) | 0,4 |
| **Tekst (betekenis)** | Gemini-embeddings per alinea: documentgelijkenis + beste match per alinea | 0,3 |
| **Intentie** | Gemini-embedding van title + H1 + meta description | 0,2 |
| **Letterlijke kopie** | Jaccard op reeksen van 5 woorden | 0,1 |

- Blokken die op beide pagina's leeg zijn tellen niet mee; de gewichten worden herschaald.
- Per paar zie je de meest gelijke alinea's naast elkaar, hoeveel producten gedeeld zijn en het verschil in URL-onderdelen (handig bij filterpagina's).

**Oordeel** (drempels aanpasbaar):

| Totaal | Oordeel |
|---|---|
| ≥ 85% | praktisch dezelfde pagina |
| 65–85% | sterk overlappend: onderscheid aanbrengen |
| < 65% | verschillend genoeg |

> Gemini-cosines liggen ook voor ongerelateerde Nederlandse tekst rond 0,70. De app schaalt [0,70–1] naar [0–100%], zodat 0% echt "niets gemeen" betekent (`EMB_VLOER` in `vergelijk.py`).

## Keys
Elke gebruiker vult zijn eigen keys in de sidebar in. Ze blijven alleen in de browsersessie en worden niet opgeslagen of gelogd.
- **Firecrawl** (ophalen van pagina's): https://www.firecrawl.dev/app/api-keys. Elke pagina kost één scrape; een tweede vergelijking binnen een uur komt uit de cache.
- **Google Gemini** (embeddings, model `gemini-embedding-001`): https://aistudio.google.com/apikey. Er is een gratis tier.

**Lokaal zonder invullen:** zet je keys in `.streamlit/secrets.toml` (voorbeeld: `.streamlit/secrets.toml.example`; het bestand staat in `.gitignore`). De velden tonen dan "✓ uit secrets.toml"; een ingevulde key gaat altijd voor. Zet je dezelfde secrets op Streamlit Cloud, dan gebruikt iedereen die de app opent jouw keys.

Wordt een pagina geblokkeerd door botbescherming? Sla de pagina op in je browser (Cmd/Ctrl+S) en upload het HTML-bestand in de app.

## Lokaal draaien
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

Tests (zonder API-calls):
```bash
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q
```

## Online zetten (Streamlit Community Cloud)
1. Push deze repo naar GitHub.
2. Ga naar https://share.streamlit.io → *Create app* → kies de repo, branch `main` en bestand `app.py`.
3. Je hoeft geen secrets in te stellen; gebruikers vullen hun eigen keys in.

## Als script
`vergelijk.py` bevat geen Streamlit-code:
```python
import vergelijk as vg
data = vg.scrape(url, FIRECRAWL_KEY)
p = vg.uit_firecrawl("A", url, data)
paren = vg.vergelijk([p1, p2], vg.gemini_embedder(GEMINI_KEY))
```

## Licentie
MIT, zie [LICENSE](LICENSE).
