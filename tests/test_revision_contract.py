import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ferramentas'))
import pipeline_autonomo_pro as pipeline
class RevisionContract(unittest.TestCase):
    def test_frame_boundaries_do_not_accumulate_rounding(self):
        self.assertTrue(hasattr(pipeline, 'quantizar_cortes'), 'missing frame-exact revision contract')
        bounds = pipeline.quantizar_cortes([0,1.79,3.58,174.77])
        self.assertEqual(sum(b-a for a,b in zip(bounds,bounds[1:])),5243)
        self.assertEqual(bounds[0],0)
    def test_manifest_revision_entry_exists(self):
        self.assertTrue(hasattr(pipeline, 'executar_revisao'), 'missing reusable revision pipeline')
    def test_refined_mask_preserves_opaque_face(self):
        import revisao_master as rev
        import numpy as np
        self.assertTrue(hasattr(rev, 'refinar_alpha'))
        a=np.zeros((30,30),dtype=np.uint8);a[5:25,5:25]=255
        refined=rev.refinar_alpha(a)
        self.assertEqual(int(refined[15,15]),255)
        self.assertEqual(int(refined[0,0]),0)
if __name__=='__main__': unittest.main()
