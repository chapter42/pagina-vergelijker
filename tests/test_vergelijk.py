import re
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vergelijk as vg


def fake_embed(teksten):
    """Bag-of-words met hashing: deterministisch en zonder API."""
    m = np.zeros((len(teksten), 256), dtype=np.float32)
    for i, t in enumerate(teksten):
        for w in re.findall(r"\w+", t.lower()):
            m[i, hash(w) % 256] += 1
    return vg._norm(m)


def html(titel, tekst, ids):
    tegels = "".join(f'<a href="/nl/nl/p/product-{i}/{i}/">Product {i} met een lange titel hier</a>' for i in ids)
    return f"""<html><head><title>{titel}</title><meta name="description" content="{titel} kopen"></head>
    <body><nav><a href="/menu">Menu item een twee drie vier vijf zes zeven acht</a></nav>
    <h1>{titel}</h1><div class="grid">{tegels}</div><p>{tekst}</p>
    <footer><p>Footer tekst die op elke pagina staat een twee drie vier vijf</p></footer></body></html>"""


TEKST_A = ("Een robotmaaier maait je gazon automatisch. Kies een model dat past bij de grootte "
           "van je tuin en let op de maximale hellingshoek.")
TEKST_B = ("Een grasmachine voor je terras of balkon? Lees hoe je planten water geeft "
           "en welke potgrond het beste werkt in de zomer.")
IDS = [9300000100000 + i for i in range(10)]


def test_zelfde_pagina_scoort_1():
    a = vg.uit_html("A", html("Robotmaaiers", TEKST_A, IDS), url="https://x.nl/l/robotmaaiers/1/")
    b = vg.uit_html("B", html("Robotmaaiers", TEKST_A, IDS), url="https://x.nl/l/robotmaaiers/1/")
    r = vg.vergelijk([a, b], fake_embed)[0]
    for k in ["intentie", "tekst", "letterlijk", "product", "totaal"]:
        assert r[k] == pytest.approx(1.0, abs=1e-5), k
    assert r["oordeel"] == "praktisch dezelfde pagina"


def test_verschillende_pagina_scoort_laag():
    a = vg.uit_html("A", html("Robotmaaiers", TEKST_A, IDS))
    b = vg.uit_html("B", html("Potgrond", TEKST_B, [1234567 + i for i in range(10)]))
    r = vg.vergelijk([a, b], fake_embed)[0]
    assert r["product"] == 0 and r["letterlijk"] == 0
    assert r["totaal"] < 0.65
    assert r["oordeel"] == "verschillend genoeg"


def test_boilerplate_en_producten_niet_in_tekst():
    p = vg.uit_html("A", html("Robotmaaiers", TEKST_A, IDS))
    assert p.alineas == [TEKST_A]
    assert p.producten == [str(i) for i in IDS]
    assert p.h1 == "Robotmaaiers" and p.meta == "Robotmaaiers kopen"


def test_markdown_zonder_productkaarten_en_navigatie():
    md = ("[Tuin](https://x/tuin) [Wonen](https://x/wonen) [Koken](https://x/koken)\n\n"
          "[Husqvarna Automower 310 Mark II robotmaaier met app](https://www.bol.com/nl/nl/p/husqvarna/9300000123456/)\n\n"
          "## Robotmaaier kopen\n\n" + TEKST_A)
    assert vg._md_alineas(md, vg.BOL_PRODUCT_RE) == [TEKST_A]


def test_lege_blokken_tellen_niet_mee():
    a = vg.Pagina("A", producten=["1", "2"])
    b = vg.Pagina("B", producten=["1", "2"])
    r = vg.vergelijk([a, b], fake_embed)[0]
    assert r["tekst"] is None and r["intentie"] is None
    assert r["totaal"] == pytest.approx(1.0)


def test_url_verschil_en_maximum():
    a = vg.Pagina("A", url="https://www.bol.com/nl/nl/l/robotmaaiers/21187/4285+75727/")
    b = vg.Pagina("B", url="https://www.bol.com/nl/nl/l/robotmaaiers/21187/4285/")
    r = vg.vergelijk([a, b], fake_embed)[0]
    assert r["alleen_in_a"] == ["75727"] and r["alleen_in_b"] == []
    with pytest.raises(vg.Fout):
        vg.vergelijk([a] * 6, fake_embed)
