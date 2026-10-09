"""Manifest-driven revision renderer. Entry: estudio.py revisao <slug>.
No publishing, no destructive cleanup, no fabricated sync approval.
"""
from pathlib import Path
import json, subprocess, hashlib, re, unicodedata, urllib.request
import numpy as np
import render_dispatch as rd
from pipeline_autonomo_pro import quantizar_cortes
ROOT=Path(__file__).resolve().parents[1]

def refinar_alpha(alpha):
    """Erode only the silhouette rim, never recolor face pixels."""
    import cv2
    eroded=cv2.erode(alpha,np.ones((3,3),np.uint8),iterations=1)
    return cv2.GaussianBlur(eroded,(3,3),.55)


def depth_take(p,cfg,work,n,out):
    """Short parallax take using an approved still mask, NOT chroma key."""
    from PIL import Image
    asset=p/cfg['depth_asset'];im=Image.open(asset).convert('RGBA')
    arr=np.array(im);arr[:,:,3]=refinar_alpha(arr[:,:,3]);clean=work/'depth_clean.png';Image.fromarray(arr).save(clean)
    back=work/'depth_back.ass';front=work/'depth_front.ass'
    back.write_text(HEADER+event(0,n/30,r'{\an5\move(900,450,1020,450)\fs230\fsp18\c&H00FFE040&}U C H I H A','Hero'),encoding='utf-8')
    front.write_text(HEADER+event(0,n/30,r'{\an2\pos(960,835)\fs62\bord4}SASUKE / O PESO DA ESCOLHA'),encoding='utf-8')
    graph=f"[0:v]scale=1920:1080,setsar=1,gblur=sigma=4,eq=brightness=-0.08,ass='{back.relative_to(ROOT).as_posix()}':fontsdir=assets/fontes/revisao[b];[1:v]scale=1920:1080,format=rgba[f];[b][f]overlay=x='10*sin(t*1.4)':y=0,ass='{front.relative_to(ROOT).as_posix()}':fontsdir=assets/fontes/revisao,fps=30,setsar=1,format=yuv420p[v]"
    rd.encode(str(out),['-loop','1','-i',str(p/cfg['depth_background']),'-loop','1','-i',str(clean)],filtro_complexo=graph,mapa=['-map','[v]'],args_audio=['-an'],args_extra=['-frames:v',str(n)],silencioso=True,cq='17')


def dump(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')

def probe(p):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)]))

def fonts():
    d=ROOT/'assets/fontes/revisao';d.mkdir(parents=True,exist_ok=True)
    evidence=[]
    for family,file in [('anton','Anton-Regular.ttf'),('barlow','Barlow-SemiBold.ttf')]:
        url='https://raw.githubusercontent.com/google/fonts/main/ofl/'+family+'/'
        for name in [file,'OFL.txt']:
            out=d/(family+'-'+name if name=='OFL.txt' else name)
            if not out.exists(): urllib.request.urlretrieve(url+name,out)
        license=(d/(family+'-OFL.txt')).read_text(encoding='utf-8')
        assert 'SIL OPEN FONT LICENSE' in license
        assert (d/file).read_bytes()[:4] in [b'\x00\x01\x00\x00',b'OTTO']
        evidence.append(dict(family=family,url=url+file,license_url=url+'OFL.txt',license='SIL OFL 1.1',commercial=True,sha256=hashlib.sha256((d/file).read_bytes()).hexdigest()))
    dump(d/'evidence.json',evidence)
    return d

def tc(t):
    n=round(t*100);return f'{n//360000}:{n//6000%60:02}:{n//100%60:02}.{n%100:02}'

HEADER='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Lyric,Barlow SemiBold,64,&H00FFFFFF,&H00FFFF00,&H00101018,&H90000000,0,0,0,0,100,100,1,0,1,3,1,2,100,100,70,1
Style: Hero,Anton,155,&H00FFFFFF,&H00FFFF00,&H00101018,&H90000000,0,0,0,0,100,100,4,0,1,3,2,7,100,100,70,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
def event(a,b,text,style='Lyric',layer=1):
    return f'Dialogue: {layer},{tc(a)},{tc(b)},{style},,0,0,0,,{text}\n'

def norm(w):
    return re.sub(r'\W','',unicodedata.normalize('NFKD',w).encode('ascii','ignore').decode().lower())

def subtitles(p,cfg,qa):
    """Agreement across separate mix/stem ASR plus measured vocal activity.
    Missing/disputed words are omitted, not passed as perfect alignment.
    """
    import soundfile as sf
    old=json.loads((p/cfg['mix_transcript']).read_text(encoding='utf-8'))['words']
    fresh=[]
    for src in cfg['vocal_transcripts']:
        data=json.loads((p/src['file']).read_text(encoding='utf-8'))
        fresh.extend(dict(w,start=w['start']+src.get('offset',0),end=w['end']+src.get('offset',0)) for w in data['words'])
    fresh.sort(key=lambda w:w['start'])
    y,sr=sf.read(p/cfg['vocal']); y=y.mean(axis=1) if y.ndim>1 else y
    hop=int(sr*.01); rms=np.array([np.sqrt(np.mean(y[i:i+hop]**2)) for i in range(0,len(y),hop)])
    threshold=max(.003,float(np.percentile(rms,85))*.045)
    accepted=[];rejected=[];deltas=[]
    for w in old:
        candidates=[v for v in fresh if norm(v['word'])==norm(w['word']) and abs(v['start']-w['start'])<=.30]
        if not candidates or norm(w['word']) in cfg.get('reject_words',[]):
            rejected.append(w);continue
        v=min(candidates,key=lambda v:abs(v['start']-w['start']))
        a,b=float(v['start']),float(v['end'])
        bins=np.flatnonzero(rms[int(a/.01):int(b/.01)+1]>threshold)
        if not len(bins) or b-a<=.015: rejected.append(w);continue
        a=max(a,int(a/.01)*.01+bins[0]*.01);b=min(b,int(v['start']/.01)*.01+(bins[-1]+1)*.01)
        if b<=a:continue
        accepted.append(dict(word=w['word'].strip(),start=a,end=b));deltas.append(abs(v['start']-w['start']))
    lines=HEADER;phrase=[];last=-1
    for w in accepted:
        if w['start']-last>.30 or len(phrase)>=5:phrase=[]
        phrase.append(w['word'].upper());last=w['end']
        previous=' '.join(phrase[:-1]);active=phrase[-1]
        text=(previous+' ' if previous else '')+r'{\c&H00FFE040&\3c&H00604010&\bord3\blur0.6}'+active
        lines+=event(w['start'],w['end'],text)
    if not accepted:
        raise ValueError('Nenhuma palavra alinhada: confira transcricoes e stem vocal')
    out=p/'legendas/revisao_neon.ass'
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(lines,encoding='utf-8')
    dump(qa/'vocal_agreement.json',dict(method='Independent full-mix versus new stem ASR; vocal RMS trims only. NOT listening/phonetic gold standard.',accepted=len(accepted),total=len(old),omitted=rejected,median_asr_disagreement=float(np.median(deltas)),p90_asr_disagreement=float(np.percentile(deltas,90)),rms_threshold=threshold,words=accepted,status='PARTIAL: disputed/missing words omitted; manual listening still required'))
    return out

def analyze_music(p,cfg,qa):
    import librosa
    from scipy.signal import find_peaks
    y,sr=librosa.load(p/cfg['drums'],sr=22050)
    e=librosa.onset.onset_strength(y=y,sr=sr)
    peaks,_=find_peaks(e,distance=int(6*sr/512),prominence=2)
    peaks=sorted(peaks,key=lambda x:float(e[x]),reverse=True)[:14]
    data=[dict(time=float(librosa.frames_to_time(k,sr=sr)),strength=float(e[k])) for k in sorted(peaks)]
    dump(qa/'audio_peaks.json',data)
    return data

def normalize_video():
    return 'setsar=1,scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30'

def audio_graph():
    return '[0:a]aresample=48000,atrim=duration=10,asetpts=N/SR/TB[ia];[2:a]aresample=48000,asetpts=N/SR/TB,afade=t=in:st=0:d=2[ma];[ia][ma]concat=n=2:v=0:a=1,volume=-3.5dB[a]'

def render(p,cfg,qa,ass,peaks):
    import shutil
    work=p/'saidas/revisao_work_v2';work.mkdir(parents=True,exist_ok=True)
    duration=float(probe(p/cfg['audio'])['format']['duration'])
    # Variable edit rhythm; strongest measured transients become exact cut boundaries.
    times=[0.,5.]; t=5.
    while t<duration:
        t+=cfg['cut_lengths'][len(times)%len(cfg['cut_lengths'])]
        if t<duration:times.append(t)
    for hit in peaks:
        t=hit['time'];times=[x for x in times if x in [0.,5.] or abs(x-t)>.65];times.append(t)
    times=sorted(set(times+[duration]));frames=quantizar_cortes(times)
    shots=[];parts=[];pool=cfg['shots']
    for i,(a,b) in enumerate(zip(frames,frames[1:])):
        source=pool[i%len(pool)];clip=p/'clips_raw'/source['clip'];n=b-a
        out=work/f'shot_{i:03}.mp4'
        vf=normalize_video()
        # Motion is a restrained optical camera push, not a glow over facial pixels.
        vf+=",scale=2016:1134,crop=1920:1080:x='48+22*sin(t*1.5)':y=27,setsar=1,format=yuv420p"
        title=HEADER
        nearest=min(peaks,key=lambda h:abs(h['time']-a/30),default=None)
        is_hit=nearest is not None and abs(nearest['time']-a/30)<.025
        if i==0:
            title+=event(0,n/30,r'{\pos(110,170)\fad(180,200)}'+cfg['title'],'Hero')
            title+=event(0,n/30,r'{\an7\pos(115,370)\fs46}'+cfg['subtitle'])
        elif is_hit:
            word=cfg['impact_labels'][sum(1 for s in shots if s['impact'])%len(cfg['impact_labels'])]
            title+=event(0,min(1.05,n/30),r'{\move(80,170,130,170,0,180)\fad(0,140)\c&H00FFE040&\fscx112\t(0,180,\fscx100)}'+word,'Hero')
            title+=event(0,min(1.05,n/30),r'{\an7\pos(135,365)\fs42\bord3}'+cfg['impact_support'])
        tf=work/f'type_{i:03}.ass';tf.write_text(title,encoding='utf-8')
        if i==0 or is_hit: vf+=f",ass='{tf.relative_to(ROOT).as_posix()}':fontsdir=assets/fontes/revisao"
        # Re-render: cached existence cannot validate changed inputs.
        if i==0 and cfg.get('hero_mask'):
            graph="[0:v]scale=1920:1080,setsar=1,"+f"ass='{tf.relative_to(ROOT).as_posix()}':fontsdir=assets/fontes/revisao[bg];[bg][1:v]overlay=0:0,scale=2016:1134,crop=1920:1080:x='48+20*sin(t)':y=27,setsar=1,format=yuv420p[v]"
            rd.encode(str(out),['-loop','1','-framerate','30','-i',str(p/cfg['hero_frame']),'-loop','1','-framerate','30','-i',str(p/cfg['hero_mask'])],filtro_complexo=graph,mapa=['-map','[v]'],args_audio=['-an'],args_extra=['-frames:v',str(n),'-r','30'],silencioso=True,cq='17')
        else:
            rd.encode(str(out),['-ss',str(source['src']),'-i',str(clip)],filtro_v=vf,mapa=['-map','0:v:0'],args_audio=['-an'],args_extra=['-frames:v',str(n),'-r','30'],silencioso=True,cq='17')
        actual=int(probe(out)['streams'][0]['nb_frames']);assert actual==n,(i,actual,n)
        parts.append(out);shots.append(dict(start=a/30,end=b/30,clip=source['clip'],src=source['src'],type='action',impact=is_hit,frames=n))
        print('shot',i,len(frames)-1,flush=True)
    dump(p/'timeline_revisao.json',dict(audio_duration=duration,segments=shots))
    listing=work/'concat.txt';listing.write_text(''.join("file '"+x.name+"'\n" for x in parts),encoding='utf-8')
    raw=work/'montage.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(raw)],check=True)
    intro=ROOT/'assets/intro/Eu_preciso_criar_INTRO_para_o.mp4';assert intro.exists()
    dest=p/'saidas'/cfg['output']
    # Unified encode, not concat-copy of incompatible H264 streams.
    vf0='scale=1920:1080,setsar=1,fps=30,format=yuv420p,trim=end_frame=300,setpts=N/(30*TB)'
    vf1=f"setsar=1,fps=30,ass='{ass.relative_to(ROOT).as_posix()}':fontsdir=assets/fontes/revisao,format=yuv420p,setpts=N/(30*TB)"
    graph=f'[0:v]{vf0}[iv];[1:v]{vf1}[mv];[iv][mv]concat=n=2:v=1:a=0[v];'+audio_graph()
    rd.encode(str(dest),['-i',str(intro),'-reinit_filter','0','-i',str(raw),'-i',str(p/cfg['audio'])],filtro_complexo=graph,mapa=['-map','[v]','-map','[a]'],args_extra=['-r','30','-fps_mode','cfr'],cq='17')
    return dest,shots

def sheets(video,qa,times,name):
    from PIL import Image,ImageDraw
    for batch in range(0,len(times),20):
        subset=times[batch:batch+20];sheet=Image.new('RGB',(1600,((len(subset)+3)//4)*250),(15,15,20));d=ImageDraw.Draw(sheet)
        for i,t in enumerate(subset):
            f=qa/'frame_tmp.jpg';subprocess.run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(video),'-frames:v','1','-vf','scale=400:225',str(f)],check=True)
            x=i%4*400;y=i//4*250;sheet.paste(Image.open(f),(x,y+25));d.text((x+8,y+5),f'{t:.3f}s',fill='white')
        sheet.save(qa/f'{name}_{batch//20+1:02}.jpg')
    (qa/'frame_tmp.jpg').unlink(missing_ok=True)


def tc_seconds(value):
    h,m,s=value.split(':')
    return int(h)*3600+int(m)*60+float(s)


def validar_blocos_previa(cfg):
    expected=' '.join(cfg['lyrics']); actual=' '.join(cfg['phrase_blocks'])
    if norm(expected)!=norm(actual):
        raise ValueError('phrase_blocks must cover the four complete lyric lines in order')
    forbidden={'voce','adorde','emuma'}
    for block in cfg['phrase_blocks']:
        if norm(block) in forbidden or len(block.split()) < 2:
            raise ValueError(f'isolated fragment forbidden: {block}')
    return True


def gerar_ass_previa_v2(words,origin,duration,phrase_blocks):
    """Large complete phrase blocks with a crisp word-level active core."""
    header=HEADER.replace('Barlow SemiBold,64','Cinzel,110').replace('Anton,155','Cinzel,145')
    header=header.replace('&H90000000,0,0,0,0,100,100,1,', '&H90000000,-1,0,0,0,100,100,1,')
    header=header.replace('[Events]', 'Style: Backing,Cinzel,110,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,2,0,0,0,1\n[Events]')
    out=header; cursor=0
    # Keep all lyric blocks in a consistent lower safe band, away from eyes/hair.
    positions=[875,875,875,875,875,875]
    linebreaks={
        'VOCÊ NÃO CONHECE A DOR':'VOCÊ NÃO CONHECE\\NA DOR',
        'DE PERDER TUDO EM UMA NOITE':'DE PERDER TUDO\\NEM UMA NOITE',
        'E AGORA O MUNDO VAI QUEIMAR':'E AGORA O MUNDO\\NVAI QUEIMAR',
    }
    for block_index,block in enumerate(phrase_blocks):
        count=len(block.split()); group=words[cursor:cursor+count]; cursor+=count
        if len(group)!=count: raise ValueError('not enough canonical words for phrase blocks')
        timed=[w for w in group if w.get('start') is not None]
        if not timed: continue
        a=min(float(w['start']) for w in timed)-origin; z=max(float(w['end']) for w in timed)-origin
        y=positions[block_index]
        display=linebreaks.get(block,block)
        width=min(1580,max(600,max(len(x) for x in display.split('\\N'))*43)); x1=960-width//2; x2=960+width//2
        if y < 500:
            top,bottom=35,340
        else:
            top,bottom=720,1015
        shape=(r'{\an7\pos(0,0)\p1\bord0\shad0\blur20\c&H00050408&\alpha&H72&}'
               f'm {x1} {top} l {x2} {top} l {x2-85} {bottom} l {x1+85} {bottom}')
        out+=event(a,z+.10,shape,'Backing',0)
        for j,w in enumerate(group):
            if w.get('start') is None: continue
            wa=float(w['start'])-origin
            later=[x for x in group[j+1:] if x.get('start') is not None]
            boundary=float(later[0]['start'])-origin if later else z+.10
            wz=min(z+.10,boundary+.04)  # >=1 frame overlap after ASS centisecond quantization
            pieces=[]
            break_before={'VOCÊ NÃO CONHECE A DOR':3,
                          'DE PERDER TUDO EM UMA NOITE':3,
                          'E AGORA O MUNDO VAI QUEIMAR':4}.get(block)
            for k,token in enumerate(block.split()):
                prefix=r'\N' if break_before==k else ''
                if k==j:
                    color='&H003040FF&' if norm(token) in {'vermelhos','dor','cortei','queimar'} else '&H00FFD070&'
                    pieces.append(prefix+r'{\b1\c&H00FFFFFF&\3c'+color+r'\bord5.2\blur0.25\fscx110\fscy110\t(0,170,\fscx100\fscy100)}'+token)
                else:
                    pieces.append(prefix+r'{\b1\c&H00F4F4F8&\3c&H00101018&\bord4.2\blur0.15}'+token)
            rendered=' '.join(pieces)
            pos=r'{\an5\pos(960,'+str(y)+r')\q2\fad(35,45)}'
            # Two crisp cores make variable Cinzel weight 700 read as a true display bold.
            out+=event(wa,wz,pos+r'{\bord7\blur0.1\3c&H00000000&}'+rendered,'Lyric',1)
            out+=event(wa,wz,pos+rendered,'Lyric',2)
    if cursor!=len(words): raise ValueError('unused timed words in preview')
    return out


def validar_previa_v3(cfg):
    """Fail closed unless a v3 preview is diverse, contiguous and semantic."""
    validar_blocos_previa(cfg)
    shots=cfg.get('shots') or []
    if len(shots)<8: raise ValueError('v3 preview requires at least 8 cuts')
    required={'sharingan','darkness','family_loss','loneliness','naruto_break','amaterasu'}
    semantics={s.get('semantic') for s in shots}
    if not required.issubset(semantics):
        raise ValueError('missing semantic arc: '+', '.join(sorted(required-semantics)))
    allowed={'eye_pulse','loss_sweep','silhouette_rim','bond_streak','fire_lightwrap'}
    windows=set(); previous=0
    for s in shots:
        a,b=float(s['start']),float(s['end'])
        if abs(a-previous)>1/60: raise ValueError('shot timeline must be contiguous')
        if b<=a: raise ValueError('shot duration must be positive')
        previous=b
        key=(s['clip'],round(float(s['src']),2))
        if key in windows: raise ValueError('source window repeated')
        windows.add(key)
        if s.get('fx') not in allowed: raise ValueError('unknown environmental fx')
    if abs(previous-(float(cfg['end'])-float(cfg['start'])))>1/60:
        raise ValueError('shots must cover preview duration')
    return True


def gerar_ass_previa_v4(words,origin,duration,phrase_blocks):
    """Continuous canonical phrases in a face-safe band with separate neon glow."""
    header=HEADER.replace('Barlow SemiBold,64','Cinzel,104').replace('Anton,155','Cinzel,140')
    header=header.replace('&H90000000,0,0,0,0,100,100,1,', '&H90000000,-1,0,0,0,100,100,1,')
    header=header.replace('[Events]', 'Style: Backing,Cinzel,104,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,2,0,0,0,1\n[Events]')
    out=header;cursor=0
    linebreaks={
        'VOCÊ NÃO CONHECE A DOR':'VOCÊ NÃO CONHECE\\NA DOR',
        'DE PERDER TUDO EM UMA NOITE':'DE PERDER TUDO\\NEM UMA NOITE',
        'E AGORA O MUNDO VAI QUEIMAR':'E AGORA O MUNDO\\NVAI QUEIMAR',
    }
    for block in phrase_blocks:
        tokens=block.split();group=words[cursor:cursor+len(tokens)];cursor+=len(tokens)
        if len(group)!=len(tokens): raise ValueError('not enough canonical words for phrase blocks')
        timed=[w for w in group if w.get('start') is not None]
        if not timed: continue
        a=min(float(w['start']) for w in timed)-origin;z=max(float(w['end']) for w in timed)-origin
        # Different phrase blocks must never coexist on the same frame. Within a
        # block, word states still overlap by >=1 frame for continuous revelation.
        next_start=(float(words[cursor]['start'])-origin
                    if cursor<len(words) and words[cursor].get('start') is not None else None)
        block_end=min(z+.10,next_start) if next_start is not None else z+.10
        display=linebreaks.get(block,block); y=800
        width=min(1580,max(620,max(len(x) for x in display.split('\\N'))*41));x1=960-width//2;x2=960+width//2
        shape=(r'{\an7\pos(0,0)\p1\bord0\shad0\blur18\c&H00050408&\alpha&H78&}'
               f'm {x1} 650 l {x2} 650 l {x2-70} 930 l {x1+70} 930')
        if block != 'EU CORTEI MEUS LAÇOS':
            out+=event(a,block_end,shape,'Backing',0)
        break_before={'VOCÊ NÃO CONHECE A DOR':3,'DE PERDER TUDO EM UMA NOITE':3,
                      'E AGORA O MUNDO VAI QUEIMAR':4}.get(block)
        pos=r'{\an5\pos(960,800)\q2\fad(30,40)}'
        core_tokens=[]
        for k,token in enumerate(tokens):
            prefix=r'\N' if break_before==k else ''
            core_tokens.append(prefix+r'{\b1\c&H00FFFFFF&\3c&H00101018&\bord3.2\blur0}'+token)
        out+=event(a,block_end,pos+' '.join(core_tokens),'Lyric',2)
        plain_tokens=[]
        for k,token in enumerate(tokens):
            plain_tokens.append((r'\N' if break_before==k else '')+token)
        color='&H003040FF&' if any(norm(t) in {'vermelhos','dor','cortei','queimar'} for t in tokens) else '&H00FFD070&'
        out+=event(a,block_end,pos+r'{\c&H00FFFFFF&\3c'+color+r'\bord2.2\blur1.6}'+' '.join(plain_tokens),'Lyric',1)
    if cursor!=len(words): raise ValueError('unused timed words in preview')
    return out


def validar_previa_v4(cfg):
    """V4 contract: diverse source windows and explicit child-to-destruction arc."""
    validar_blocos_previa(cfg);shots=cfg.get('shots') or []
    if len(shots)<9: raise ValueError('v4 preview requires at least 9 cuts')
    required={'sharingan','darkness','child','family_loss','loneliness','naruto_break','destruction','amaterasu'}
    semantics={s.get('semantic') for s in shots}
    if not required.issubset(semantics): raise ValueError('missing v4 semantic arc: '+', '.join(sorted(required-semantics)))
    allowed={'eye_pair','loss_rim','silhouette_rim','bond_crack','fire_lightwrap'}
    windows=set();previous=0
    for s in shots:
        a,b=float(s['start']),float(s['end'])
        if abs(a-previous)>1/60: raise ValueError('shot timeline must be contiguous')
        if b<=a: raise ValueError('shot duration must be positive')
        previous=b;key=(s['clip'],round(float(s['src']),2))
        if key in windows: raise ValueError('source window repeated')
        windows.add(key)
        if s.get('fx') not in allowed: raise ValueError('unknown v4 environmental fx')
    if len(windows)<9: raise ValueError('v4 requires at least 9 unique source windows')
    if abs(previous-(float(cfg['end'])-float(cfg['start'])))>1/60: raise ValueError('shots must cover preview duration')
    order=[s.get('semantic') for s in shots]
    if not (order.index('child') < order.index('family_loss') < order.index('loneliness') < order.index('destruction')):
        raise ValueError('loss microprogression must be child -> family -> loneliness -> destruction')
    return True


def validar_previa_v5(cfg):
    """V5 adds measured darkness, anatomical eye bounds and visible crack energy."""
    validar_previa_v4(cfg)
    dark_categories={'interior_dark','night','cavern_dark'}
    darkness=[s for s in cfg['shots'] if s.get('semantic')=='darkness']
    if not darkness: raise ValueError('v5 requires a darkness scene')
    for s in darkness:
        if s.get('scene_category') not in dark_categories:
            raise ValueError('darkness scene must be genuinely dark/night/interior')
        if float(s.get('measured_luma',999))>45:
            raise ValueError('darkness scene measured luma must be <=45')
    eyes=[s for s in cfg['shots'] if s.get('fx')=='eye_pair']
    if not eyes: raise ValueError('v5 requires an anatomical eye pair')
    for s in eyes:
        centers=s.get('fx_region') or []; regions=s.get('eye_regions') or []
        if len(centers)!=2 or len(regions)!=2: raise ValueError('two explicit eye centers and regions required')
        for (cx,cy),(x,y,w,h) in zip(centers,regions):
            if not (x<=cx<=x+w and y<=cy<=y+h):
                raise ValueError('eye center outside expected iris region')
    cracks=[s for s in cfg['shots'] if s.get('fx')=='bond_crack']
    if len(cracks)!=1: raise ValueError('v5 requires exactly one masked bond crack')
    crack=cracks[0]
    if float(crack.get('crack_alpha',0))<.8 or float(crack.get('crack_amplitude',0))<200:
        raise ValueError('bond crack must have visible alpha and amplitude')
    x,y,w,h=crack.get('fx_region',[0,0,0,0])
    if w>180 or h>420 or x<780 or x+w>1140 or y<20 or y+h>720:
        raise ValueError('bond crack mask must stay in central negative space above text')
    return True


def grafo_neon_v5(fx,duration,region=None,params=None):
    """V5 light integrates compact eye cores/spill and a masked branched crack."""
    params=params or {}
    if fx=='eye_pair':
        eyes=region or [[780,540],[1140,540]]
        cores=[f"exp(-pow((X-{int(x)})/8,2)-pow((Y-{int(y)})/6,2))" for x,y in eyes]
        uppers=[f"exp(-pow((X-{int(x)})/38,2)-pow((Y-{int(y)-13})/9,2))" for x,y in eyes]
        lowers=[f"exp(-pow((X-{int(x)})/34,2)-pow((Y-{int(y)+13})/10,2))" for x,y in eyes]
        pulse='(0.82+0.18*sin(2*PI*T/1.1))'
        core='+'.join(cores);upper='+'.join(uppers);lower='+'.join(lowers)
        layer=(f"[src]split=3[core_src][upper_src][lower_src];"
               f"[core_src]geq=r='255*({core})*{pulse}':g='8*({core})':b='10*({core})',"
               "gblur=sigma=0.8,format=gbrp[core];"
               f"[upper_src]geq=r='255*({upper})*{pulse}':g='9*({upper})':b='14*({upper})',"
               "gblur=sigma=6,format=gbrp[upper];"
               f"[lower_src]geq=r='230*({lower})*{pulse}':g='8*({lower})':b='12*({lower})',"
               "gblur=sigma=6,format=gbrp[lower];"
               "[upper][lower]blend=all_mode=screen:all_opacity=1[spill];"
               "[spill][core]blend=all_mode=screen:all_opacity=1,format=gbrp[light]")
        desc='two compact red iris core ellipses with subtle radial eyelid and face spill';opacity=.82
    elif fx=='bond_crack':
        x,y,w,h=region or [900,255,120,360]
        alpha=float(params.get('crack_alpha',.86));amp=float(params.get('crack_amplitude',245))
        # A short central diagonal with two gated branches. Every luminous pixel is
        # generated inside the crop, then padded into the verified negative-space mask.
        main=f"exp(-pow((X-({w}/2+0.10*(Y-{h}/2)))/4.2,2))"
        b1=f"exp(-pow((X-({w}/2-0.28*(Y-{h}*0.44)-12))/4.2,2))*between(Y,{h}*0.20,{h}*0.50)"
        b2=f"exp(-pow((X-({w}/2+0.32*(Y-{h}*0.60)+10))/4.2,2))*between(Y,{h}*0.56,{h}*0.86)"
        gate=f"between(Y,{h}*0.10,{h}*0.90)"
        energy=f"min(1,({main}*{gate}+0.95*{b1}+0.92*{b2}))*(0.94+0.06*sin(2*PI*T/0.72))"
        layer=(f"[src]crop={w}:{h}:{x}:{y},split=2[crack_src][halo_src];"
               f"[crack_src]geq=r='{amp}*{energy}':g='180*{energy}':b='255*{energy}',"
               "gblur=sigma=1.0,format=gbrp[crack];"
               f"[halo_src]geq=r='230*{energy}':g='36*{energy}':b='255*{energy}',"
               "gblur=sigma=6,format=gbrp[halo];"
               f"[halo][crack]blend=all_mode=screen:all_opacity=1,pad=1920:1080:{x}:{y}:black,format=gbrp[light]")
        desc='bright short animated branched diagonal crack confined to verified negative-space mask';opacity=alpha
    else:
        return grafo_neon_v4(fx,duration,region)
    return {'filter':layer+f";[base][light]blend=all_mode=screen:all_opacity={opacity},format=yuv420p,setsar=1[v]",'description':desc}


def grafo_neon_v4(fx,duration,region=None):
    """Anatomical V4 light: paired eyes, silhouette rim, or masked diagonal crack."""
    if fx=='eye_pair':
        eyes=region or [[830,405],[1090,405]]
        terms=[f"exp(-pow((X-{int(x)})/55,2)-pow((Y-{int(y)})/30,2))" for x,y in eyes]
        pulse="*(0.68+0.32*sin(2*PI*T/1.1))"
        layer=f"[src]geq=r='225*({'+'.join(terms)}){pulse}':g='0':b='3',gblur=sigma=6,format=gbrp[light]"
        desc='two small pulsing radial eye ellipses with anatomical skin spill';opacity=.54
    elif fx in {'loss_rim','silhouette_rim'}:
        color="r='val*0.62':g='val*0.30':b='val*1.35'" if fx=='loss_rim' else "r='val*0.45':g='val*0.22':b='val*1.30'"
        layer=f"[src]edgedetect=low=0.045:high=0.16,lutrgb={color},gblur=sigma=8.5,format=gbrp[light]"
        desc='blurred silhouette edge rim and local lightwrap, without rectangular scan';opacity=.46 if fx=='loss_rim' else .40
    elif fx=='bond_crack':
        x,y,w,h=region or [430,80,760,220]
        diag="exp(-pow((X-0.77*Y+3)/4,2))*(0.72+0.28*sin(2*PI*T/0.8))"
        layer=(f"[src]crop={w}:{h}:{x}:{y},geq=r='215*{diag}':g='35*{diag}':b='235*{diag}',"
               f"gblur=sigma=3,pad=1920:1080:{x}:{y}:black,format=gbrp[light]")
        desc='thin diagonal bond crack masked strictly to negative space between bodies';opacity=.56
    elif fx=='fire_lightwrap':
        layer=("[src]geq=r='190*exp(-pow((X-960)/760,4)-pow((Y-690)/360,2))*(0.72+0.28*sin(T*3.1))':"
               "g='18*exp(-pow((X-960)/760,4)-pow((Y-690)/360,2))':"
               "b='125*exp(-pow((X-960)/760,4)-pow((Y-690)/360,2))*(0.72+0.28*sin(T*3.1))',"
               "gblur=sigma=24,format=gbrp[light]")
        desc='preserved v3 violet red fire lightwrap';opacity=.60
    else: raise ValueError(f'unknown v4 environmental fx: {fx}')
    return {'filter':layer+f";[base][light]blend=all_mode=screen:all_opacity={opacity},format=yuv420p,setsar=1[v]",'description':desc}


def grafo_neon_ambiental(fx,duration,region=None):
    """RGB-only screen light tied to the image; no decorative side ornaments."""
    x,y,w,h=(region or [480,260,960,520]); d=max(.1,float(duration))
    if fx=='eye_pulse':
        # Animated elliptical field around the eyes; broad blur creates skin spill.
        layer=("[src]geq=r='210*exp(-pow((X-960)/430,2)-pow((Y-430)/145,2))*(0.62+0.38*sin(2*PI*T/1.15))':"
               "g='18*exp(-pow((X-960)/430,2)-pow((Y-430)/145,2))':"
               "b='24*exp(-pow((X-960)/430,2)-pow((Y-430)/145,2))',"
               "gblur=sigma=18,format=gbrp[light]")
        desc='pulsing red ellipse around Sharingan with visible skin spill'
        opacity=.58
    elif fx=='loss_sweep':
        layer=("[src]geq=r='42*exp(-pow((X-(T/"+str(d)+")*W)/300,2))':"
               "g='92*exp(-pow((X-(T/"+str(d)+")*W)/300,2))':"
               "b='205*exp(-pow((X-(T/"+str(d)+")*W)/300,2))',"
               "gblur=sigma=28,format=gbrp[light]")
        desc='visible blue purple gradient sweep across loss scene'
        opacity=.62
    elif fx=='silhouette_rim':
        layer=("[src]edgedetect=low=0.035:high=0.14,lutrgb=r='val*0.55':g='val*0.25':b='val*1.55',"
               "gblur=sigma=7.5,format=gbrp[light]")
        desc='visible violet silhouette rim extracted from image edges'
        opacity=.58
    elif fx=='bond_streak':
        layer=("[src]geq=r='205*exp(-pow((Y-(610+75*sin(T*2.2)))/28,2))*exp(-pow((X-960)/620,4))':"
               "g='45*exp(-pow((Y-(610+75*sin(T*2.2)))/28,2))*exp(-pow((X-960)/620,4))':"
               "b='235*exp(-pow((Y-(610+75*sin(T*2.2)))/28,2))*exp(-pow((X-960)/620,4))',"
               "gblur=sigma=10,format=gbrp[light]")
        desc='visible animated luminous bond streak between Sasuke and Naruto below faces'
        opacity=.68
    elif fx=='fire_lightwrap':
        layer=("[src]geq=r='190*exp(-pow((X-960)/760,4)-pow((Y-690)/360,2))*(0.72+0.28*sin(T*3.1))':"
               "g='18*exp(-pow((X-960)/760,4)-pow((Y-690)/360,2))':"
               "b='125*exp(-pow((X-960)/760,4)-pow((Y-690)/360,2))*(0.72+0.28*sin(T*3.1))',"
               "gblur=sigma=24,format=gbrp[light]")
        desc='visible violet red fire lightwrap across subject and environment, no crow overlay'
        opacity=.60
    else: raise ValueError(f'unknown environmental fx: {fx}')
    return {'filter':layer+f";[base][light]blend=all_mode=screen:all_opacity={opacity},format=yuv420p,setsar=1[v]",
            'description':desc}


def _executar_previa_v4(p,cfg):
    """V4/V5 preview with version-isolated outputs and strict technical QA."""
    from dataclasses import asdict
    import imagem
    ver=int(cfg.get('version',4)); validar_previa_v5(cfg) if ver==5 else validar_previa_v4(cfg)
    qa=p/f'qa/previa_v{ver}';qa.mkdir(parents=True,exist_ok=True)
    work=p/f'saidas/previa_work_v{ver}';work.mkdir(parents=True,exist_ok=True)
    fd=ROOT/'assets/fontes/cinzel'
    assert (fd/'Cinzel.ttf').exists() and 'SIL OPEN FONT LICENSE' in (fd/'OFL.txt').read_text(encoding='utf-8')
    origin=float(cfg['start']);duration=float(cfg['end'])-origin
    canonical=json.loads((p/cfg['canonical']).read_text(encoding='utf-8'))
    lines=canonical['lines'][:4];words=[w for line in lines for w in line['words']]
    assert [norm(x['text']) for x in lines]==[norm(x) for x in cfg['lyrics']]
    ass=gerar_ass_previa_v4(words,origin,duration,cfg['phrase_blocks'])
    af=work/f'lyrics_v{ver}.ass';af.write_text(ass,encoding='utf-8')
    assert '\\,' not in ass and ass.count('Style:')>=3
    parts=[];timeline=[]
    for i,s in enumerate(cfg['shots']):
        a=round(float(s['start'])*30);b=round(float(s['end'])*30);n=b-a
        assert n>0 and (a==0 if i==0 else a==round(float(cfg['shots'][i-1]['end'])*30))
        out=work/f'shot_{i:02}.mp4';motion=s.get('motion','push')
        if motion=='left': cx="42+20*sin(t*0.9)"
        elif motion=='right': cx="38-18*sin(t*0.8)"
        else: cx="40+12*sin(t*1.1)"
        base=normalize_video()+f",scale=2000:1125,crop=1920:1080:x='{cx}':y=22,setsar=1,setpts=N/(30*TB)"
        fx=(grafo_neon_v5(s['fx'],n/30,s.get('fx_region'),s)
            if ver==5 else grafo_neon_v4(s['fx'],n/30,s.get('fx_region')))
        if s.get('hard_text_safe'):
            # Full-width picture ends above the lyric band; no gradient/backing crosses bodies.
            lit=fx['filter'].replace('setsar=1[v]','setsar=1[lit]')
            graph=(f"[0:v]{base},format=gbrp,split=2[base][src];"+lit+
                   ";[lit]crop=1920:720:0:0,pad=1920:1080:0:0:black,format=yuv420p,setsar=1[v]")
        elif s.get('text_safe_inset'):
            # Light the scene before layout. Edgedetect after inset would illuminate
            # the rectangular layout seam and manufacture a horizontal flare.
            lit=fx['filter'].replace('setsar=1[v]','setsar=1[lit]')
            graph=(f"[0:v]{base},format=gbrp,split=2[base][src];"+lit+
                   ";[lit]split=2[flat0][fg0];[flat0]gblur=sigma=42,"
                   "lutrgb=r='val*0.08':g='val*0.08':b='val*0.12'[bg];"
                   "[fg0]format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
                   "a='255*max(0,min(1,(980-Y)/220))'[fg];"
                   "[bg][fg]overlay=0:-100,format=yuv420p,setsar=1[v]")
        elif s.get('safe_inset'):
            # Preserve the V3-approved fire composition and negative space.
            graph=(f"[0:v]{base},split=2[bg0][fg0];[bg0]gblur=sigma=34[bg];"
                   "[fg0]scale=1400:788[fg];[bg][fg]overlay=260:0,format=gbrp,"
                   "split=2[base][src];"+fx['filter'])
        else:
            graph=f"[0:v]{base},format=gbrp,split=2[base][src];"+fx['filter']
        rd.encode(str(out),['-ss',str(s['src']),'-i',str(p/'clips_raw'/s['clip'])],
                  filtro_complexo=graph,mapa=['-map','[v]'],args_audio=['-an'],
                  args_extra=['-frames:v',str(n),'-r','30'],silencioso=True,cq='17')
        assert int(probe(out)['streams'][0]['nb_frames'])==n
        assert rd.tem_nvenc()  # video_args ja bloqueia CPU
        parts.append(out);timeline.append(dict(**s,frames=n,fx_description=fx['description']))
        print('v4 shot',i,s['meaning'],flush=True)
    assert b==round(duration*30)
    listing=work/'concat.txt';listing.write_text(''.join("file '"+x.name+"'\n" for x in parts),encoding='utf-8')
    raw=work/'raw.mp4';subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(raw)],check=True)
    dest=p/'saidas'/cfg['output']
    graph=(f"[0:v]setsar=1,fps=30,setpts=N/(30*TB),ass='{af.relative_to(ROOT).as_posix()}':"
           f"fontsdir=assets/fontes/cinzel,format=yuv420p[v];"
           f"[1:a]atrim=start={origin}:end={cfg['end']},asetpts=PTS-STARTPTS,"
           f"afade=t=in:d=0.12,afade=t=out:st={duration-0.35}:d=0.35,"
           "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")
    rd.encode(str(dest),['-reinit_filter','0','-i',str(raw),'-i',str(p/cfg['audio'])],
              filtro_complexo=graph,mapa=['-map','[v]','-map','[a]'],
              args_extra=['-r','30','-fps_mode','cfr'],cq='17')
    decode=subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(dest),'-f','null','-'],capture_output=True,text=True)
    (qa/'decode.log').write_text(decode.stderr,encoding='utf-8');assert decode.returncode==0
    info=probe(dest);dump(qa/'probe.json',info)
    v=next(x for x in info['streams'] if x['codec_type']=='video');au=next(x for x in info['streams'] if x['codec_type']=='audio')
    assert v['pix_fmt']=='yuv420p' and v['sample_aspect_ratio']=='1:1' and v['avg_frame_rate']=='30/1'
    assert int(v['nb_frames'])==round(duration*30)
    assert abs(float(v['duration'])-duration)<.05 and abs(float(au['duration'])-duration)<.05
    assert abs(float(v['duration'])-float(au['duration']))<.05
    gate=asdict(imagem.analisar(dest,qa));dump(qa/'image_gate.json',gate);assert gate['aprovado'],gate['motivos']
    dump(qa/'timeline.json',{'audio_window':[origin,cfg['end']],'segments':timeline})
    dump(qa/'lyrics_audit.json',{'lines':[x['text'] for x in lines],'canonical_words':len(words),
         'timed_words':sum(w.get('start') is not None for w in words),'gaps':[w['word'] for w in words if w.get('start') is None],
         'asr_repeated':False,'note':'Canonical 25/25 preview timing preserved; no new ASR.'})
    mids=[(float(s['start'])+float(s['end']))/2 for s in cfg['shots']]
    sheets(dest,qa,mids,'contact_full')
    for i,s in enumerate(cfg['shots']):
        a=float(s['start']);z=float(s['end']);span=z-a
        sheets(dest,qa,[a+span*x for x in (.18,.38,.58,.78)],f'motion_{i:02}')
    loud=subprocess.run(['ffmpeg','-hide_banner','-i',str(dest),'-af','loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True)
    (qa/'loudness.log').write_text(loud.stderr,encoding='utf-8')
    print(json.dumps({'output':str(dest),'duration':duration,'frames':v['nb_frames'],'image_gate':gate},ensure_ascii=False));return 0


def _executar_previa_v3(p,cfg):
    """Nine-cut semantic preview with image-emissive neon progression."""
    from dataclasses import asdict
    import imagem
    validar_previa_v3(cfg)
    qa=p/'qa/previa_v3';qa.mkdir(parents=True,exist_ok=True)
    work=p/'saidas/previa_work_v3';work.mkdir(parents=True,exist_ok=True)
    fd=ROOT/'assets/fontes/cinzel'
    assert (fd/'Cinzel.ttf').exists() and 'SIL OPEN FONT LICENSE' in (fd/'OFL.txt').read_text(encoding='utf-8')
    origin=float(cfg['start']);duration=float(cfg['end'])-origin
    canonical=json.loads((p/cfg['canonical']).read_text(encoding='utf-8'))
    lines=canonical['lines'][:4];words=[w for line in lines for w in line['words']]
    assert [norm(x['text']) for x in lines]==[norm(x) for x in cfg['lyrics']]
    ass=gerar_ass_previa_v2(words,origin,duration,cfg['phrase_blocks'])
    af=work/'lyrics_v3.ass';af.write_text(ass,encoding='utf-8')
    assert '\\,' not in ass and ass.count('Style:')>=3
    parts=[];timeline=[]
    for i,s in enumerate(cfg['shots']):
        a=round(float(s['start'])*30);b=round(float(s['end'])*30);n=b-a
        out=work/f'shot_{i:02}.mp4';motion=s.get('motion','push')
        if motion=='left': cx="42+26*sin(t*0.9)"
        elif motion=='right': cx="38-24*sin(t*0.8)"
        else: cx="40+15*sin(t*1.1)"
        base=normalize_video()+f",scale=2000:1125,crop=1920:1080:x='{cx}':y=22,setsar=1,setpts=N/(30*TB)"
        fx=grafo_neon_ambiental(s['fx'],n/30,s.get('fx_region'))
        if s.get('safe_inset'):
            # Preserve the whole final image above a blurred extension, leaving real
            # negative space for lyrics instead of covering hair or adding an empty band.
            graph=(f"[0:v]{base},split=2[bg0][fg0];"
                   "[bg0]gblur=sigma=34[bg];[fg0]scale=1400:788[fg];"
                   "[bg][fg]overlay=260:0,format=gbrp,split=2[base][src];"+fx['filter'])
        else:
            graph=f"[0:v]{base},format=gbrp,split=2[base][src];"+fx['filter']
        rd.encode(str(out),['-ss',str(s['src']),'-i',str(p/'clips_raw'/s['clip'])],
                  filtro_complexo=graph,mapa=['-map','[v]'],args_audio=['-an'],
                  args_extra=['-frames:v',str(n),'-r','30'],silencioso=True,cq='17')
        assert int(probe(out)['streams'][0]['nb_frames'])==n
        assert rd.tem_nvenc()  # video_args ja bloqueia CPU
        parts.append(out);timeline.append(dict(**s,frames=n,fx_description=fx['description']))
        print('v3 shot',i,s['meaning'],flush=True)
    assert b==round(duration*30)
    listing=work/'concat.txt';listing.write_text(''.join("file '"+x.name+"'\n" for x in parts),encoding='utf-8')
    raw=work/'raw.mp4';subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(raw)],check=True)
    dest=p/'saidas'/cfg['output']
    graph=(f"[0:v]setsar=1,fps=30,setpts=N/(30*TB),ass='{af.relative_to(ROOT).as_posix()}':"
           f"fontsdir=assets/fontes/cinzel,format=yuv420p[v];"
           f"[1:a]atrim=start={origin}:end={cfg['end']},asetpts=PTS-STARTPTS,"
           f"afade=t=in:d=0.12,afade=t=out:st={duration-0.35}:d=0.35,"
           "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")
    rd.encode(str(dest),['-reinit_filter','0','-i',str(raw),'-i',str(p/cfg['audio'])],
              filtro_complexo=graph,mapa=['-map','[v]','-map','[a]'],
              args_extra=['-r','30','-fps_mode','cfr'],cq='17')
    decode=subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(dest),'-f','null','-'],capture_output=True,text=True)
    (qa/'decode.log').write_text(decode.stderr,encoding='utf-8');assert decode.returncode==0
    info=probe(dest);dump(qa/'probe.json',info);v=next(x for x in info['streams'] if x['codec_type']=='video');au=next(x for x in info['streams'] if x['codec_type']=='audio')
    assert v['pix_fmt']=='yuv420p' and v['sample_aspect_ratio']=='1:1' and v['avg_frame_rate']=='30/1'
    assert int(v['nb_frames'])==round(duration*30) and abs(float(v['duration'])-duration)<.05 and abs(float(au['duration'])-duration)<.05
    gate=asdict(imagem.analisar(dest,qa));dump(qa/'image_gate.json',gate);assert gate['aprovado'],gate['motivos']
    dump(qa/'timeline.json',{'audio_window':[origin,cfg['end']],'segments':timeline})
    dump(qa/'lyrics_audit.json',{'lines':[x['text'] for x in lines],'canonical_words':len(words),
         'timed_words':sum(w.get('start') is not None for w in words),'gaps':[w['word'] for w in words if w.get('start') is None]})
    mids=[(float(s['start'])+float(s['end']))/2 for s in cfg['shots']]
    sheets(dest,qa,mids,'contact_full')
    for i,s in enumerate(cfg['shots']):
        a=float(s['start']);z=float(s['end']);span=z-a
        samples=[a+span*x for x in (.18,.38,.58,.78)]
        sheets(dest,qa,samples,f'motion_{i:02}')
    loud=subprocess.run(['ffmpeg','-hide_banner','-i',str(dest),'-af','loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True)
    (qa/'loudness.log').write_text(loud.stderr,encoding='utf-8')
    print(json.dumps({'output':str(dest),'duration':duration,'frames':v['nb_frames'],'image_gate':gate},ensure_ascii=False));return 0


def _executar_previa_v2(p,cfg):
    """Canonical-lyrics semantic preview with localized scene-derived light."""
    from dataclasses import asdict
    import imagem
    qa=p/'qa/previa_v2';qa.mkdir(parents=True,exist_ok=True)
    work=p/'saidas/previa_work_v2';work.mkdir(parents=True,exist_ok=True)
    fd=ROOT/'assets/fontes/cinzel'
    assert (fd/'Cinzel.ttf').exists() and 'SIL OPEN FONT LICENSE' in (fd/'OFL.txt').read_text(encoding='utf-8')
    origin=float(cfg['start']);duration=float(cfg['end'])-origin
    canonical=json.loads((p/cfg['canonical']).read_text(encoding='utf-8'))
    lines=canonical['lines'][:4];words=[w for line in lines for w in line['words']]
    assert [norm(x['text']) for x in lines]==[norm(x) for x in cfg['lyrics']]
    validar_blocos_previa(cfg)
    ass=gerar_ass_previa_v2(words,origin,duration,cfg['phrase_blocks'])
    af=work/'lyrics_v2.ass';af.write_text(ass,encoding='utf-8')
    assert '\\,' not in ass and ass.count('Style:')>=3
    parts=[];timeline=[]
    for i,s in enumerate(cfg['shots']):
        a=round(float(s['start'])*30);b=round(float(s['end'])*30);n=b-a
        assert n>0 and (a==0 if i==0 else a==round(float(cfg['shots'][i-1]['end'])*30))
        out=work/f'shot_{i:02}.mp4';x,y,w,h=s['fx_region']
        # Different camera drift per scene, plus edge light extracted only from the
        # semantic region (eyes/Chidori/Amaterasu), never generic side ornaments.
        motion=s.get('motion','push')
        if motion=='left': cx="42+30*sin(t*0.9)"
        elif motion=='right': cx="38-28*sin(t*0.8)"
        else: cx="40+18*sin(t*1.1)"
        base=normalize_video()+f",scale=2000:1125,crop=1920:1080:x='{cx}':y=22,setsar=1,setpts=N/(30*TB)"
        color=s.get('fx_color','cyan')
        lut={'red':'r=val:g=val*0.05:b=val*0.05','cyan':'r=val*0.08:g=val*0.75:b=val','purple':'r=val*0.65:g=val*0.12:b=val'}[color]
        graph=(f"[0:v]{base},format=gbrp,split=2[base][src];"
               f"[src]crop={w}:{h}:{x}:{y},edgedetect=low=0.10:high=0.28,"
               f"lutrgb={lut},gblur=sigma=2.6,"
               f"pad=1920:1080:{x}:{y}:black,format=gbrp[e];"
               f"[base][e]blend=all_mode=screen:all_opacity={s.get('fx_opacity',.34)},"
               "format=yuv420p,setsar=1[v]")
        rd.encode(str(out),['-ss',str(s['src']),'-i',str(p/'clips_raw'/s['clip'])],
                  filtro_complexo=graph,mapa=['-map','[v]'],args_audio=['-an'],
                  args_extra=['-frames:v',str(n),'-r','30'],silencioso=True,cq='17')
        assert int(probe(out)['streams'][0]['nb_frames'])==n
        assert rd.tem_nvenc()  # video_args ja bloqueia CPU
        parts.append(out);timeline.append(dict(**s,frames=n));print('v2 shot',i,s['meaning'],flush=True)
    assert b==round(duration*30)
    listing=work/'concat.txt';listing.write_text(''.join("file '"+x.name+"'\n" for x in parts),encoding='utf-8')
    raw=work/'raw.mp4';subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(raw)],check=True)
    dest=p/'saidas'/cfg['output']
    graph=(f"[0:v]setsar=1,fps=30,setpts=N/(30*TB),ass='{af.relative_to(ROOT).as_posix()}':"
           f"fontsdir=assets/fontes/cinzel,format=yuv420p[v];"
           f"[1:a]atrim=start={origin}:end={cfg['end']},asetpts=PTS-STARTPTS,"
           f"afade=t=in:d=0.12,afade=t=out:st={duration-0.35}:d=0.35,"
           "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]")
    rd.encode(str(dest),['-reinit_filter','0','-i',str(raw),'-i',str(p/cfg['audio'])],
              filtro_complexo=graph,mapa=['-map','[v]','-map','[a]'],
              args_extra=['-r','30','-fps_mode','cfr'],cq='17')
    decode=subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(dest),'-f','null','-'],capture_output=True,text=True)
    (qa/'decode.log').write_text(decode.stderr,encoding='utf-8');assert decode.returncode==0
    info=probe(dest);dump(qa/'probe.json',info);v=next(x for x in info['streams'] if x['codec_type']=='video');au=next(x for x in info['streams'] if x['codec_type']=='audio')
    assert v['pix_fmt']=='yuv420p' and v['sample_aspect_ratio']=='1:1' and v['avg_frame_rate']=='30/1'
    assert int(v['nb_frames'])==round(duration*30) and abs(float(v['duration'])-duration)<.05 and abs(float(au['duration'])-duration)<.05
    gate=asdict(imagem.analisar(dest,qa));dump(qa/'image_gate.json',gate);assert gate['aprovado'],gate['motivos']
    dump(qa/'timeline.json',{'audio_window':[origin,cfg['end']],'segments':timeline})
    dump(qa/'lyrics_audit.json',{'lines':[x['text'] for x in lines],'canonical_words':len(words),
         'timed_words':sum(w.get('start') is not None for w in words),'gaps':[w['word'] for w in words if w.get('start') is None],
         'note':'The initial E in line 4 is retained visibly but has no fabricated individual onset; block activates on agora.'})
    # One exact frame per editorial shot for diversity; reveal samples stay inside events.
    sheets(dest,qa,[1.2,3.6,6.4,10.0,13.4,17.0,20.2],'diversity')
    sheets(dest,qa,[.48,.62,.82,1.05,13.18,13.34,13.52,13.76,19.02,19.16,19.34,19.72],'motion')
    loud=subprocess.run(['ffmpeg','-hide_banner','-i',str(dest),'-af','loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True)
    (qa/'loudness.log').write_text(loud.stderr,encoding='utf-8')
    print(json.dumps({'output':str(dest),'duration':duration,'frames':v['nb_frames'],'image_gate':gate},ensure_ascii=False));return 0


def executar_previa(slug):
    """Explicit semantic preview; no rotation or intersection-based lyric loss."""
    from dataclasses import asdict
    import imagem
    p=ROOT/'projetos'/slug
    cfg=json.loads((p/'previa.json').read_text(encoding='utf-8'))
    if cfg.get('version') in {4, 5}:
        return _executar_previa_v4(p,cfg)
    if cfg.get('version') == 3:
        return _executar_previa_v3(p,cfg)
    if cfg.get('version') == 2:
        return _executar_previa_v2(p,cfg)
    qa=p/'qa/previa';qa.mkdir(parents=True,exist_ok=True)
    work=p/'saidas/previa_work';work.mkdir(parents=True,exist_ok=True)
    fd=ROOT/'assets/fontes/cinzel';fd.mkdir(parents=True,exist_ok=True)
    base='https://raw.githubusercontent.com/google/fonts/main/ofl/cinzel/'
    for remote,local in [('Cinzel%5Bwght%5D.ttf','Cinzel.ttf'),('OFL.txt','OFL.txt')]:
        if not (fd/local).exists(): urllib.request.urlretrieve(base+remote,fd/local)
    assert 'SIL OPEN FONT LICENSE' in (fd/'OFL.txt').read_text(encoding='utf-8')
    dump(fd/'evidence.json',dict(source=base+'Cinzel%5Bwght%5D.ttf',license_url=base+'OFL.txt',sha256=hashlib.sha256((fd/'Cinzel.ttf').read_bytes()).hexdigest()))
    header=HEADER.replace('Barlow SemiBold,64','Cinzel,110').replace('Anton,155','Cinzel,155').replace('&H90000000,0,0,0,0,100,100,1,','&H90000000,-1,0,0,0,100,100,1,')
    origin=cfg['start'];duration=cfg['end']-origin
    words=json.loads((p/cfg['words']).read_text(encoding='utf-8'))['words']
    expected=' '.join(cfg['lyrics']).split()
    assert [norm(w['word']) for w in words]==[norm(w) for w in expected], 'Incomplete lyric coverage'
    ass=header;idx=0
    ass+=event(0,duration,r'{\an7\pos(0,0)\p1\bord0\shad0\blur22\c&H00100808&\alpha&H38&}m 130 820 l 1790 820 l 1790 1030 l 130 1030',layer=0)
    for phrase in cfg['phrases']:
        group=words[idx:idx+phrase];idx+=phrase
        for j,w in enumerate(group):
            a=w['start']-origin;b=min(w['end']+.08,group[j+1]['start'] if j+1<len(group) else w['end']+.12)-origin
            prior=' '.join(x['word'].strip().upper().strip('.,') for x in group[:j])
            current=w['word'].strip().upper().strip('.,')
            color='&H005050FF&' if current in ['VERMELHOS','DOR','CORTEI','QUEIMAR'] else '&H00FFD080&'
            common=r'{\an2\pos(960,970)\fscx108\fscy108\t(0,150,\fscx100\fscy100)}'
            text=(r'{\c&H00C8C8D0&}'+prior+' ' if prior else '')+r'{\b1\c&H00FFFFFF&}'+current
            glow=common+r'{\blur9\bord5\shad0\3c'+color+r'\c'+color+'}'+(prior+' ' if prior else '')+current
            ass+=event(a,b,glow,layer=1)+event(a,b,common+r'{\blur0\bord2.4\shad1.5}'+text,layer=2)
            width=min(1400,max(260,len((prior+' '+current).strip())*43));x=960-width//2;y=988
            for blur,bord,layer in [(9,5,0),(.3,1,1)]:
                tag=r'{\an7\pos(0,0)\p1\shad0\blur'+str(blur)+r'\bord'+str(bord)+r'\c'+color+r'\3c'+color+f'\\clip({x},970,{x},1010)\\t(0,200,\\clip({x},970,{x+width},1010))'+'}'
                ass+=event(a,b,tag+f'm {x} {y} l {x+width} {y} l {x+width} {y+2} l {x} {y+2}',layer=layer)
    assert idx==len(words)
    af=work/'lyrics.ass';af.write_text(ass,encoding='utf-8')
    parts=[]
    for i,s in enumerate(cfg['shots']):
        a=round(s['start']*30);b=round(s['end']*30);n=b-a
        assert n>0 and (i==0 and a==0 or i>0 and a==round(cfg['shots'][i-1]['end']*30))
        out=work/f'shot_{i:02}.mp4'
        # Animated vector energy follows the image perimeter, outside facial safe area.
        fx=header;color=s.get('color','&H00FF8050&')
        for k in range(int(n/30/.65)+1):
            t=k*.65
            for side in [0,1]:
                x=160 if side==0 else 1760;sign=1 if side==0 else -1
                path=f'm {x} 800 b {x+sign*130} 690 {x-sign*85} 570 {x+sign*65} 450 b {x+sign*180} 300 {x-sign*50} 210 {x+sign*130} 95'
                for blur,bord,layer in [(18,14,0),(.4,3.5,1)]:
                    tag=r'{\an7\pos(0,0)\p1\1a&HFF&\shad0\3c'+color+r'\bord'+str(bord)+r'\blur'+str(blur)+r'\fad(30,160)\clip(0,790,1920,810)\t(0,470,\clip(0,60,1920,810))}'
                    fx+=event(t,min(t+.6,n/30),tag+path,layer=layer)
        fxfile=work/f'fx_{i:02}.ass';fxfile.write_text(fx,encoding='utf-8')
        vf=normalize_video()+',setpts=N/(30*TB),format=yuv420p'
        graph=f"[0:v]{vf},format=gbrp,split=2[base][edge];[edge]scale=960:540,edgedetect=low=0.12:high=0.3,format=gbrp,lutrgb=r=val:g=val*0.22:b=val*0.9,drawbox=x=200:y=35:w=560:h=390:color=black:t=fill,gblur=sigma=2,scale=1920:1080,format=gbrp[e];[base][e]blend=all_mode=screen:all_opacity=0.45,format=yuv420p,ass='{fxfile.relative_to(ROOT).as_posix()}':fontsdir=assets/fontes/cinzel,setsar=1,format=yuv420p[v]"
        rd.encode(str(out),['-ss',str(s['src']),'-i',str(p/'clips_raw'/s['clip'])],filtro_complexo=graph,mapa=['-map','[v]'],args_audio=['-an'],args_extra=['-frames:v',str(n),'-r','30'],silencioso=True,cq='17')
        assert int(probe(out)['streams'][0]['nb_frames'])==n
        assert rd.tem_nvenc()  # video_args ja bloqueia CPU
        parts.append(out);print('semantic shot',i,s['meaning'],flush=True)
    assert b==round(duration*30)
    listing=work/'concat.txt';listing.write_text(''.join("file '"+x.name+"'\n" for x in parts),encoding='utf-8')
    raw=work/'raw.mp4';subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(raw)],check=True)
    dest=p/'saidas'/cfg['output']
    graph=f"[0:v]setsar=1,fps=30,setpts=N/(30*TB),ass='{af.relative_to(ROOT).as_posix()}':fontsdir=assets/fontes/cinzel,format=yuv420p[v];[1:a]atrim=start={origin}:end={cfg['end']},asetpts=PTS-STARTPTS,afade=t=in:d=0.12,afade=t=out:st={duration-.35}:d=0.35,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]"
    rd.encode(str(dest),['-reinit_filter','0','-i',str(raw),'-i',str(p/cfg['audio'])],filtro_complexo=graph,mapa=['-map','[v]','-map','[a]'],args_extra=['-r','30','-fps_mode','cfr'],cq='17')
    r=subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(dest),'-f','null','-'],capture_output=True,text=True)
    (qa/'decode.log').write_text(r.stderr,encoding='utf-8');assert r.returncode==0
    info=probe(dest);dump(qa/'probe.json',info)
    v=next(x for x in info['streams'] if x['codec_type']=='video');audio=next(x for x in info['streams'] if x['codec_type']=='audio')
    assert int(v['nb_frames'])==round(duration*30) and abs(float(v['duration'])-duration)<.05 and abs(float(audio['duration'])-duration)<.05
    gate=asdict(imagem.analisar(dest,qa));dump(qa/'image_gate.json',gate)
    old=json.loads((p/'entradas/transcricao.json').read_text(encoding='utf-8'))['words'];deltas=[]
    for w in words:
        matches=[o for o in old if norm(o['word'])==norm(w['word']) and abs(o['start']-w['start'])<1]
        if matches:deltas.append(min(abs(o['start']-w['start']) for o in matches))
    dump(qa/'sync.json',dict(words=len(words),expected=len(expected),coverage=len(words)/len(expected),median=float(np.median(deltas)),p90=float(np.percentile(deltas,90)),max=float(max(deltas)),method='Chunk vocal ASR vs previous full-mix ASR; no omissions. Not phonetic gold standard.',thresholds=dict(median=.15,p90=.30),passed=bool(np.median(deltas)<=.15 and np.percentile(deltas,90)<=.30)))
    sheets(dest,qa,[.6,1.8,3.6,6.2,8.5,10.8,13.3,14.7,17.7,19.8,21.3],'preview')
    sheets(dest,qa,[1.05,1.15,1.3,1.5,14.05,14.15,14.3,14.5],'motion')
    r=subprocess.run(['ffmpeg','-hide_banner','-i',str(dest),'-af','loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True)
    (qa/'loudness.log').write_text(r.stderr,encoding='utf-8')
    print(json.dumps(dict(output=str(dest),duration=duration,frames=v['nb_frames'],image_gate=gate),ensure_ascii=False));return 0


def executar(slug):
    from dataclasses import asdict
    import imagem
    p=ROOT/'projetos'/slug;cfg=json.loads((p/'revisao.json').read_text(encoding='utf-8'));qa=p/'qa/revisao';qa.mkdir(parents=True,exist_ok=True)
    fonts();ass=subtitles(p,cfg,qa);peaks=analyze_music(p,cfg,qa)
    dest,shots=render(p,cfg,qa,ass,peaks)
    result=subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(dest),'-f','null','-'],capture_output=True,text=True)
    (qa/'decode.log').write_text(result.stderr,encoding='utf-8')
    info=probe(dest);v=next(s for s in info['streams'] if s['codec_type']=='video');a=next(s for s in info['streams'] if s['codec_type']=='audio')
    technical=dict(decode_exit=result.returncode,pix_fmt=v['pix_fmt'],sar=v['sample_aspect_ratio'],fps=v['avg_frame_rate'],video_duration=v['duration'],audio_duration=a['duration'],frames=v['nb_frames'],encoder='h264_nvenc p7 via render_dispatch',master=str(dest))
    dump(qa/'technical.json',technical)
    assert result.returncode==0 and v['pix_fmt']=='yuv420p' and v['sample_aspect_ratio']=='1:1' and v['avg_frame_rate']=='30/1'
    assert abs(float(v['duration'])-float(a['duration']))<.05
    image_gate=imagem.analisar(dest,qa,excluir_intro=10.0)
    dump(qa/'image_gate.json',asdict(image_gate))
    if not image_gate.aprovado:
        raise RuntimeError('QA de imagem reprovado: ' + '; '.join(image_gate.motivos))
    dur=float(v['duration']);sheets(dest,qa,list(np.arange(0,dur,4))+[dur-.1],'full')
    for i,s in enumerate([s for s in shots if s['impact']]):
        sheets(dest,qa,[10+s['start']+x for x in [0,.1,.25,.5,.8]],f'take_{i:02}')
    r=subprocess.run(['ffmpeg','-hide_banner','-i',str(dest),'-af','loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True)
    (qa/'loudness.log').write_text(r.stderr,encoding='utf-8')
    print(json.dumps(technical,indent=2));return 0
