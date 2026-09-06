"""MVP interaction smoke tests; no hosted account required."""
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest


class StreamlitTests(unittest.TestCase):
    def test_simulate_and_stale_state(self):
        app = AppTest.from_file(str(Path(__file__).with_name('streamlit_app.py'))).run(timeout=60)
        self.assertFalse(app.exception)
        next(x for x in app.slider if x.label == 'Horizon · weeks').set_value(4)
        next(x for x in app.select_slider if x.label == 'Paired scenario runs').set_value(5)
        app.run()
        next(x for x in app.button if x.label == 'Simulate').click().run(timeout=120)
        self.assertFalse(app.exception)
        self.assertIsNotNone(app.session_state['result'])
        self.assertAlmostEqual(app.session_state['result']['kpis']['simulated_net_benefit_inr'], 0)
        self.assertTrue(app.session_state['exports'][0].startswith(b'<!DOCTYPE') or b'<html' in app.session_state['exports'][0][:200])
        next(x for x in app.selectbox if x.label == 'Policies to test').select('Decline / exit proposals').run()
        self.assertTrue(any('Inputs changed' in x.value for x in app.warning))
        next(x for x in app.button if x.label == 'Simulate').click().run(timeout=120)
        self.assertFalse(app.exception)
        self.assertGreater(app.session_state['result']['kpis']['approved_positions'], 0)


if __name__ == '__main__':
    unittest.main()
