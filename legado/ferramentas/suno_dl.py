#!/usr/bin/env python3
"""
suno_dl.py — Baixa e destrava músicas do Suno (stream AES-CTR) e converte pra MP3.

O Suno entrega o áudio criptografado (m4a-opus, encoding 1.0.0).
Este script: 1) pega os direitos (key/iv/glt), 2) descriptografa,
3) converte pra MP3 320k via ffmpeg (se disponível).

Uso:
    python suno_dl.py <suno-song-url-ou-uuid> [-o saida.mp3] [--keep-m4a] [--no-mp3]

Ex:
    python suno_dl.py https://suno.com/song/50f942e6-fa41-4f8e-826e-00dcd662c726
    python suno_dl.py 50f942e6-fa41-4f8e-826e-00dcd662c726 -o minha_musica.mp3

Dependências: pip install pycryptodome | ffmpeg no PATH (só pro MP3)
Só use com músicas suas ou que você tem direito de baixar.
"""

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

RIGHTS_URL = "https://yellow-salad.aibiei.com/rights"
AUDIO_BASE = "https://d2lwuy8qc234o3.cloudfront.net/1/clip/"
CLIP_API = "https://studio-api.prod.suno.com/api/clip/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def b64d(v: str) -> bytes:
    s = v.replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    return base64.b64decode(s)


def extract_uuid(url_or_id: str) -> str:
    m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", url_or_id, re.I)
    if not m:
        raise ValueError("Nenhum UUID de música encontrado. Cole o link suno.com/song/... ou o UUID.")
    return m.group(0).lower()


def fetch_clip_meta(cid: str) -> dict:
    req = urllib.request.Request(CLIP_API + cid, headers={"User-Agent": UA}, method="GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fetch_rights(cid: str) -> dict:
    body = json.dumps({"content_params": {"content_id": cid, "content_type": "clip"}}).encode()
    req = urllib.request.Request(
        RIGHTS_URL, data=body, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "User-Agent": UA, "Origin": "https://usesuno.com",
                 "Referer": "https://usesuno.com/"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        rights = json.loads(r.read())
    if not all(k in rights for k in ("key", "iv", "glt")):
        raise RuntimeError("Resposta de direitos incompleta: %s" % list(rights.keys()))
    return rights


def unwrap_gcm(wrapped_b64: str, userkey: bytes, cid: str) -> bytes:
    from Crypto.Cipher import AES
    w = b64d(wrapped_b64)
    if len(w) < 28:
        raise RuntimeError("Chave/IV embrulhada incompleta.")
    nonce, ct_tag = w[:12], w[12:]
    ct, tag = ct_tag[:-16], ct_tag[-16:]
    c = AES.new(userkey, AES.MODE_GCM, nonce=nonce)
    c.update(cid.encode())
    return c.decrypt_and_verify(ct, tag)


def decrypt_file(enc: bytes, key: bytes, iv: bytes) -> bytes:
    from Crypto.Cipher import AES
    ctr = AES.new(key, AES.MODE_CTR, nonce=b"", initial_value=int.from_bytes(iv, "big"))
    return ctr.decrypt(enc)


def detect_ext(data: bytes) -> str:
    if data[:4] == bytes([0x1A, 0x45, 0xDF, 0xA3]):
        return ".webm"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return ".mp3"
    return ".m4a"  # ftyp isom — caso normal do Suno


def safe_name(s: str) -> str:
    s = re.sub(r"[^\w\s\-áàâãéèêíïóôõöúçñ]+", "", s, flags=re.I).strip()
    return re.sub(r"\s+", "_", s) or "suno_track"


def main() -> int:
    ap = argparse.ArgumentParser(description="Baixa música do Suno e converte pra MP3.")
    ap.add_argument("song", help="URL suno.com/song/... ou UUID")
    ap.add_argument("-o", "--out", default=None, help="Arquivo MP3 de saída (default: <titulo>.mp3)")
    ap.add_argument("--keep-m4a", action="store_true", help="Mantém o .m4a destravado intermediário")
    ap.add_argument("--no-mp3", action="store_true", help="Só destrava, não converte pra MP3")
    ap.add_argument("--dir", default=".", help="Pasta de saída (default: atual)")
    args = ap.parse_args()

    try:
        from Crypto.Cipher import AES  # noqa: F401
    except ImportError:
        print("ERRO: pip install pycryptodome", file=sys.stderr)
        return 1

    cid = extract_uuid(args.song)
    print("[1/4] Lendo metadados do clip %s ..." % cid)
    meta = fetch_clip_meta(cid)
    title = meta.get("title") or "suno_track"
    print("      Título: %s | modelo: %s | duração: %ss" % (
        title, meta.get("major_model_version"), meta.get("metadata", {}).get("duration")))

    print("[2/4] Pedindo chave de destrave ...")
    rights = fetch_rights(cid)
    userkey = hashlib.sha256(rights["glt"].encode()).digest()
    key = unwrap_gcm(rights["key"], userkey, cid)
    iv = unwrap_gcm(rights["iv"], userkey, cid)
    print("      key=%d bytes iv=%s" % (len(key), iv.hex()))

    print("[3/4] Baixando stream criptografado ...")
    req = urllib.request.Request(AUDIO_BASE + cid + ".m4a", headers={"User-Agent": UA}, method="GET")
    with urllib.request.urlopen(req, timeout=120) as r:
        enc = r.read()
    print("      %.2f MB baixados, destravando ..." % (len(enc) / 1e6))
    dec = decrypt_file(enc, key, iv)
    ext = detect_ext(dec)
    if dec[4:8] != b"ftyp" and ext == ".m4a":
        print("AVISO: cabeçalho inesperado (%s) — destrave pode ter falhado." % dec[:16].hex())

    os.makedirs(args.dir, exist_ok=True)
    base = safe_name(title)
    m4a_path = os.path.join(args.dir, base + ext)
    with open(m4a_path, "wb") as f:
        f.write(dec)
    print("      Salvo: %s (%.2f MB)" % (m4a_path, len(dec) / 1e6))

    if args.no_mp3:
        return 0

    print("[4/4] Convertendo pra MP3 320k ...")
    mp3_path = args.out or os.path.join(args.dir, base + ".mp3")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("AVISO: ffmpeg não encontrado no PATH — ficando só com %s" % m4a_path)
        return 0
    subprocess.run([ffmpeg, "-y", "-v", "error", "-i", m4a_path,
                    "-codec:a", "libmp3lame", "-b:a", "320k", mp3_path], check=True)
    print("      Salvo: %s (%.2f MB)" % (mp3_path, os.path.getsize(mp3_path) / 1e6))
    if not args.keep_m4a and m4a_path != mp3_path and ext == ".m4a":
        pass  # mantém por padrão; apague manualmente se quiser
    print("OK — gnawed clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
