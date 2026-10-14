#!/usr/bin/env python3
"""Descarga el feed de noticias y lo guarda como noticias.json (lo ejecuta GitHub Actions)."""
import datetime
import email.utils
import html
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

FEEDS = [
    "https://www.aenverde.es/titulares/feed",
    "https://www.aenverde.es/feed/",
]
MAX_NOTICIAS = 10
SALIDA = "noticias.json"
CARPETA_IMG = "imagenes"   # copia local de las fotos: se sirven desde el mismo sitio que el dashboard
# API de WordPress: de aquí salen la imagen destacada y el extracto de cada noticia
API = ("https://www.aenverde.es/wp-json/wp/v2/posts"
       "?per_page={n}&_embed=wp:featuredmedia")
# Frase que aenverde.es pone al principio de cada extracto
PREFIJO_WHATSAPP = re.compile(r"^\s*\(\s*Tambi.n nos puedes seguir por[^)]*\)\s*", re.I)


def limpiar(valor):
    """Quita etiquetas HTML, entidades, espacios raros y el prefijo de WhatsApp."""
    s = re.sub(r"<[^>]+>", " ", valor or "")
    s = html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return PREFIJO_WHATSAPP.sub("", s).strip()


def id_post(guid):
    m = re.search(r"[?&]p=(\d+)", guid or "")
    return int(m.group(1)) if m else None


def imagen_destacada(post):
    try:
        media = post["_embedded"]["wp:featuredmedia"][0]
        tamanos = media.get("media_details", {}).get("sizes", {})
        for nombre in ("medium_large", "large", "full"):
            if nombre in tamanos and tamanos[nombre].get("source_url"):
                return tamanos[nombre]["source_url"]
        return media.get("source_url", "")
    except (KeyError, IndexError, TypeError):
        return ""


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
        guid = texto(n, "guid", "id")
        salida.append({
            "id": guid or enlace or titulo,
            "titulo": titulo,
            "fecha": d.isoformat() if d else "",
            "enlace": enlace,
            "imagen": "",
            # Extracto del feed; si la API responde, se sustituye por el suyo
            "descripcion": limpiar(texto(n, "description", "summary")),
            "_post": id_post(guid),
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


def guardar_imagen(url, post_id):
    """Descarga la foto a imagenes/ y devuelve su ruta relativa; si falla, devuelve la URL original."""
    if not url:
        return ""
    ext = os.path.splitext(url.split("?")[0])[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ext = ".jpg"
    ruta = f"{CARPETA_IMG}/{post_id}{ext}"
    try:
        if not os.path.exists(ruta):
            os.makedirs(CARPETA_IMG, exist_ok=True)
            datos = descargar(url)
            if len(datos) < 500:
                raise ValueError("imagen vacía")
            with open(ruta, "wb") as f:
                f.write(datos)
        return ruta
    except Exception as e:
        print(f"Aviso: no se pudo copiar {url}: {e}", file=sys.stderr)
        return url


def limpiar_imagenes(items):
    """Borra de imagenes/ las fotos de noticias que ya no están en la lista."""
    usadas = {os.path.basename(i["imagen"]) for i in items if i["imagen"].startswith(CARPETA_IMG + "/")}
    if os.path.isdir(CARPETA_IMG):
        for nombre in os.listdir(CARPETA_IMG):
            if nombre not in usadas:
                os.remove(os.path.join(CARPETA_IMG, nombre))


def enriquecer(items):
    """Añade imagen y descripción desde la API de WordPress. Si falla, no pasa nada."""
    try:
        posts = json.loads(descargar(API.format(n=max(MAX_NOTICIAS * 2, 20))))
        por_id = {p["id"]: p for p in posts}
    except Exception as e:
        print(f"Aviso: sin imágenes (API no disponible): {e}", file=sys.stderr)
        por_id = {}
    for it in items:
        pid = it.pop("_post", None)
        p = por_id.get(pid)
        if not p:
            continue
        it["imagen"] = guardar_imagen(imagen_destacada(p), pid)
        extracto = limpiar(p.get("excerpt", {}).get("rendered", ""))
        if extracto:
            it["descripcion"] = extracto
    return items


def main():
    ultimo_error = None
    for url in FEEDS:
        try:
            items = enriquecer(leer(descargar(url)))
            if items:
                limpiar_imagenes(items)
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
