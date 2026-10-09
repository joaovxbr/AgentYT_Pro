#!/usr/bin/env python3
"""
mureka_dl.py — Baixa músicas públicas do Mureka via share_key e salva o MP3.

Fluxo (reversado do front em 2026-09):
1) GET https://www.mureka.ai/api/pgc/song/detail?share_key=<SID>
   -> data.song: title, duration_milliseconds, mp3_url (path relativo cos-prod/...)
2) GET https://static-cos.mureka.ai/<mp3_url> -> MP3 direto, sem cripto.

Uso:
    python mureka_dl.py <song-detail-url-ou-share_key> [-o saida.mp3] [--dir ./musicas]

Ex:
    python mureka_dl.py "https://www.mureka.ai/song-detail/RvtfZDUHsJLJiTUiodBz8Z?is_from_share=1"
    python mureka_dl.py RvtfZDUHsJLJiTUiodBz8Z -o minha_musica.mp3

Sem dependências além da stdlib. Só use com músicas suas ou que você tem direito de baixar.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://www.mureka.ai"
CDN = "https://static-cos.mureka.ai/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def extract_share_key(url_or_key: str) -> str:
    s = url_or_key.strip()
    m = re.search(r"song-detail/([A-Za-z0-9_-]+)", s)
    if m:
        return m.group(1)
    m = re.search(r"share_key=([A-Za-z0-9_-]+)", s)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{8,64}", s):
        return s
    raise ValueError("Share key não encontrada. Cole o link song-detail/... ou a chave.")


def api_detail(share_key: str) -> dict:
    params = urllib.parse.urlencode({"share_key": share_key})
    url = BASE + "/api/pgc/song/detail?" + params
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json",
        "Referer": BASE + "/song-detail/" + share_key + "?is_from_share=1",
        "X-Auth-Timestamp": str(int(time.time() * 1000)),
    }, method="GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    if data.get("code") not in (0, 200):
        raise RuntimeError("API retornou code=%s msg=%s" % (data.get("code"), data.get("msg")))
    song = (data.get("data") or {}).get("song") or {}
    if not song.get("mp3_url"):
        raise RuntimeError("Resposta sem mp3_url: %s" % list(song.keys()))
    return song


def download(url: str, referer: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer}, method="GET")
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def safe_name(s: str) -> str:
    s = re.sub(r"[^\w\s\-]+", "", s, flags=re.U).strip()
    return re.sub(r"\s+", "_", s) or "mureka_track"


def main() -> int:
    ap = argparse.ArgumentParser(description="Baixa música do Mureka e salva o MP3.")
    ap.add_argument("song", help="URL song-detail/... ou share_key")
    ap.add_argument("-o", "--out", default=None, help="Arquivo MP3 de saída (default: <titulo>.mp3)")
    ap.add_argument("--dir", default=".", help="Pasta de saída (default: atual)")
    args = ap.parse_args()

    sid = extract_share_key(args.song)
    print("[1/2] Lendo detail %s ..." % sid)
    song = api_detail(sid)
    title = song.get("title") or "mureka_track"
    dur = song.get("duration_milliseconds")
    print("      Título: %s | duração: %ss | song_id: %s" % (
        title, (dur / 1000 if dur else "?"), song.get("song_id")))

    rel = song["mp3_url"]
    mp3_url = rel if rel.startswith("http") else CDN + rel.lstrip("/")
    print("[2/2] Baixando %s ..." % mp3_url)
    audio = download(mp3_url, BASE + "/")
    if not (audio[:3] == b"ID3" or (len(audio) > 1 and audio[0] == 0xFF and audio[1] & 0xE0 == 0xE0)):
        print("AVISO: cabeçalho inesperado (%s) — pode não ser MP3." % audio[:8].hex())

    os.makedirs(args.dir, exist_ok=True)
    out = args.out or os.path.join(args.dir, safe_name(title) + ".mp3")
    with open(out, "wb") as f:
        f.write(audio)
    print("      Salvo: %s (%.2f MB)" % (out, len(audio) / 1e6))
    print("OK — gnawed clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
