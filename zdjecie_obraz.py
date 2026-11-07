"""Pobieranie i zmniejszanie zdjęć produktów (wspólne dla nowe_pc.py i nowe_monitory.py).

Dlaczego osobny moduł: w środowisku Rutyny (chmura) systemowy Pillow jest uszkodzony —
`import PIL` przechodzi, ale `from PIL import Image` kończy się „cannot import name '_imaging'".
Dawne zabezpieczenie `python3 -c "import PIL" || pip install` tego nie wykrywało, więc dopisywanie
produktów po cichu pomijało KAŻDY nowy produkt (zdjęcie jest wymagane) i kończyło się kodem 0.
Teraz moduł sprawdza, czy Pillow naprawdę koduje WebP, a jeśli nie — instaluje własną kopię do
katalogu tymczasowego i ją ustawia przed systemową.
"""
import base64, importlib, io, os, subprocess, sys, tempfile, urllib.parse, urllib.request

from ocena_pc import BrakDanych
import zbieraj_ceny as z

MAX_PX, JAKOSC = 400, 62   # WebP: ok. 9 KB na zdjęcie (JPEG 480 px miał 26 KB), limit strony to 16 MB
_IMAGE = None


class BladSrodowiska(RuntimeError):
    """Problem środowiska (Pillow, sieć), a nie cecha produktu — nie wolno go zapamiętywać jako odrzucenia."""


def _sprawdz(Image):
    b = io.BytesIO()
    Image.new("RGB", (4, 4)).save(b, "WEBP", quality=JAKOSC, method=6)
    if not b.getvalue():
        raise RuntimeError("Pillow nie zakodował WebP")
    return Image


def pil_image():
    """Działający Pillow.Image — albo systemowy, albo własna kopia z pip --target."""
    global _IMAGE
    if _IMAGE is not None:
        return _IMAGE
    try:
        from PIL import Image
        _IMAGE = _sprawdz(Image)
        return _IMAGE
    except Exception as e:
        pierwotny = f"{type(e).__name__}: {e}"
    katalog = os.path.join(tempfile.gettempdir(), "pillow_pkg")
    print(f"  Pillow systemowy nie działa ({pierwotny[:120]}) — instaluję własną kopię do {katalog}",
          file=sys.stderr)
    for dodatkowe in ([], ["--break-system-packages"]):
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                            "--target", katalog, *dodatkowe, "pillow"],
                           capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            break
    else:
        raise BladSrodowiska(f"Pillow nie działa ({pierwotny[:100]}) i nie dało się go zainstalować: {r.stderr[-200:]}")
    for m in [m for m in list(sys.modules) if m == "PIL" or m.startswith("PIL.")]:
        del sys.modules[m]
    importlib.invalidate_caches()
    sys.path.insert(0, katalog)
    try:
        from PIL import Image
        _IMAGE = _sprawdz(Image)
    except Exception as e:
        raise BladSrodowiska(f"Pillow nadal nie działa po instalacji: {type(e).__name__}: {e}")
    return _IMAGE


def zdjecie_data_uri(url_zdjecia):
    """Pobiera zdjęcie (z poszanowaniem robots.txt i tempa), zmniejsza do 400 px WebP → data URI."""
    Image = pil_image()
    if not z.REGULAMIN.wolno(url_zdjecia):
        raise BrakDanych("robots.txt nie pozwala pobrać zdjęcia")
    z.TEMPO.czekaj(urllib.parse.urlparse(url_zdjecia).netloc)
    r = urllib.request.Request(url_zdjecia, headers={"User-Agent": getattr(z, "UA", "Mozilla/5.0")})
    surowe = urllib.request.urlopen(r, timeout=30).read()
    im = Image.open(io.BytesIO(surowe))
    if im.mode in ("RGBA", "LA", "P"):
        tlo = Image.new("RGB", im.size, (255, 255, 255))
        im = im.convert("RGBA")
        tlo.paste(im, mask=im.split()[-1])
        im = tlo
    else:
        im = im.convert("RGB")
    im.thumbnail((MAX_PX, MAX_PX))
    b = io.BytesIO()
    im.save(b, "WEBP", quality=JAKOSC, method=6)
    return "data:image/webp;base64," + base64.b64encode(b.getvalue()).decode()
