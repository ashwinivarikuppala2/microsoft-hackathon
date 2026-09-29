"""End-to-end test of the 9-step guided demo using Streamlit's headless AppTest."""
import os
import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def texts(at):
    out = []
    for group in (at.markdown, at.subheader, at.success, at.info, at.warning, at.caption):
        out += [e.value for e in group]
    return "\n".join(out)


def click(at, label):
    [b for b in at.button if b.label.startswith(label)][0].click().run()


class TestStage4Flow(unittest.TestCase):
    def setUp(self):
        os.environ["DEALMIND_DATA_DIR"] = tempfile.mkdtemp()
        os.environ.pop("HINDSIGHT_BASE_URL", None)

    def test_full_demo_flow(self):
        at = AppTest.from_file(APP, default_timeout=30).run()
        self.assertFalse(at.exception, at.exception)
        
        # Scene 1: Cold start Ask DealMind
        click(at, "Ask DealMind")
        self.assertFalse(at.exception, at.exception)
        t = texts(at)
        self.assertTrue("Little/no relevant memory" in t or "Playbook default" in t)
        self.assertIn("Diagnose before you respond", t)

        # Record LOST after discount, save
        at.selectbox[0].set_value("discount")
        at.radio[0].set_value("LOST")
        at.button[[b.label for b in at.button].index("💾 Save outcome to Hindsight")].click().run()
        self.assertFalse(at.exception, at.exception)
        t = texts(at)
        self.assertTrue("Learning from the new outcome" in t or "Recorded" in t)

        # Scene 2: Create a future similar deal
        click(at, "➡️ Create a future similar deal")
        self.assertTrue("Contoso Freight" in texts(at) or any("Contoso" in e.value for e in at.subheader))
        click(at, "Ask DealMind")
        self.assertFalse(at.exception, at.exception)
        t = texts(at)
        self.assertIn("Evidence-based", t)
        self.assertIn("What the new experience changed", t)
        self.assertIn("recommendation changed because of the saved experience", t)

    def test_won_path_recommends_same_tactic(self):
        at = AppTest.from_file(APP, default_timeout=30).run()
        click(at, "Ask DealMind")
        at.selectbox[0].set_value("phased")
        at.radio[0].set_value("WON")
        at.button[[b.label for b in at.button].index("💾 Save outcome to Hindsight")].click().run()
        click(at, "➡️ Create a future similar deal")
        click(at, "Ask DealMind")
        self.assertFalse(at.exception, at.exception)
        self.assertIn("Phased rollout", texts(at))


if __name__ == "__main__":
    unittest.main()
