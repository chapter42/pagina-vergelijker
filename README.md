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
Elke gebruiker vult zijn eigen keys in de sidebar in en betaalt zelf zijn gebruik. Zie [Privacy](#privacy-wat-gebeurt-er-met-je-gegevens) voor wat er met de keys gebeurt.
- **Firecrawl** (ophalen van pagina's): https://www.firecrawl.dev/app/api-keys. Elke pagina kost één scrape; een tweede vergelijking binnen een uur komt uit de cache.
- **Google Gemini** (embeddings, model `gemini-embedding-001`): https://aistudio.google.com/apikey. Er is een gratis tier.

**Lokaal zonder invullen:** zet je keys in `.streamlit/secrets.toml` (voorbeeld: `.streamlit/secrets.toml.example`; het bestand staat in `.gitignore`). De velden tonen dan "✓ uit secrets.toml"; een ingevulde key gaat altijd voor. Zet je dezelfde secrets op Streamlit Cloud, dan gebruikt iedereen die de app opent jouw keys.

Wordt een pagina geblokkeerd door botbescherming? Sla de pagina op in je browser (Cmd/Ctrl+S) en upload het HTML-bestand in de app.

## Privacy: wat gebeurt er met je gegevens
- **Je API-keys** gaan naar de server waarop de app draait (bij de online versie: Streamlit Community Cloud). Ze staan alleen in het geheugen van jouw sessie en verdwijnen als je de tab sluit. De app slaat ze niet op, logt ze niet en gebruikt ze niet als cachesleutel. Je vertrouwt wel de beheerder van de app en Streamlit, zoals bij elke webtool waarin je een key plakt. Wil je dat niet, draai de app dan lokaal; de code is openbaar.
- **De URL's en paginatekst** gaan naar Firecrawl (ophalen) en naar Google Gemini (embeddings). Daar gelden hun voorwaarden.
- **De cache wordt gedeeld.** Opgehaalde pagina's en embeddings blijven een uur bewaard, voor alle gebruikers samen. Vergelijken twee mensen dezelfde URL, dan kost dat de tweede geen Firecrawl-credits. Er staan geen keys in de cache. Een ander kan alleen aan de snelheid merken dat een URL net is opgehaald.
- **Resultaten en geüploade HTML** blijven in jouw sessie en worden niet opgeslagen. Andere gebruikers zien ze niet.

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
3. Stel géén secrets in: dan vullen gebruikers hun eigen keys in en betalen ze hun eigen gebruik.
4. Streamlit voegt een alleen-lezen deploy key toe aan de repo (*Settings → Deploy keys*). Die is nodig om bij elke push naar `main` opnieuw te deployen. Verwijder hem als je de app op Streamlit weghaalt.

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
