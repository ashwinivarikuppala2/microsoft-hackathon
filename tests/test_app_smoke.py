"""Runs app.py top-to-bottom against a recording stand-in for streamlit.

This checks wiring (imports, form -> Hindsight recall -> display), not visuals.
"""

import os
import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from tests.support import FakeHindsight, install_hindsight_stub_if_missing

install_hindsight_stub_if_missing()

from dealmind.seed import seed_historical_deals  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class Ctx:
    def __init__(self, st):
        self._st = st

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return getattr(self._st, name)

    def empty(self):
        pass


class StreamlitStub(types.ModuleType):
    def __init__(self, inputs=None, submitted=False):
        super().__init__("streamlit")
        self.inputs, self.submitted = inputs or {}, submitted
        self.session_state = {}
        self.out: list[str] = []      # everything rendered as text
        self.kinds: list[str] = []    # which st.* calls happened

    def cache_resource(self, f=None, **kw):
        return f if f else (lambda g: g)

    def columns(self, spec, **kw):
        return [Ctx(self) for _ in range(spec if isinstance(spec, int) else len(spec))]

    def text_input(self, label, **kw):
        return self.inputs.get(label, "")

    text_area = text_input

    def number_input(self, label, **kw):
        return self.inputs.get(label, kw.get("value", 0))

    def selectbox(self, label, options, index=0, **kw):
        return self.inputs.get(label, options[index])

    def form_submit_button(self, *a, **kw):
        return self.submitted

    def button(self, *a, **kw):
        return False

    def progress(self, *a, **kw):
        return Ctx(self)

    @property
    def sidebar(self):
        return Ctx(self)

    def tabs(self, labels):
        return [Ctx(self) for _ in labels]

    def chat_message(self, *a, **kw):
        return Ctx(self)

    def chat_input(self, *a, **kw):
        return ""

    def date_input(self, label, **kw):
        import datetime
        return datetime.date(2026, 9, 28)

    def rerun(self):
        pass

    def stop(self):
        raise SystemExit

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def call(*args, **kw):
            self.kinds.append(name)
            for a in args:
                if isinstance(a, str):
                    self.out.append(a)
            return Ctx(self)
        return call


def run_app(inputs=None, submitted=False, client=None, env=None):
    stub = StreamlitStub(inputs, submitted)
    env = {"HINDSIGHT_API_KEY": "test-key", "HINDSIGHT_BANK_ID": "smoke"} if env is None else env
    with mock.patch.dict(sys.modules, {"streamlit": stub}), \
         mock.patch.dict(os.environ, env, clear=False), \
         mock.patch("dealmind.memory.get_client", return_value=client or FakeHindsight()), \
         mock.patch("dealmind.memory.load_dotenv"):
        runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
    return stub


FORM = {
    "Industry": "Logistics", "Product": "Enterprise Platform", "Competitor": "FreightIQ",
    "Objection": "FreightIQ is cheaper than our quote",
    "Stakeholder concern": "Operations wants a fast go-live",
    "Pricing discussion": "Buyer wants a discount to match FreightIQ",
    "Deal value (USD)": 150000,
}


class TestAppSmoke(unittest.TestCase):
    def test_renders_form_without_submit(self):
        st = run_app()
        self.assertIn("Current deal", st.out)
        self.assertNotIn("result", st.session_state)
        self.assertNotIn("error", st.kinds)

    def test_submit_shows_recalled_memories_and_evidence(self):
        client = FakeHindsight()
        seed_historical_deals(client, "smoke")
        st = run_app(FORM, submitted=True, client=client)
        self.assertEqual(client.calls["recall"], 1)
        self.assertIn("result", st.session_state)
        text = "\n".join(st.out)
        self.assertRegex(text, r"Recalled memories \(\d+\)")
        self.assertRegex(text, r"Historical evidence \(\d+ deals\)")
        self.assertRegex(text, r"Outcome|Why it")  # evidence card rendered

    def test_invalid_form_does_not_call_hindsight(self):
        client = FakeHindsight()
        st = run_app({"Industry": "Retail", "Product": "Team Plan"}, submitted=True, client=client)
        self.assertEqual(client.calls["recall"], 0)
        self.assertIn("warning", st.kinds)

    def test_empty_bank_shows_helpful_message(self):
        st = run_app(FORM, submitted=True, client=FakeHindsight())
        self.assertIn("Hindsight returned no memories", "\n".join(st.out))

    def test_recall_error_is_surfaced(self):
        class Boom(FakeHindsight):
            def recall(self, *a, **k):
                raise ConnectionError("network down")
        st = run_app(FORM, submitted=True, client=Boom())
        self.assertIn("Hindsight recall failed: ConnectionError: network down", "\n".join(st.out))

    def test_submit_shows_patterns_and_recommendations(self):
        client = FakeHindsight()
        seed_historical_deals(client, "smoke")
        st = run_app(FORM, submitted=True, client=client)
        self.assertIn("report", st.session_state)
        report = st.session_state["report"]
        self.assertGreater(len(report.objection_patterns), 0)
        self.assertGreater(len(report.competitor_patterns), 0)
        self.assertEqual(len(report.recommendations), 4)
        text = "\n".join(st.out)
        self.assertIn("Deal-Risk Analysis", text)
        self.assertIn("Objection Patterns", text)
        self.assertIn("Competitor Patterns", text)
        self.assertIn("Evidence-Based Recommendations", text)

    def test_missing_config_shows_error_and_no_crash(self):
        # no API key + default cloud URL => ConfigError path
        with mock.patch.dict(os.environ, {}, clear=True):
            st = run_app(env={})
        self.assertIn("error", st.kinds)



if __name__ == "__main__":
    unittest.main()
