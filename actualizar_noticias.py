#!/usr/bin/env python3
"""Descarga el feed de noticias y lo guarda como noticias.json (lo ejecuta GitHub Actions)."""
import datetime
import email.utils
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET

FEEDS = [
    "https://www.aenverde.es/titulares/feed",
    "https://www.aenverde.es/feed/",
]
MAX_NOTICIAS = 10
SALIDA = "noticias.json"


def local(etiqueta):
    return etiqueta.rsplit("}", 1)[-1]


def hijo(nodo, *nombres):
    for h in nodo:
        if local(h.tag) in nombres:
            return h
    return None


def texto(nodo, *nombres):
    h = hijo(nodo, *nombres)
    return (h.text or "").strip() if h is not None and h.text else ""


def fecha(valor):
    if not valor:
        return None
    try:
        d = email.utils.parsedate_to_datetime(valor)
    except Exception:
        try:
            d = datetime.datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return d.astimezone(datetime.timezone.utc)


def leer(datos):
    raiz = ET.fromstring(datos)
    salida = []
    for n in raiz.iter():
        if local(n.tag) not in ("item", "entry"):
            continue
        titulo = texto(n, "title")
        if not titulo:
            continue
        enlace_el = hijo(n, "link")
        enlace = ""
        if enlace_el is not None:
            enlace = (enlace_el.get("href") or enlace_el.text or "").strip()
        d = fecha(texto(n, "pubDate", "published", "updated", "date"))
        salida.append({
            "id": texto(n, "guid", "id") or enlace or titulo,
            "titulo": titulo,
            "fecha": d.isoformat() if d else "",
            "enlace": enlace,
        })
    salida.sort(key=lambda x: x["fecha"], reverse=True)
    return salida[:MAX_NOTICIAS]


def descargar(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def main():
    ultimo_error = None
    for url in FEEDS:
        try:
            items = leer(descargar(url))
            if items:
                with open(SALIDA, "w", encoding="utf-8") as f:
                    json.dump({"items": items}, f, ensure_ascii=False, indent=1)
                    f.write("\n")
                print(f"{len(items)} noticias guardadas desde {url}")
                return 0
            ultimo_error = f"{url}: sin noticias en la respuesta"
        except Exception as e:
            ultimo_error = f"{url}: {e}"
    print("No se pudo leer el feed -> " + str(ultimo_error), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
