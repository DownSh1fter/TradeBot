# Validation evidence / Проверка изменений

[Русское руководство](REWORK.ru.md) · [English guide](REWORK.en.md)

## Русский

### Диагноз

Присланная выдержка содержит 36 записей наблюдателя: 35 успешных оценок neutral и одну ошибку. Поле технического сигнала отсутствует/равно null во всех снимках; торговых записей `events` нет. Отсутствие сделок исполнителя нельзя доказать или опровергнуть этим файлом: это лог другого процесса. Пользователь выбрал единый запуск, чтобы устранить эту неоднозначность.

### Выполненные проверки

- Причинность: решения для префикса свечей совпадают с теми же решениями при добавлении будущих свечей.
- На искусственном установленном тренде без нового EMA-пересечения новая политика выдаёт допустимые сигналы long/short.
- Во флэте, при широком спреде и слишком маленьком расстоянии до цели принудительных входов нет.
- Полный paper-цикл: вход, цель, выход, cooldown и журнал JSONL.
- Подставной Bybit: SL/TP, риск/округление/минимумы, свободный баланс, дневная equity-блокировка, допустимость защитных reduce-only ордеров, отказ при чужой позиции/заявках, read-only ожидание заявки/позиции без повторной отправки.
- Неоднозначные ордера и неподтверждённая защита сохраняют pending_order.
- Дочерний аналитик запускается/останавливается владельцем; BYBIT_* и TELEGRAM_* удаляются из его окружения.
- Новости: ограниченные HTTPS-переходы, запрет downgrade до HTTP, фильтр crypto/macro, ограничение количества ссылок модели.
- CLI сравнительного теста выполнен на замороженном синтетическом OHLCV-файле, с SHA256 входа и раздельной последующей выборкой без сделок в прогреве.

### Отрицательный контроль — случайное движение, не реальные котировки

Проверка не подбирала параметры, чтобы скрыть убытки. 1500 искусственных баров: старт 10000, изменения `random.Random(seed).gauss(0,18)`, открытие равно прошлому закрытию, high/low расширены на 8, объём 100, шаг времени 15 минут. Начальный капитал 1000, комиссия 0.00055 и проскальзывание 0.0002 с каждой стороны.

| Seed | EMA-cross: сделки / net PnL | Trend-pullback: сделки / net PnL |
|---|---|---|
| 7 | 28 / +1.645 | 42 / -20.516 |
| 42 | 32 / -10.001 | 41 / -18.644 |
| 123 | 32 / -15.776 | 33 / -11.373 |

Новая политика не выигрывает универсально и в этих трёх случайных сценариях убыточна. Больше сделок не равно больше прибыли. Эти числа — проверка поведения на искусственной модели, не статистика BTC или прогноз. Положительные результаты на искусственном тренде также не подтверждают доходность.

### Ограничения проверки

Обращения к Bybit market API и архиву Binance из облачной среды отклонены прокси с CONNECT 403. Независимого теста на текущей биржевой истории и исполнения новой политики с настоящими Demo-ключами здесь нет. Короткие присланные снимки признаков не содержат полных OHLCV, их нельзя превращать в выдуманный бэктест сделок.

Исторический движок не моделирует funding, ликвидации, стакан, шаг объёма и минимумы биржи. Online это дополнительно фильтруется, поэтому исторический PnL может отличаться. Нужны замороженные реальные данные, независимые будущие периоды и forward Demo. Реальные деньги этой версией не поддерживаются.

## English

The supplied excerpt contains 36 observer records: 35 neutral successful assessments and one error. Technical signals are absent/null throughout. There is no execution-process journal, so it cannot establish whether trading ran. The user requested single-command operation to remove this ambiguity.

Tests cover prefix invariance/no lookahead, existing-trend long/short entry, flat/cost/spread rejection, a full audited paper roundtrip, mocked Bybit SL/TP and sizing/minimums, equity entry halts without blocking exits, protective reduce-only order recognition, foreign-position/order rejection, read-only order/position polling and pending-order preservation. Supervisor tests cover lifecycle and credential stripping; RSS tests cover bounded HTTPS redirects and relevance filtering. The benchmark CLI ran against frozen synthetic OHLCV with input SHA256 and a subsequent test segment without warmup trades.

The table above is a negative control, not market performance. It uses 1500 random-walk bars starting at 10000, Gaussian increments with sigma 18 from the listed Python seeds, prior close as open, extrema extended by 8, volume 100 and 15-minute spacing. Starting equity is 1000; per-side fee/slippage are 0.00055/0.0002. The new policy loses after costs in all three scenarios and is not universally better than the baseline. Positive artificial-trend tests likewise cannot establish profitability.

The cloud proxy rejected current Bybit API and Binance archive requests with CONNECT 403. No current historical-market performance test or new-policy Demo execution with actual credentials has completed here. Feature snapshots cannot reconstruct missing OHLCV or justify invented trades. Historical modeling excludes funding, liquidations, depth and exchange sizing rules; online additional filters can change outcomes. Frozen real data, further independent periods and forward Demo remain necessary. There is no real-money mode.
