#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VX POV Official: Poppins base, Anton em refrões, fontes especiais em keywords."""
from __future__ import annotations
import json, re, sys, tempfile, unicodedata
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_dispatch as rd
from legenda import filtro_subtitles
import pov_lyrics_bottom_v2 as base
from compositor_master_gpu import LIMITADOR_TRUE_PEAK

W,H=1080,1920
SCENE_Y=620
LYRIC_Y=1475
FONT_DIR=Path(__file__).resolve().parent/'fontes'
# Legado (projeto Sasuke). Producao passa `especiais` gerado do manifesto (shorts_pipeline).
SPECIAL={
    'CHIDORI':'Black Ops One','KIRIN':'Black Ops One','SUSANOO':'Black Ops One',
    'RINNEGAN':'Black Ops One','AMATERASU':'Bangers','VINGADOR':'Bangers',
    'MANGEKYO':'Bangers'
}

def norm(text:str)->str:
    s=unicodedata.normalize('NFKD',text).encode('ascii','ignore').decode().upper()
    return ' '.join(re.findall(r'[A-Z0-9]+',s))

def tc(sec:float)->str:
    sec=max(0.0,sec); h=int(sec//3600); m=int((sec%3600)//60); s=sec%60
    return f'{h}:{m:02d}:{s:05.2f}'

def esc(text:str)->str:
    return text.replace('{','(').replace('}',')')

def wrap_words(words:list[str], max_chars:int=28)->tuple[list[list[str]],int]:
    lines=[]; cur=[]; count=0
    for word in words:
        add=len(word)+(1 if cur else 0)
        if cur and count+add>max_chars:
            lines.append(cur); cur=[word]; count=len(word)
        else:
            cur.append(word); count+=add
    if cur: lines.append(cur)
    if len(lines)>2: lines=[lines[0],sum(lines[1:],[])]
    return lines, len(lines[0]) if lines else 0

def canonical_lines(path:Path)->list[dict]:
    """Aceita transcricao_canonica.json ({'lines': [...]}) ou letra_sincronizada.json (lista)."""
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    return data.get('lines',[]) if isinstance(data,dict) else list(data or [])

def refrain_keys(lines:list[dict])->set[str]:
    counts={}
    for line in lines:
        key=norm(str(line.get('text','')))
        if key: counts[key]=counts.get(key,0)+1
    return {key for key,n in counts.items() if n>1}

def line_words(line:dict)->list[dict]:
    out=[]
    for item in line.get('words') or []:
        word=str(item.get('word') or item.get('text') or '').strip()
        if not word: continue
        try:
            start=float(item['start']) if item.get('start') is not None else None
            end=float(item['end']) if item.get('end') is not None else None
        except (TypeError,ValueError):
            start=end=None
        out.append({'word':word,'start':start,'end':end})
    return out

def progress_text(labels:list[str], current:int, base_family:str, max_chars:int,
                  especiais:dict|None=None)->str:
    especiais=SPECIAL if especiais is None else especiais
    _, first_n=wrap_words(labels,max_chars)
    base_b=r'\b1' if base_family=='Poppins' else r'\b0'
    parts=[r'{\fn'+base_family+base_b+r'}']
    for i,word in enumerate(labels[:current+1]):
        if i==first_n and i>0: parts.append(r'\N')
        clean=esc(word)
        if i==current:
            special=especiais.get(norm(word)); family=special or base_family
            scale=118 if special else 108
            cur_b=r'\b0' if special else base_b
            parts.append(r'{\fn'+family+cur_b+r'\1c&H00FFFFFF&\bord6\blur0\fscx'+str(scale)+r'\fscy'+str(scale)+'}'+clean+r'{\fn'+base_family+base_b+r'\fscx100\fscy100\bord4}')
        else:
            parts.append(clean)
    return ' '.join(parts).replace(' \\N ',r'\N')

def event_tag()->str:
    return (r'{\an5\pos(540,'+str(LYRIC_Y)+r')\fad(15,30)\bord4\shad2'
            r'\fscx103\fscy103\t(0,95,\fscx100\fscy100)}')

def build_ass(canonical:Path,dest:Path,start:float,dur:float,especiais:dict|None=None)->Path:
    lines=canonical_lines(canonical); refrains=refrain_keys(lines); clip_end=start+dur
    header=("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nScaledBorderAndShadow: yes\n\n"
      "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
      "Style: Lyric,Poppins,64,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,0,0,0,0,100,100,1,0,1,4,2,5,60,60,0,1\n\n"
      "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    events=[]
    for line in lines:
        line_a=float(line.get('start',0)); line_b=float(line.get('end',line_a+1.5))
        if line_b<=start or line_a>=clip_end: continue
        words=line_words(line); labels=[w['word'] for w in words]
        if not words: continue
        family='Anton' if norm(str(line.get('text',''))) in refrains else 'Poppins'
        max_chars=29 if family=='Poppins' else 26
        timed=[i for i,w in enumerate(words) if w['start'] is not None and w['end'] is not None]
        for pos,i in enumerate(timed):
            w=words[i]; next_i=timed[pos+1] if pos+1<len(timed) else None
            # o evento da palavra termina quando a PROXIMA acende: nunca duas versoes da
            # frase na tela ao mesmo tempo (incidente 2026-10-01-douma-pov-fora-de-ordem)
            if next_i is not None:
                b=min(float(words[next_i]['start']),line_b,clip_end)
            else:
                b=min(line_b,clip_end)
            if b<=start: continue
            a=max(float(w['start']),start,line_a)
            if b-a<0.04: continue
            text=progress_text(labels,i,family,max_chars,especiais)
            events.append(f'Dialogue: 0,{tc(a-start)},{tc(b-start)},Lyric,,0,0,0,,{event_tag()}{text}')
    dest.write_text(header+'\n'.join(events)+'\n',encoding='utf-8-sig')
    return dest

def render(source:Path,canonical:Path,output:Path,start:float,gancho:str,
           anime:str,tema:str,cor:str='#7D2BFF',dur:float=35.0,especiais:dict|None=None)->Path:
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vx_pov_official_') as td:
        td=Path(td)
        overlay=base.make_overlay(td/'overlay.png',gancho,anime,tema,cor)
        ass=build_ass(canonical,td/'lyrics.ass',start,dur,especiais)
        sub=filtro_subtitles(ass)
        fc=(f'[0:v]split=2[bg][fg];'
            f'[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,'
            f'gblur=sigma=32:steps=3,eq=brightness=-0.25[b];'
            f'[fg]scale=1080:608:force_original_aspect_ratio=decrease,'
            f'pad=1080:608:(ow-iw)/2:(oh-ih)/2[s];'
            f'[b][s]overlay=0:{SCENE_Y}[v0];[v0][1:v]overlay=0:0:format=auto[v1];'
            f'[v1]{sub},fps=30,format=yuv420p[vout];'
            # mesmo teto de true peak do master + micro fades (corte limpo/loop do Short)
            f'[0:a]afade=t=in:st=0:d=0.12,afade=t=out:st={max(0.0,dur-0.5):.3f}:d=0.5,'
            f'{LIMITADOR_TRUE_PEAK}[aout]')
        rd.encode(str(output),['-i',str(source),'-i',str(overlay)],filtro_complexo=fc,
                  mapa=['-map','[vout]','-map','[aout]'],
                  args_audio=['-c:a','aac','-b:a','256k','-ar','48000'],
                  args_extra=['-t',str(dur),'-shortest'])
    return output
