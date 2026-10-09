#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""POV Lyrics Bottom V2: cena 16:9 limpa + letra animada sem caixa inferior."""
from __future__ import annotations
import json, re, sys, tempfile
from pathlib import Path
from typing import Optional
sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_dispatch as rd
from legenda import filtro_subtitles
try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None

W,H=1080,1920
SCENE_W,SCENE_H=1080,608
SCENE_Y=620
LYRIC_Y=1475
BRAND_Y=1735
FONT_DIR=Path(__file__).resolve().parent/'fontes'

PRESETS={
 'word_pop_neon': {'font':'Poppins-ExtraBold.ttf','size':64,'accent':'#FFFFFF','mode':'word'},
 'word_clean': {'font':'Montserrat-Variable.ttf','size':62,'accent':'#FFFFFF','mode':'word'},
 'phrase_impact': {'font':'BlackOpsOne-Regular.ttf','size':70,'accent':'#FF365C','mode':'phrase'},
}
def _font(name: str, size: int):
    p=Path(name)
    if not p.is_file(): p=FONT_DIR/name
    return ImageFont.truetype(str(p),size) if p.is_file() else ImageFont.load_default()

def _rgb(h: str):
    s=h.lstrip('#'); return tuple(int(s[i:i+2],16) for i in (0,2,4))

def _ass(h: str):
    r,g,b=_rgb(h); return f'&H00{b:02X}{g:02X}{r:02X}'

def _tc(sec: float)->str:
    sec=max(0,sec); h=int(sec//3600); m=int((sec%3600)//60); s=sec%60
    return f'{h}:{m:02d}:{s:05.2f}'

def _wrap_words(words:list[str], max_chars:int=27)->list[list[str]]:
    lines=[]; cur=[]; n=0
    for w in words:
        add=len(w)+(1 if cur else 0)
        if cur and n+add>max_chars:
            lines.append(cur); cur=[w]; n=len(w)
        else:
            cur.append(w); n+=add
    if cur: lines.append(cur)
    if len(lines)>2:
        lines=[lines[0],sum(lines[1:],[])]
    return lines

def _escape_ass(t:str)->str:
    return t.replace('{','(').replace('}',')')
def make_overlay(dest:Path, gancho:str, anime:str, tema:str,
                 cor:str='#8A2BE2', marca:str='VX RAPS', handle:str='@VXRaps'):
    if Image is None: raise RuntimeError('Pillow necessario')
    im=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(im)
    accent=_rgb(cor)
    f_label=_font('BebasNeue-Regular.ttf',36)
    f_hook=_font('Anton-Regular.ttf',44)
    f_brand=_font('BebasNeue-Regular.ttf',48)
    x0,x1=46,W-46; y1=SCENE_Y-28; y0=y1-205
    d.rounded_rectangle((x0,y0,x1,y1),20,fill=(10,11,16,220),outline=accent+(255,),width=3)
    label=f'POV  •  {anime.upper()}  //  {tema.upper()}'
    d.text((x0+28,y0+25),label,font=f_label,fill=(218,220,226,255))
    hook=gancho.upper(); maxw=x1-x0-56; lines=[]; cur=''
    for w in hook.split():
        t=(cur+' '+w).strip()
        if d.textlength(t,font=f_hook)<=maxw or not cur: cur=t
        else: lines.append(cur); cur=w
    if cur: lines.append(cur)
    for i,line in enumerate(lines[:2]):
        d.text((x0+28,y0+80+i*54),line,font=f_hook,fill=(250,250,252,255))
    brand=f'{marca.upper()}  •  {handle}'
    tw=d.textlength(brand,font=f_brand)
    # Marca maior e solta, sem caixa; sombra para leitura sobre qualquer fundo.
    d.text(((W-tw)/2+2,BRAND_Y+3),brand,font=f_brand,fill=(0,0,0,190))
    d.text(((W-tw)/2,BRAND_Y),brand,font=f_brand,fill=(244,245,248,255),stroke_width=1,stroke_fill=accent+(255,))
    dest.parent.mkdir(parents=True,exist_ok=True); im.save(dest); return dest
def _family(font_file:str)->str:
    known={
      'Bangers-Regular.ttf':'Bangers',
      'Anton-Regular.ttf':'Anton',
      'BlackOpsOne-Regular.ttf':'Black Ops One',
      'BebasNeue-Regular.ttf':'Bebas Neue',
      'Cinzel-Bold.ttf':'Cinzel',
      'Poppins-ExtraBold.ttf':'Poppins ExtraBold',
      'Montserrat-Variable.ttf':'Montserrat',
    }
    return known.get(Path(font_file).name,Path(font_file).stem.replace('-Regular',''))

def _canonical_lines(path:Path)->list[dict]:
    data=json.loads(path.read_text(encoding='utf-8'))
    return data.get('lines',[])

def _line_words(line:dict)->list[dict]:
    # Mantem inclusive palavras gap sem timestamp; elas aparecem junto
    # da proxima palavra temporizada em vez de sumirem da letra.
    out=[]
    for w in line.get('words') or []:
        word=str(w.get('word','')).strip()
        if not word: continue
        try:
            a=float(w['start']) if w.get('start') is not None else None
            b=float(w['end']) if w.get('end') is not None else None
        except (TypeError,ValueError):
            a=b=None
        out.append({'word':word,'start':a,'end':b})
    return out

def _styled_progress(words:list[str], current:int, accent:str)->str:
    out=[]
    for i,w in enumerate(words[:current+1]):
        w=_escape_ass(w)
        if i==current:
            out.append(r'{\1c&H00FFFFFF&\bord6\blur0\fscx108\fscy108}'+w+r'{\fscx100\fscy100\bord4}')
        else: out.append(w)
    return ' '.join(out)
def _progress_text(words:list[str], current:int, accent:str, max_chars:int)->str:
    wrapped=_wrap_words(words,max_chars)
    first_n=len(wrapped[0]) if wrapped else 0
    parts=[]
    for i,w in enumerate(words[:current+1]):
        if i==first_n and i>0: parts.append(r'\N')
        w=_escape_ass(w)
        if i==current:
            parts.append(r'{\1c&H00FFFFFF&\bord6\blur0\fscx108\fscy108}'+w+r'{\fscx100\fscy100\bord4}')
        else: parts.append(w)
    text=' '.join(parts).replace(' \\N ',r'\N')
    return text

def build_ass(canonical:Path,dest:Path,start:float,dur:float,
              preset:str='word_pop_neon',font:Optional[str]=None):
    cfg=dict(PRESETS[preset])
    if font: cfg['font']=font
    family=_family(cfg['font']); size=int(cfg['size']); accent=_ass(cfg['accent'])
    header=("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nScaledBorderAndShadow: yes\n\n"
      "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
      f"Style: Lyric,{family},{size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,0,0,0,0,100,100,1,0,1,4,2,5,60,60,0,1\n\n"
      "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    events=[]
    clip_end=start+dur
    for line in _canonical_lines(canonical):
        a=float(line.get('start',0)); b=float(line.get('end',a+1.5))
        if b<=start or a>=clip_end: continue
        words=_line_words(line)
        if cfg['mode']=='word' and words:
            events.extend(_word_events(words,a,b,start,clip_end,accent,preset))
        else:
            events.append(_phrase_event(str(line.get('text','')),a,b,start,clip_end,accent,preset))
    dest.write_text(header+'\n'.join(e for e in events if e)+'\n',encoding='utf-8-sig')
    return dest
def _word_events(words:list[dict],line_a:float,line_b:float,start:float,
                 clip_end:float,accent:str,preset:str)->list[str]:
    labels=[w['word'] for w in words]
    out=[]; max_chars=25 if preset=='word_pop_neon' else 29
    timed=[i for i,w in enumerate(words) if w.get('start') is not None and w.get('end') is not None]
    for pos,i in enumerate(timed):
        w=words[i]
        a=max(float(w['start']),start,line_a)
        next_i=timed[pos+1] if pos+1<len(timed) else None
        next_a=float(words[next_i]['start']) if next_i is not None else line_b
        b=min(max(float(w['end']),next_a),line_b,clip_end)
        if b-a<0.04: continue
        # inclui gaps anteriores (ex.: artigos curtos sem timestamp) na frase acumulada
        text=_progress_text(labels,i,accent,max_chars)
        if preset=='word_pop_neon':
            tag=(r'{\an5\pos(540,'+str(LYRIC_Y)+r')\fad(20,35)\bord4\shad2'
                 r'\fscx106\fscy106\t(0,110,\fscx100\fscy100)')
        else:
            tag=(r'{\an5\pos(540,'+str(LYRIC_Y)+r')\fad(15,30)\bord4\shad2'
                 r'\fscx102\fscy102\t(0,90,\fscx100\fscy100)')
        out.append(f'Dialogue: 0,{_tc(a-start)},{_tc(b-start)},Lyric,,0,0,0,,{tag}}}{text}')
    return out

def _phrase_event(text:str,a:float,b:float,start:float,clip_end:float,
                  accent:str,preset:str)->str:
    a=max(a,start); b=min(b,clip_end)
    if b-a<0.04: return ''
    words=text.split(); wrapped=_wrap_words(words,25)
    text=r'\N'.join(' '.join(x) for x in wrapped)
    text=_escape_ass(text).replace('\\N',r'\N')
    tag=(r'{\an5\pos(540,'+str(LYRIC_Y)+r')\fad(25,70)\bord6\shad3\blur2'
         r'\1c&H00FFFFFF&\3c'+accent+r'\fscx122\fscy122'
         r'\t(0,150,\fscx100\fscy100\blur0\bord4)}')
    return f'Dialogue: 0,{_tc(a-start)},{_tc(b-start)},Lyric,,0,0,0,,{tag}{text}'
def render(source:Path,canonical:Path,output:Path,start:float,gancho:str,
           anime:str,tema:str,preset:str='word_pop_neon',font:Optional[str]=None,
           cor:str='#8A2BE2',dur:float=35.0):
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vx_pov_lyrics_v2_') as td:
        td=Path(td)
        overlay=make_overlay(td/'overlay.png',gancho,anime,tema,cor)
        ass=build_ass(canonical,td/'lyrics.ass',start,dur,preset,font)
        sub=filtro_subtitles(ass)
        fc=(f'[0:v]split=2[bg][fg];'
            f'[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,'
            f'gblur=sigma=32:steps=3,eq=brightness=-0.25[b];'
            f'[fg]scale=1080:608:force_original_aspect_ratio=decrease,'
            f'pad=1080:608:(ow-iw)/2:(oh-ih)/2[s];'
            f'[b][s]overlay=0:{SCENE_Y}[v0];'
            f'[v0][1:v]overlay=0:0:format=auto[v1];'
            f'[v1]{sub},fps=30,format=yuv420p[vout]')
        rd.encode(str(output),['-i',str(source),'-i',str(overlay)],
                  filtro_complexo=fc,mapa=['-map','[vout]','-map','0:a:0'],
                  args_audio=['-c:a','aac','-b:a','256k','-ar','48000'],
                  args_extra=['-t',str(dur),'-shortest'])
    return output
