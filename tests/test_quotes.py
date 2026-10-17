import unittest
from unittest.mock import Mock
from dual_futures_bot.realtime import fetch_quote


class QuoteTests(unittest.TestCase):
    def exchange(self):
        ex = Mock()
        ex.milliseconds.return_value = 100_000
        ex.fetch_ticker.return_value = {'timestamp': None, 'last': 100}
        ex.fetch_order_book.return_value = {'timestamp': 99_000, 'bids': [[99, 1]], 'asks': [[101, 1]]}
        return ex

    def test_bybit_missing_ticker_timestamp_uses_timestamped_midpoint(self):
        ex = self.exchange()
        quote = fetch_quote(ex, 'BTC/USDT:USDT')
        self.assertEqual(quote['last'], 100)
        self.assertEqual(quote['timestamp'], 99_000)
        self.assertEqual(quote['source'], 'orderbook_midpoint')

    def test_timestamped_ticker_keeps_last_price(self):
        ex = self.exchange()
        ex.fetch_ticker.return_value = {'timestamp': 99_000, 'last': 102}
        self.assertEqual(fetch_quote(ex, 'BTC')['last'], 102)
        ex.fetch_order_book.assert_not_called()

    def test_invalid_orderbooks_rejected(self):
        for book in ({'timestamp': 0, 'bids': [[99]], 'asks': [[101]]},
                     {'timestamp': None, 'bids': [[99]], 'asks': [[101]]},
                     {'timestamp': 101_000, 'bids': [[99]], 'asks': [[101]]},
                     {'timestamp': 99_000, 'bids': [], 'asks': [[101]]},
                     {'timestamp': 99_000, 'bids': [[102]], 'asks': [[101]]},
                     {'timestamp': 99_000, 'bids': [[float('nan')]], 'asks': [[101]]}):
            with self.subTest(book=book):
                ex = self.exchange()
                ex.fetch_order_book.return_value = book
                with self.assertRaises(ValueError): fetch_quote(ex, 'BTC')

    def test_stale_ticker_is_not_replaced_with_fresh_orderbook(self):
        ex = self.exchange()
        ex.fetch_ticker.return_value = {'timestamp': 1, 'last': 100}
        with self.assertRaises(ValueError): fetch_quote(ex, 'BTC')
        ex.fetch_order_book.assert_not_called()
