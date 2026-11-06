from src.config import load_config
from src.data.provider import make_multi_tf_pair
from src.backtest.engine import run_backtest


def test_backtest_runs():
    cfg = load_config("config.example.yaml")
    data = {}
    for i, pair in enumerate(cfg.pairs[:2]):
        data[pair] = make_multi_tf_pair(n_entry=1200, seed=10 + i)
    res = run_backtest(data, cfg)
    assert "metrics" in res
    assert "equity_curve" in res
    assert res["metrics"]["n_trades"] >= 0
    assert len(res["equity_curve"]) > 0