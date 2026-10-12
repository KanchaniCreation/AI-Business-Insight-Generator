"""Run the real Streamlit script headlessly: it must never raise on either sample dataset."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "app" / "app.py"


@pytest.mark.parametrize("button", ["Sample (₹)", "Superstore-like ($)"])
def test_app_runs_end_to_end(button, tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("LLM_API_KEY", "")
    at = AppTest.from_file(str(APP), default_timeout=180).run()
    assert not at.exception
    [b for b in at.sidebar.button if b.label == button][0].click().run()
    assert not at.exception
    [b for b in at.button if "Run data cleaning" in b.label][0].click().run()
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert "Revenue" in labels and "Profit margin" in labels
    [b for b in at.button if "Generate" in b.label][0].click().run()
    assert not at.exception
