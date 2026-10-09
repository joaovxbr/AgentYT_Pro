import sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ferramentas'))
import render_dispatch as rd
import revisao_master as rev
class Safety(unittest.TestCase):
 def test_gpu_unavailable_fails_closed(self):
  with patch.object(rd,'tem_nvenc',return_value=False):
   with self.assertRaises(RuntimeError): rd.video_args()
 def test_normalization_ignores_bad_sar(self):
  self.assertIn('setsar=1,scale=1920:1080',rev.normalize_video())
 def test_audio_fade_title_continuous(self):
  self.assertIn('afade=t=in:st=0:d=2',rev.audio_graph())
  self.assertNotIn('loudnorm',rev.audio_graph().split('[ia]')[0])
 def test_nvenc_runtime_error_is_not_masked_by_forbidden_cpu_fallback(self):
  failed=SimpleNamespace(returncode=1,stderr='original nvenc/filter error')
  with patch.object(rd,'tem_nvenc',return_value=True), patch.object(rd,'tem_gpu_nvidia',return_value=True), patch.object(rd.subprocess,'run',return_value=failed):
   import tempfile
   with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(RuntimeError,'original nvenc/filter error'):
    rd.encode(str(Path(tmp)/'out.mp4'),['-f','lavfi','-i','color=black:s=16x16:d=.1'])
if __name__=='__main__':unittest.main()
