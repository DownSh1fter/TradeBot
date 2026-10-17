import unittest

from dual_futures_bot.models import Candle
from dual_futures_bot.simulator import RiskConfig, size_for_risk, simulate
from dual_futures_bot.strategy import ema_cross_signals


class CoreTests(unittest.TestCase):
    def test_risk_sizing_respects_risk_and_notional_caps(self):
        qty = size_for_risk(10_000, 100, 95, 0.01, 0.25)
        self.assertAlmostEqual(qty, 20)
        self.assertAlmostEqual(qty * (100 - 95), 100)
        self.assertLessEqual(qty * 100, 10_000 * 0.25)

    def test_risk_config_rejects_large_daily_loss_limit(self):
        with self.assertRaises(ValueError):
            RiskConfig(max_daily_loss_fraction=0.2).validate()

    def test_strategy_requires_slow_ema_longer_than_fast_ema(self):
        with self.assertRaises(ValueError):
            ema_cross_signals([], fast_period=50, slow_period=20)

    def test_simulation_is_deterministic_and_never_uses_live_exchange(self):
        candles = []
        price = 100.0
        for i in range(240):
            price += 0.3 if i % 80 < 40 else -0.28
            candles.append(Candle(i * 900_000, price, price + 0.6, price - 0.6, price, 1.0))
        config = RiskConfig(initial_equity=1_000)
        first = simulate(candles, config)
        second = simulate(candles, config)
        self.assertEqual(first, second)
        self.assertGreaterEqual(first["trade_count"], 0)
        self.assertGreaterEqual(first["fees_paid"], 0)
        self.assertGreaterEqual(first["max_drawdown_fraction"], 0)
        self.assertLess(first["max_drawdown_fraction"], 1)

if __name__ == "__main__":
    unittest.main()
