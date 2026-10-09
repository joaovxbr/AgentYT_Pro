import unittest, sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ferramentas'))
import paineis_manga as pm

class MotionMangaTests(unittest.TestCase):
    def test_diagonal_panels_are_complementary_and_move(self):
        a,b=pm.mascaras_diagonais(320,180,.2)
        c,d=pm.mascaras_diagonais(320,180,.8)
        self.assertEqual(a.shape,(180,320))
        self.assertFalse(np.any((a>0)&(b>0)))
        self.assertGreater(np.count_nonzero(a!=c),300)
        self.assertGreater(np.count_nonzero(a),5000)

class DepthTests(unittest.TestCase):
    def test_background_reconstruction_removes_subject(self):
        import paralaxe_3d as depth
        im=np.full((90,160,3),80,np.uint8);im[20:75,55:105]=240
        alpha=np.zeros((90,160),np.uint8);alpha[20:75,55:105]=255
        bg=depth.reconstruir_fundo(im,alpha)
        self.assertLess(float(bg[30:60,60:100].mean()),120)
    def test_depth_motion_preserves_opaque_face(self):
        import paralaxe_3d as depth
        bg=np.full((90,160,3),70,np.uint8)
        char=np.zeros((90,160,4),np.uint8);char[20:70,50:110]=[210,210,210,255]
        a=depth.compor_profundidade(bg,char,0)
        b=depth.compor_profundidade(bg,char,1)
        self.assertEqual(a.shape,(90,160,3))
        self.assertGreater(float(np.abs(a.astype(float)-b).mean()),1)
        self.assertGreater(b[45,80,0],200)

class RendererTests(unittest.TestCase):
    def test_ink_preserves_only_requested_accent(self):
        import motion_manga as mm
        im=np.zeros((40,60,3),np.uint8);im[:]=[180,120,90];im[10:30,20:40]=[20,200,240]
        out=mm.tinta(im,'cyan')
        self.assertEqual(out.shape,im.shape)
        self.assertEqual(int(out[5,5,0]),int(out[5,5,1]))
        self.assertGreater(int(out[20,30,2]),int(out[20,30,0]))
    def test_ass_omits_unidentified_words_and_no_pause_event(self):
        import motion_manga as mm
        line={'words':[{'word':'A','start':None,'end':None,'identified_in_audio':False},{'word':'verdade','start':50.,'end':50.3,'identified_in_audio':True},{'word':'vem','start':51.,'end':51.3,'identified_in_audio':True}]}
        text,audit=mm.legenda_manga([line],49.8,3)
        self.assertIn('Cinzel',text)
        self.assertEqual(audit['omitted'],['A'])
        self.assertNotIn('VERDADE A',text)
        self.assertIn('0:00:00.54',text)
    def test_segmentation_keeps_seeded_face(self):
        import motion_manga as mm
        im=np.full((90,160,3),30,np.uint8);im[15:90,50:115]=190
        poly=[[.30,.1],[.75,.1],[.75,1],[.3,1]]
        cut=mm.segmentar_local(im,poly)
        self.assertEqual(cut[45,80,3],255)
        self.assertEqual(cut[5,5,3],0)
    def test_uncertain_negative_does_not_reverse_phrase_meaning(self):
        import motion_manga as mm
        line={'words':[{'word':'Não','start':50.,'end':50.2,'confidence':'low','identified_in_audio':False},{'word':'venha','start':50.2,'end':50.5,'identified_in_audio':True}]}
        text,audit=mm.legenda_manga([line],49.8,2)
        self.assertNotIn('VENHA',text)
        self.assertEqual(audit['omitted'],['Não','venha'])
    def test_renderer_has_studio_entry(self):
        source=(Path(__file__).resolve().parents[1]/'ferramentas/estudio.py').read_text(encoding='utf8')
        self.assertIn('motion-manga',source)

if __name__=='__main__': unittest.main()
