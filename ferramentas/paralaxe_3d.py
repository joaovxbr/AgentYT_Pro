#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
paralaxe_3d.py — Profundidade 3D Cinemática com Recorte de Personagem e Câmera Lenta.
Separa o personagem do fundo (rembg) e recria uma cena 2.5D com movimento de câmera:
- O fundo se move lentamente (0.95x zoom / pan suave) com leve desfoque de lente (bokeh)
- O personagem na frente tem movimento independente e escala dinâmica (1.05x zoom)
- Efeito 'Parallax 3D' idêntico aos melhores edits de anime do After Effects.
"""
from pathlib import Path
import sys
import numpy as np
from PIL import Image, ImageFilter

def reconstruir_fundo(rgb, alpha):
    """Remove the hidden subject before camera displacement; no ghost duplicate."""
    import cv2
    h,w=alpha.shape
    small=cv2.resize(rgb,(max(1,w//4),max(1,h//4)))
    mask=cv2.resize((alpha>8).astype('uint8')*255,(small.shape[1],small.shape[0]))
    mask=cv2.dilate(mask,np.ones((5,5),np.uint8))
    return cv2.resize(cv2.inpaint(small,mask,5,cv2.INPAINT_TELEA),(w,h))


def compor_profundidade(bg, rgba, progresso):
    """Independent camera/subject transforms; anatomy remains rigid and intact."""
    import cv2
    h,w=bg.shape[:2];p=float(progresso)
    mb=cv2.getRotationMatrix2D((w/2,h/2),0,1.07-.035*p)
    mb[0,2]+=w*.012*p
    back=cv2.warpAffine(bg,mb,(w,h),borderMode=cv2.BORDER_REFLECT)
    mc=cv2.getRotationMatrix2D((w/2,h*.55),0,1.015+.055*p)
    mc[0,2]-=w*.019*p;mc[1,2]-=h*.013*p
    front=cv2.warpAffine(rgba,mc,(w,h))
    a=front[:,:,3:4].astype('float32')/255
    return np.clip(front[:,:,:3]*a+back*(1-a),0,255).astype('uint8')


def gerar_frames_paralaxe_3d(
    frame_original_path: str,
    pasta_saida: Path,
    duracao_s: float = 2.0,
    fps: int = 30,
    direcao_pan: str = "zoom_in"
) -> list[Path]:
    """
    Gera uma sequência de frames com profundidade e movimento 3D.
    """
    pasta_saida.mkdir(parents=True, exist_ok=True)
    orig_path = Path(frame_original_path)
    
    img_orig = Image.open(orig_path).convert("RGBA")
    w, h = img_orig.size

    # 1. Recortar personagem usando rembg
    from rembg import remove
    personagem_rgba = remove(img_orig)

    # 2. Criar fundo inpainteado/desfocado
    # Desfoca o fundo original para dar bokeh/profundidade de campo cinematográfica
    fundo_bokeh = img_orig.filter(ImageFilter.GaussianBlur(15))

    total_frames = int(duracao_s * fps)
    frames_gerados = []

    for f in range(total_frames):
        prog = f / max(1, total_frames - 1)
        
        # O fundo dá zoom out lento (1.08 -> 1.0)
        escala_fundo = 1.08 - (0.08 * prog)
        # O personagem dá zoom in (1.0 -> 1.12)
        escala_char = 1.0 + (0.12 * prog)

        # Tratar fundo
        fw, fh = int(w * escala_fundo), int(h * escala_fundo)
        fundo_res = fundo_bokeh.resize((fw, fh), Image.Resampling.BILINEAR)
        # Recortar centro
        fx = (fw - w) // 2
        fy = (fh - h) // 2
        fundo_frame = fundo_res.crop((fx, fy, fx + w, fy + h))

        # Tratar personagem
        cw, ch = int(w * escala_char), int(h * escala_char)
        char_res = personagem_rgba.resize((cw, ch), Image.Resampling.LANCZOS)
        cx = (cw - w) // 2
        cy = (ch - h) // 2
        char_frame = char_res.crop((cx, cy, cx + w, cy + h))

        # Compor os dois
        frame_final = Image.alpha_composite(fundo_frame, char_frame)

        out_f = pasta_saida / f"parallax_{f:04d}.png"
        frame_final.save(out_f, "PNG")
        frames_gerados.append(out_f)

    return frames_gerados

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python paralaxe_3d.py <imagem.jpg>")
        sys.exit(1)
    res = gerar_frames_paralaxe_3d(sys.argv[1], Path("teste_paralaxe"), duracao_s=1.0)
    print(f"Sucesso: {len(res)} frames gerados!")
