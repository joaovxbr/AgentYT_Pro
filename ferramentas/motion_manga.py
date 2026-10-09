"""Reusable offline motion-manga take renderer. Entry: estudio.py motion-manga SLUG.
Configuration/assets belong to the project; no network or publishing path.
"""
from pathlib import Path
import json, subprocess
import cv2
import numpy as np
from PIL import Image
from paralaxe_3d import reconstruir_fundo, compor_profundidade
from paineis_manga import mascaras_diagonais
from revisao_master import ROOT, HEADER, event, dump, probe, sheets
import render_dispatch as rd


def desenhar_rinnegan_fx(canvas, center_xy, radius, u, tomoe_count=6):
    """Procedural Rinnegan overlay with concentric rings, purple glow, and orbiting tomoes."""
    cx, cy = int(center_xy[0]), int(center_xy[1])
    h, w = canvas.shape[:2]
    overlay = np.zeros((h, w, 3), dtype=np.float32)
    alpha_mask = np.zeros((h, w), dtype=np.float32)
    
    # Outer to inner rings
    ring_radii = [radius * f for f in [1.0, 0.78, 0.58, 0.38, 0.20]]
    # Purple/violet base color: R~170, G~80, B~240
    color_ring = np.array([240, 80, 180], dtype=np.float32) # BGR or RGB depending on caller, assuming RGB: [180, 80, 240]
    rgb_ring = np.array([190, 70, 245], dtype=np.float32)
    
    # Radial glow around eye
    y_coords, x_coords = np.ogrid[:h, :w]
    dist_sq = (x_coords - cx) ** 2 + (y_coords - cy) ** 2
    dist = np.sqrt(dist_sq)
    
    glow = np.clip(1.0 - (dist / (radius * 1.5)), 0, 1) ** 2
    pulse = 0.85 + 0.15 * np.sin(u * np.pi * 4)
    
    # Draw concentric ripples
    cv2.circle(canvas, (cx, cy), int(ring_radii[4]), (40, 20, 50), -1) # Dark pupil
    for r_cur in ring_radii:
        r_int = max(2, int(r_cur))
        cv2.circle(canvas, (cx, cy), r_int, (180, 60, 235), 2, cv2.LINE_AA)
        
    # Orbiting tomoes on the 2nd and 3rd rings
    # 6 tomoes total: 3 on middle ring (r=0.78), 3 on inner ring (r=0.58) or 6 distributed
    base_angle = u * 2 * np.pi
    rings_for_tomoe = [ring_radii[1], ring_radii[2]]
    tomoe_per_ring = tomoe_count // len(rings_for_tomoe)
    
    for ring_idx, r_t in enumerate(rings_for_tomoe):
        for k in range(tomoe_per_ring):
            ang = base_angle * (1.0 if ring_idx % 2 == 0 else -0.8) + (k * 2 * np.pi / tomoe_per_ring)
            tx = int(cx + r_t * np.cos(ang))
            ty = int(cy + r_t * np.sin(ang))
            if 0 <= tx < w and 0 <= ty < h:
                # Tomoe head
                cv2.circle(canvas, (tx, ty), max(2, int(radius * 0.065)), (25, 10, 30), -1, cv2.LINE_AA)
                # Tomoe tail curve
                tail_ang = ang + 0.6
                tail_x = int(tx + radius * 0.07 * np.cos(tail_ang))
                tail_y = int(ty + radius * 0.07 * np.sin(tail_ang))
                cv2.line(canvas, (tx, ty), (tail_x, tail_y), (25, 10, 30), 2, cv2.LINE_AA)

    # Add localized purple aura bloom
    aura = np.stack([glow * rgb_ring[0], glow * rgb_ring[1], glow * rgb_ring[2]], axis=2) * (0.35 * pulse)
    canvas = np.clip(canvas.astype(np.float32) + aura, 0, 255).astype(np.uint8)
    return canvas


def efeito_amenotejikara_shatter(canvas, u, seed=42):
    """Dimensional shatter/glitch displacement: breaks frame into Voronoi/geometric polygonal shards."""
    h, w = canvas.shape[:2]
    out = canvas.copy()
    rng = np.random.RandomState(seed + int(u * 15))
    
    num_shards = 16
    centers = rng.randint(0, [w, h], size=(num_shards, 2))
    
    # Calculate shard displacements
    # Peak displacement around u=0.5, creating spatial warp
    disp_mag = np.sin(u * np.pi) * 35.0
    
    # Grid slices for robust vectorized shattering
    step_y = max(16, h // 6)
    step_x = max(16, w // 8)
    
    for y0 in range(0, h, step_y):
        for x0 in range(0, w, step_x):
            y1 = min(h, y0 + step_y)
            x1 = min(w, x0 + step_x)
            # Find closest center
            c_idx = np.argmin(np.sum((centers - [(x0+x1)//2, (y0+y1)//2])**2, axis=1))
            shard_rng = np.random.RandomState(seed + c_idx)
            dx = int(shard_rng.uniform(-disp_mag, disp_mag))
            dy = int(shard_rng.uniform(-disp_mag * 0.6, disp_mag * 0.6))
            
            # Warp region
            src_y0 = np.clip(y0 + dy, 0, h - 1)
            src_y1 = np.clip(y1 + dy, 0, h)
            src_x0 = np.clip(x0 + dx, 0, w - 1)
            src_x1 = np.clip(x1 + dx, 0, w)
            
            patch = cv2.resize(canvas[src_y0:src_y1, src_x0:src_x1], (x1 - x0, y1 - y0))
            out[y0:y1, x0:x1] = patch
            # Draw dimensional crack on border
            if disp_mag > 8:
                cv2.line(out, (x0, y0), (x1, y0), (220, 180, 255), 1, cv2.LINE_AA)
                cv2.line(out, (x0, y0), (x0, y1), (220, 180, 255), 1, cv2.LINE_AA)
                
    # Add subtle chromatic aberration on edges during dimension break
    if disp_mag > 10:
        shift = int(disp_mag * 0.25)
        b_channel = np.roll(out[:, :, 2], shift, axis=1) # R/B split
        out[:, :, 2] = b_channel
    return out


def efeito_flecha_susanoo(canvas, u):
    """Susanoo piercing arrow 2.5D: rushes towards screen breaking frame borders."""
    h, w = canvas.shape[:2]
    # Trajectory relative to frame size (w, h)
    p = u ** 2.2
    start_pos = np.array([w * 0.25, h * 0.35])
    target_pos = np.array([w * 0.70, h * 0.65])
    
    cur_pos = start_pos + (target_pos - start_pos) * p
    cx, cy = int(cur_pos[0]), int(cur_pos[1])
    
    # Scale relative to width
    scale = (0.2 + 2.8 * p) * (w / 1920.0)
    length = max(20, int(280 * scale))
    width = max(3, int(18 * scale))
    
    angle = np.arctan2(target_pos[1] - start_pos[1], target_pos[0] - start_pos[0])
    cos_a, sin_a = np.cos(angle), np.sin(angle)
    
    # Arrow points
    tip = (int(cx + length * 0.5 * cos_a), int(cy + length * 0.5 * sin_a))
    tail = (int(cx - length * 0.5 * cos_a), int(cy - length * 0.5 * sin_a))
    
    # Arrow glow layer
    arrow_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.line(arrow_mask, tail, tip, 255, max(2, width), cv2.LINE_AA)
    
    # Arrow arrowhead wings
    wing_len = int(width * 2.5)
    w1 = (int(tip[0] - wing_len * np.cos(angle - 0.5)), int(tip[1] - wing_len * np.sin(angle - 0.5)))
    w2 = (int(tip[0] - wing_len * np.cos(angle + 0.5)), int(tip[1] - wing_len * np.sin(angle + 0.5)))
    pts = np.array([tip, w1, (int(tip[0] - wing_len * 0.5 * cos_a), int(tip[1] - wing_len * 0.5 * sin_a)), w2])
    cv2.fillPoly(arrow_mask, [pts], 255)
    
    # Purple/Gold chakra energy
    k_size = max(5, (width | 1) * 2 + 1)
    if k_size % 2 == 0: k_size += 1
    glow = cv2.GaussianBlur(arrow_mask, (k_size, k_size), 0)
    glow_f = (glow.astype(float) / 255.0)[:, :, None]
    core_f = (arrow_mask.astype(float) / 255.0)[:, :, None]
    
    purple_glow = np.array([210, 60, 240], dtype=float)
    white_core = np.array([255, 255, 240], dtype=float)
    
    fx = glow_f * purple_glow + core_f * white_core * 0.95
    out = np.clip(canvas.astype(float) + fx, 0, 255).astype(np.uint8)
    
    # Speed streak lines trailing behind arrow
    rng = np.random.RandomState(int(u * 60) + 7)
    for _ in range(8):
        trail_dist = rng.uniform(length * 0.3, length * 1.2)
        offset_perp = rng.uniform(-width * 1.8, width * 1.8)
        px = int(cx - trail_dist * cos_a - offset_perp * sin_a)
        py = int(cy - trail_dist * sin_a + offset_perp * cos_a)
        p_end_x = int(px - length * 0.4 * cos_a)
        p_end_y = int(py - length * 0.4 * sin_a)
        if 0 <= px < w and 0 <= py < h:
            cv2.line(out, (px, py), (p_end_x, p_end_y), (200, 120, 255), max(1, int(width * 0.2)), cv2.LINE_AA)
            
    return out


def tinta(rgb, accent='none'):
    gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    gray=np.clip((gray.astype(float)-30)*1.25+35,12,242).astype('uint8')
    out=np.repeat(gray[:,:,None],3,axis=2)
    r,g,b=[rgb[:,:,i].astype(float) for i in range(3)]
    if accent == 'cyan':
        keep = (b - r > 35) & (g - r > 20)
    elif accent == 'red':
        keep = (r - g > 35) & (r - b > 25)
    elif accent == 'purple':
        keep = (b > g + 12) & (b > 25) & (r > g - 10)
    else:
        keep = np.zeros(gray.shape, bool)
    # Soft selective color; binary chroma edges produced visible square islands.
    weight=cv2.GaussianBlur(keep.astype('float32'),(9,9),2)[:,:,None]
    if accent == 'purple':
        # Boost vibrancy of purple Susanoo chakra
        boost_rgb = rgb.astype(float).copy()
        boost_rgb[:, :, 0] = np.clip(boost_rgb[:, :, 0] * 1.5, 0, 255) # Blue
        boost_rgb[:, :, 2] = np.clip(boost_rgb[:, :, 2] * 1.35, 0, 255) # Red
        return np.clip(out * (1 - weight) + boost_rgb * weight, 0, 255).astype('uint8')
    return np.clip(out*(1-weight)+rgb*weight,0,255).astype('uint8')


def segmentar_local(rgb, polygon):
    """Offline polygon-seeded GrabCut, never chroma key or a model download."""
    h,w=rgb.shape[:2];poly=np.array(polygon)*[w,h]
    seed=np.zeros((h,w),np.uint8);cv2.fillPoly(seed,[poly.astype('int32')],255)
    k=max(3,int(w*.007)|1)
    inside=cv2.erode(seed,np.ones((k,k),np.uint8))
    outside=cv2.dilate(seed,np.ones((k*3,k*3),np.uint8))
    mask=np.full((h,w),cv2.GC_BGD,np.uint8)
    mask[outside>0]=cv2.GC_PR_BGD;mask[seed>0]=cv2.GC_PR_FGD;mask[inside>0]=cv2.GC_FGD
    cv2.setRNGSeed(4)
    cv2.grabCut(rgb,mask,None,np.zeros((1,65)),np.zeros((1,65)),3,cv2.GC_INIT_WITH_MASK)
    alpha=np.where((mask==1)|(mask==3),255,0).astype('uint8')
    alpha=cv2.GaussianBlur(alpha,(3,3),.5);alpha[inside>0]=255
    return np.dstack([rgb,alpha])


def legenda_manga(lines, origin, duration):
    out=HEADER.replace('Barlow SemiBold,64','Cinzel,84').replace('&H90000000,0,0,0,0,100,100,1,','&H90000000,-1,0,0,0,100,100,1,')
    audit={'omitted':[],'medium':[],'timed_words':0,'method':'Canonical timings; prior mix/stem evidence, not new listening.'}
    for line in lines:
        # Omitting an uncertain negation alone reverses the author's meaning.
        if any(w['word'].casefold() in {'não','nunca'} and (w.get('confidence') in {'low','gap'} or not w.get('identified_in_audio',True)) for w in line['words']):
            audit['omitted'].extend(w['word'] for w in line['words']);continue
        valid=[]
        for w in line['words']:
            if w.get('start') is None or not w.get('identified_in_audio',True) or w.get('confidence')=='low':
                audit['omitted'].append(w['word']);continue
            if w.get('confidence')=='medium': audit['medium'].append(w['word'])
            valid.append(w)
        # Natural whole phrases; split only long lines near their middle.
        groups=[valid] if len(' '.join(w['word'] for w in valid))<43 else [valid[:len(valid)//2],valid[len(valid)//2:]]
        for group in groups:
            for i,w in enumerate(group):
                a=max(0,w['start']-origin);b=min(duration,w['end']-origin+.04)
                if i+1<len(group) and group[i+1]['start']-w['end']<.16: b=min(duration,group[i+1]['start']-origin+.04)
                if b<=a:continue
                words=[]
                for j,v in enumerate(group):
                    tag=r'{\c&H00FFFFFF&}' if j<i else r'{\c&H00FFE050&\b1}' if j==i else r'{\c&H00CCCCCC&}'
                    words.append(tag+v['word'].upper()+r'{\b1}')
                out+=event(a,b,r'{\an2\pos(960,965)\bord3\shad1}'+ ' '.join(words),layer=2)
                audit['timed_words']+=1
    return out,audit


def executar(slug, config='motion_manga.json', prepare_only=False):
    from dataclasses import asdict
    import soundfile as sf
    import imagem
    from scipy.signal import find_peaks
    from paineis_manga import mascaras_3_paineis
    from speedlines_manga import gerar_textura_speedlines_radial
    p=ROOT/'projetos'/slug;cfg=json.loads((p/config).read_text(encoding='utf8'))
    qa=p/'qa'/cfg.get('qa_dir', 'motion_manga');qa.mkdir(parents=True,exist_ok=True)
    work=p/'saidas'/cfg.get('work_dir', 'motion_manga_work');work.mkdir(parents=True,exist_ok=True)
    origin=cfg['start'];duration=cfg['frames']/30
    assert 10<=duration<=30
    assets={}
    for key,s in cfg['assets'].items():
        if 'image' in s:
            rgb=np.array(Image.open(p/s['image']).convert('RGB'))
        else:
            cap=cv2.VideoCapture(str(p/'clips_raw'/s['clip']));cap.set(cv2.CAP_PROP_POS_MSEC,s['time']*1000)
            ok,bgr=cap.read();cap.release();assert ok,key
            rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
        rgb=cv2.resize(rgb,(1920,1080));Image.fromarray(rgb).save(work/f'{key}_source.png')
        ink=tinta(rgb,s.get('accent','none'))
        if 'mask' in s:
            alpha=np.array(Image.open(p/s['mask']).convert('RGBA'))[:,:,3]
            rgba=np.dstack([ink,alpha])
        elif 'polygon' in s:
            rgba=segmentar_local(ink,s['polygon'])
        else:
            rgba=None
        bg=reconstruir_fundo(ink,rgba[:,:,3]) if rgba is not None else ink
        if rgba is not None:
            Image.fromarray(rgba).save(work/f'{key}_cut.png')
            Image.fromarray(bg).save(work/f'{key}_background.png')
            alpha=rgba[:,:,3:4]/255
            Image.fromarray((rgba[:,:,:3]*alpha+np.full_like(ink,[185,90,100])*(1-alpha)).astype('uint8')).save(qa/f'{key}_mask_check.jpg')
        assets[key]=(ink,rgba,bg)
    y,sr=sf.read(p/cfg['drums']);y=y.mean(axis=1) if y.ndim>1 else y
    y=y[int(origin*sr):int((origin+duration)*sr)];hop=round(sr*.01)
    energy=np.array([np.sqrt(np.mean(y[k:k+hop]**2)) for k in range(0,len(y)-hop,hop)])
    peaks,_=find_peaks(energy,distance=25,prominence=.015)
    strongest=int(peaks[np.argmax(energy[peaks])]);impact=round(strongest*.01*30)/30
    dump(qa/'music_peaks.json',{'method':'10ms RMS local maxima from existing drums stem','peaks':[{'local':float(k*.01),'strength':float(energy[k])} for k in peaks],'strongest_local':impact,'absolute':origin+impact})
    if prepare_only: return 0
    canonical=json.loads((p/cfg['canonical']).read_text(encoding='utf8'))
    if 'lines' in cfg:
        lines=[canonical['lines'][idx] for idx in cfg['lines']]
    else:
        lines=[l for l in canonical['lines'] if l.get('start') is not None and origin<=l['start']<origin+duration]
    ass,audit=legenda_manga(lines,origin,duration);af=work/'lyrics.ass';af.write_text(ass,encoding='utf8');dump(qa/'lyrics_audit.json',audit)
    frames=work/'frames';frames.mkdir(exist_ok=True)
    motion=[];last=None
    for n in range(cfg['frames']):
        t=n/30;s=next(s for s in cfg['shots'] if s['start']<=t<s['end'])
        u=(t-s['start'])/(s['end']-s['start']);ink,rgba,bg=assets[s['asset']]
        if rgba is not None: canvas=compor_profundidade(bg,rgba,u)
        else:
            mat=cv2.getRotationMatrix2D((960,540),0,1.015+.06*u);mat[0,2]+=25*u
            canvas=cv2.warpAffine(ink,mat,(1920,1080),borderMode=cv2.BORDER_REFLECT)
        if 'panels_3' in s:
            # 3-panel shonen split screen: left, middle, right
            p_left = assets[s['panels_3'][0]][0]
            p_mid = canvas
            p_right = assets[s['panels_3'][1]][0]
            # Warp panels with different subtle camera dynamics
            mat_l = cv2.getRotationMatrix2D((960, 540), 0, 1.05 + 0.03 * u)
            mat_l[0, 2] -= 400 - 30 * u
            p_left = cv2.warpAffine(p_left, mat_l, (1920, 1080), borderMode=cv2.BORDER_REFLECT)

            mat_r = cv2.getRotationMatrix2D((960, 540), 0, 1.08 - 0.04 * u)
            mat_r[0, 2] += 400 - 30 * u
            p_right = cv2.warpAffine(p_right, mat_r, (1920, 1080), borderMode=cv2.BORDER_REFLECT)

            m1, m2, m3 = mascaras_3_paineis(1920, 1080, u, borda=18)
            canvas = np.where((m1 > 0)[:, :, None], p_left,
                     np.where((m2 > 0)[:, :, None], p_mid,
                     np.where((m3 > 0)[:, :, None], p_right, 18))).astype('uint8')
        elif 'panel' in s:
            # Place each portrait in its own half; never splice two noses together.
            canvas=cv2.warpAffine(canvas,np.float32([[1,0,-350],[0,1,0]]),(1920,1080),borderMode=cv2.BORDER_REFLECT)
            other=assets[s['panel']][0]
            # Camera in each panel differs; diagonal edge opens/closes dynamically.
            mat=cv2.getRotationMatrix2D((960,540),0,1.08-.04*u);mat[0,2]+=350-30*u
            other=cv2.warpAffine(other,mat,(1920,1080),borderMode=cv2.BORDER_REFLECT)
            a,b=mascaras_diagonais(1920,1080,u,18)
            canvas=np.where((a>0)[:,:,None],canvas,np.where((b>0)[:,:,None],other,18)).astype('uint8')
        if s.get('rinnegan_fx'):
            # Procedural Rinnegan overlay with orbiting tomoes and purple glow
            eye_pos = s.get('rinnegan_pos', [1135, 475])
            eye_r = s.get('rinnegan_r', 55)
            canvas = desenhar_rinnegan_fx(canvas, eye_pos, eye_r, u, tomoe_count=6)
        if s.get('amenotejikara'):
            # Dimensional warp / glitch displacement
            canvas = efeito_amenotejikara_shatter(canvas, u, seed=s.get('amenotejikara_seed', 101))
        if s.get('susanoo_arrow'):
            # Piercing chakra arrow rushing towards screen
            canvas = efeito_flecha_susanoo(canvas, u)
        if s.get('speedlines'):
            # Shonen action speedlines on climax drops / sudden strikes
            sl = np.array(gerar_textura_speedlines_radial(1920, 1080, linhas_totais=120, opacidade=150))
            sl_mask = sl[:, :, 3:4].astype(float) / 255.0
            canvas = np.clip(canvas.astype(float) * (1 - sl_mask * 0.75) + sl[:, :, :3] * sl_mask, 0, 255).astype('uint8')
        if 'lightning' in s:
            # Kirin electric lightning bolts cutting through the sky
            t_rel = t - s['start']
            # Blue electric bolts flashing
            bolt_mask = np.zeros((1080, 1920), dtype=np.uint8)
            rng = np.random.RandomState(int((t_rel * 24)) % 1000 + 42)
            if rng.rand() > 0.3:
                # Draw 2-3 jagged lightning branches
                for _ in range(rng.randint(2, 4)):
                    x_start = rng.randint(400, 1500)
                    y_start = 0
                    pts_bolt = [(x_start, y_start)]
                    curr_x, curr_y = x_start, y_start
                    while curr_y < 1000:
                        curr_y += rng.randint(40, 90)
                        curr_x += rng.randint(-60, 60)
                        pts_bolt.append((np.clip(curr_x, 0, 1919), curr_y))
                    for pt_idx in range(len(pts_bolt) - 1):
                        cv2.line(bolt_mask, pts_bolt[pt_idx], pts_bolt[pt_idx + 1], 255, rng.randint(3, 7))
                # Glow around lightning
                glow = cv2.GaussianBlur(bolt_mask, (25, 25), 7).astype(float) / 255.0
                core = (bolt_mask.astype(float) / 255.0)[:, :, None]
                # Cyan/electric blue: R~180, G~230, B~255
                electric_color = np.array([120, 220, 255], dtype=float)
                glow_color = np.array([40, 140, 255], dtype=float)
                bolt_rgb = core * electric_color + glow[:, :, None] * glow_color * 0.8
                canvas = np.clip(canvas.astype(float) + bolt_rgb, 0, 255).astype('uint8')
        if s.get('energy'):
            # Extracted energy stays anchored around the real hand, not generic neon.
            src=assets[s['asset']][0];r,g,b=[src[:,:,i].astype(float) for i in range(3)]
            mask=((b-r>35)&(g-r>20)).astype('float32')
            mask[:600]=0;mask[880:]=0
            mask[:,:650]=0;mask[:,1080:]=0
            mask=cv2.GaussianBlur(mask,(21,21),5)
            pulse=.025+.025*(.5+.5*np.sin(t*24))
            canvas=np.clip(canvas.astype(float)+np.stack([mask*12,mask*140,mask*200],axis=2)*pulse,0,255).astype('uint8')
            for k in range(10):
                x=int((k*233+t*380)%2300)-200;y0=100+(k%3)*110
                if 580<x<1280:continue
                cv2.line(canvas,(x,y0),(x+210,y0+290),(210,225,230),2,cv2.LINE_AA)
        hit=abs(t-impact)
        if hit<.10:
            # Three-frame ink impact, never an empty white frame.
            if n%2==0:canvas=255-canvas
            mat=np.float32([[1,0,12*np.sin(n*3)],[0,1,6*np.cos(n*2)]])
            canvas=cv2.warpAffine(canvas,mat,(1920,1080),borderMode=cv2.BORDER_REFLECT)
        # A local bottom falloff keeps Cinzel readable without a title-card panel.
        fade=np.clip((np.arange(1080)-850)/230,0,1)*.68
        canvas=(canvas*(1-fade[:,None,None])).astype('uint8')
        cv2.rectangle(canvas,(7,7),(1912,1072),(15,15,15),14)
        small=cv2.resize(canvas,(320,180)).astype(float)
        if last is not None:motion.append(float(np.abs(small-last).mean()))
        last=small
        cv2.imwrite(str(frames/f'{n:04}.png'),cv2.cvtColor(canvas,cv2.COLOR_RGB2BGR))
        if n%60==0:print('manga frame',n,flush=True)
    dump(qa/'motion_metrics.json',{'adjacent_frame_mean_abs_difference':motion,'median':float(np.median(motion))})
    dest=p/'saidas'/cfg['output']
    graph=f"[0:v]setsar=1,ass='{af.relative_to(ROOT).as_posix()}':fontsdir=assets/fontes/cinzel,format=yuv420p[v];[1:a]atrim=start={origin}:duration={duration},asetpts=PTS-STARTPTS,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]"
    rd.encode(str(dest),['-framerate','30','-i',str(frames/'%04d.png'),'-i',str(p/cfg['audio'])],filtro_complexo=graph,mapa=['-map','[v]','-map','[a]'],args_extra=['-r','30','-fps_mode','cfr'],cq='17')
    result=subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(dest),'-f','null','-'],capture_output=True,text=True)
    (qa/'decode.log').write_text(result.stderr,encoding='utf8');assert result.returncode==0
    info=probe(dest);dump(qa/'probe.json',info)
    v=next(s for s in info['streams'] if s['codec_type']=='video');a=next(s for s in info['streams'] if s['codec_type']=='audio')
    assert int(v['nb_frames'])==cfg['frames'] and v['pix_fmt']=='yuv420p' and v['sample_aspect_ratio']=='1:1' and v['avg_frame_rate']=='30/1'
    assert abs(float(v['duration'])-float(a['duration']))<.05 and abs(float(v['duration'])-duration)<.05
    gate=asdict(imagem.analisar(dest,qa));dump(qa/'image_gate.json',gate)
    sheets(dest,qa,list(np.arange(.1,duration,.8))+[duration-.08],'contact_full')
    for i,s in enumerate(cfg['shots']):sheets(dest,qa,[s['start']+(s['end']-s['start'])*u for u in [.1,.35,.6,.85]],f'sequence_{i:02}')
    samples = cfg.get('samples', [('hand', 1.1), ('impact', impact), ('face', min(11.5, duration - 0.5))])
    for name, t in samples:
        subprocess.run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(dest),'-frames:v','1',str(qa/f'{name}_fullhd.png')],check=True)
    loud=subprocess.run(['ffmpeg','-hide_banner','-i',str(dest),'-af','loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True)
    (qa/'loudness.log').write_text(loud.stderr,encoding='utf8')
    dump(qa/'render_summary.json',{'output':str(dest),'frames':cfg['frames'],'duration':duration,'gate':gate,'segmentation':'existing mask plus polygon-seeded GrabCut; rembg model unavailable offline'})
    print(json.dumps({'output':str(dest),'gate':gate},ensure_ascii=False));return 0
