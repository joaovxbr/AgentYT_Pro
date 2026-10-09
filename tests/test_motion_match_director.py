from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ferramentas"))

import motion_match_director as mm
import movimento
import render_clipe
import semantic_scene_matcher as sm


def shot(start, end, direction="static", intensity=0.5, tags=None, preset="narrativo"):
    return {
        "start": start,
        "end": end,
        "preset": preset,
        "type": "lyric",
        "camera": {"zoom_inicio": 1.0, "zoom_fim": 1.025},
        "scene_match": {
            "motion_direction": direction,
            "scene_intensity": intensity,
            "scene_tags": list(tags or []),
        },
    }


class MotionMatchDirectorTests(unittest.TestCase):
    def test_same_high_energy_motion_becomes_match_cut(self):
        a = shot(0, 2, "right", 0.78, {"action", "fight"})
        b = shot(2, 4, "right", 0.74, {"action", "energy"})
        tr = mm.decidir_transicao(a, b)
        self.assertEqual(tr["type"], "match_cut")
        self.assertEqual(tr["direction"], "right")

    def test_calm_same_direction_stays_clean(self):
        a = shot(0, 2, "right", 0.34, {"calm", "portrait"})
        b = shot(2, 4, "right", 0.38, {"calm", "portrait"})
        tr = mm.decidir_transicao(a, b)
        self.assertEqual(tr["type"], "hard_cut")

    def test_opposite_impact_can_use_flash(self):
        a = shot(10, 12, "left", 0.88, {"fight", "impact"})
        b = shot(12, 14, "right", 0.82, {"electric", "action"})
        tr = mm.decidir_transicao(a, b, last_fx_time=0)
        self.assertEqual(tr["type"], "flash_cut")
        self.assertGreaterEqual(tr["strength"], 0.7)

    def test_flash_respects_cooldown(self):
        a = shot(10, 12, "left", 0.88, {"fight", "impact"})
        b = shot(12, 14, "right", 0.82, {"electric", "action"})
        tr = mm.decidir_transicao(a, b, last_fx_time=9.0)
        self.assertEqual(tr["type"], "hard_cut")

    def test_graphics_locked_never_gets_transition_fx(self):
        a = shot(0, 2, "left", 0.9, {"impact"}, preset="graphics_locked")
        b = shot(2, 4, "left", 0.9, {"impact"})
        tr = mm.decidir_transicao(a, b)
        self.assertEqual(tr["type"], "hard_cut")
        self.assertEqual(tr["reason"], "graphics_locked")

    def test_match_cut_does_not_force_camera_pan(self):
        plan = {
            "shots": [
                shot(0, 2, "left", 0.8, {"action"}),
                shot(2, 4, "left", 0.8, {"action"}),
            ]
        }
        out = mm.enriquecer_plano(plan)
        self.assertEqual(out["shots"][0]["transition_out"]["type"], "match_cut")
        self.assertNotIn("pan", out["shots"][0]["camera"])

    def test_camera_explicit_pan_wins_over_cyclic_fallback(self):
        s = shot(0, 2)
        s["camera"]["pan"] = "right"
        params = movimento.parametros_do_shot(s)
        self.assertEqual(params["pan"], "dir")


class RenderTransitionTests(unittest.TestCase):
    def test_flash_filters_only_when_slice_touches_boundary(self):
        s = {"start": 10.0, "end": 12.0}
        sh = {
            "transition_in": {"type": "flash_cut", "duration": 0.08},
            "transition_out": {"type": "flash_cut", "duration": 0.08},
        }
        full = render_clipe._filtros_transicao(sh, s, 10.0, 12.0)
        middle = render_clipe._filtros_transicao(sh, s, 10.5, 11.5)
        self.assertEqual(len(full), 4)
        self.assertEqual(middle, [])
        self.assertTrue(any("eq=brightness" in x for x in full))
        self.assertTrue(any("gblur=" in x for x in full))
        self.assertFalse(any("fade=" in x for x in full))


class SceneMatcherContinuityTests(unittest.TestCase):
    def test_same_direction_gets_small_bonus_not_semantic_override(self):
        prev = {"motion_direction": "left"}
        same = {
            "id": "same", "clip": "a.mp4", "duration": 4.0, "clip_duration": 10.0,
            "motion_direction": "left", "tag_scores": {"action": 0.8},
            "intensity": 0.6, "quality": 0.8,
        }
        opposite = dict(same, id="opp", motion_direction="right")
        intent = {
            "tag_weights": {"action": 1.0},
            "target_intensity": 0.6,
        }
        a = sm.score_scene(intent, same, 2.0, previous_scene=prev)
        b = sm.score_scene(intent, opposite, 2.0, previous_scene=prev)
        self.assertGreater(a["score"], b["score"])
        self.assertLessEqual(a["motion_continuity"], 0.04)


if __name__ == "__main__":
    unittest.main()
