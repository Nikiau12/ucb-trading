"""Long-running market, signal, and listing workers for the Telegram bot."""

import asyncio
import math
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from trading.scan_diagnostics import summarize_scan
from trading import group_shadow


def bind_background_loops(services) -> SimpleNamespace:
    """Build loops with the entrypoint's shared services resolved at call time."""

    async def group_shadow_loop():
        """Account for model signals separately from delivery and trade state."""
        while True:
            started = time.monotonic()
            try:
                loop = asyncio.get_running_loop()
                summary = await loop.run_in_executor(None, lambda: group_shadow.sync_pending(limit=20))
                services.st.record_runtime_health(
                    "group_shadow", success=summary["market_data_errors"] == 0,
                    duration_seconds=time.monotonic() - started, details=summary,
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                services.st.record_runtime_health(
                    "group_shadow", success=False,
                    duration_seconds=time.monotonic() - started,
                    details={"error": type(exc).__name__},
                )
                services.logger.warning("group shadow accounting failed: %s", type(exc).__name__)
            await asyncio.sleep(3600)

    async def account_tracker_loop():
        while True:
            try:
                loop = asyncio.get_running_loop()
                users = await loop.run_in_executor(None, services.st.tracked_account_users)
                for user_id in users:
                    try:
                        await loop.run_in_executor(None, services.st.reconcile_account, user_id)
                    except Exception as exc:
                        services.logger.warning('account tracking unavailable: %s', type(exc).__name__)
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                services.logger.warning('account tracker failed: %s', type(exc).__name__)
            await asyncio.sleep(30)

    async def plan_scanner_loop():
        """Continuously rotate through the top-cap universe in bounded batches.

        The worker stays active between 4H closes. Each batch re-evaluates its
        markets against the most recent *closed* 4H/1D candles and live ticker;
        no new decision is invented from an unfinished candle. Persistence in
        state.py prevents overlap/recycled setups across restarts and workers.
        """
        batch_size = 8
        cursor = 0
        last_recipient_refresh = None
        rate_limit_until = 0.0
        while True:
            try:
                now = datetime.now(timezone.utc)
                decision_time = int(now.timestamp()) // (4 * 3600) * (4 * 3600)
                if int(now.timestamp()) - decision_time < 300:
                    # Let BingX finalize the just-closed 4H candle.
                    await asyncio.sleep(30)
                    continue
                if time.monotonic() < rate_limit_until:
                    await asyncio.sleep(30)
                    continue
                scan_started_at = time.monotonic()
                scan_id = uuid4().hex
                try:
                    if last_recipient_refresh is None or scan_started_at - last_recipient_refresh >= 600:
                        services.refresh_recipients()
                        last_recipient_refresh = scan_started_at
                    loop = asyncio.get_running_loop()
                    universe = await loop.run_in_executor(
                        None, services.snap.top_symbols_by_market_cap, services.SCAN_CFG["top_n_symbols"]
                    )
                    symbols = services._scan_symbols(universe)
                    if not symbols:
                        raise ValueError("empty_capitalization_universe")
                    cursor %= len(symbols)
                    batch = symbols[cursor:cursor + batch_size]
                    cursor = 0 if cursor + len(batch) >= len(symbols) else cursor + len(batch)
                    results = await loop.run_in_executor(
                        None,
                        lambda: services.sc.scan_all(
                            batch,
                            deposit=1000,  # reference only; users choose their own size
                            risk_pct=services.TRADE_CFG["default_risk_pct"],
                            lev=services.TRADE_CFG["default_lev"],
                            margin=services.TRADE_CFG["default_margin"],
                            workers=min(2, services.SCAN_CFG["workers"]),
                        ),
                    )
                    rate_limited = any(row.get("error_code") == 100410 for row in results)
                    if rate_limited:
                        rate_limit_until = time.monotonic() + 15 * 60
                        services.logger.warning("plan scanner BingX rate limit; paused for 15 minutes")
                    budget = services.st.scanner_budget_counts(decision_time, now=now)
                    sent = persisted = 0
                    if not rate_limited and budget is not None:
                        for plan in services._rank_actionable_plans(results):
                            if (budget[0] + persisted >= services.st.MAX_SCANNER_SIGNALS_PER_UTC_DAY
                                    or budget[1] + persisted >= services.st.scanner_block_limit(
                                        decision_time, budget[0] + persisted, budget[1] + persisted)):
                                break
                            conf = services._conf(plan)
                            symbol = plan.get("symbol", "")
                            side = (plan.get("primary") or {}).get("side", "skip")
                            if not services.st.should_send_alert(symbol, side, conf, plan):
                                continue
                            signal_id = await services._save_plan_signal(plan, symbol, side, conf, source="scanner")
                            if signal_id is None:
                                if plan.get("publication_error_code") == 100410:
                                    rate_limit_until = time.monotonic() + 15 * 60
                                    services.logger.warning("plan scanner publication rate limited; paused for 15 minutes")
                                    break
                                continue
                            persisted += 1
                            delivered_count = 0
                            for chat_id in list(services.notifier.active_users):
                                try:
                                    user_id = int(chat_id)
                                except (TypeError, ValueError):
                                    continue
                                if not services.st.user_accepts_symbol(user_id, symbol):
                                    continue
                                balance_unavailable = False
                                connected_balance = None
                                try:
                                    connected_balance = await loop.run_in_executor(None, services.st.refresh_user_balance, user_id)
                                except Exception:
                                    balance_unavailable = True
                                settings = services.st.get_user_settings(user_id)
                                saved_deposit = settings.get("deposit")
                                try:
                                    saved_deposit = float(saved_deposit)
                                except (TypeError, ValueError):
                                    saved_deposit = 0
                                if connected_balance is not None:
                                    saved_deposit = float(connected_balance)
                                if not math.isfinite(saved_deposit):
                                    saved_deposit = 0
                                lang = services.get_lang(user_id)
                                if balance_unavailable or saved_deposit <= 0:
                                    alert = services.render_unpriced_signal(
                                        plan, lang, empty_balance=connected_balance == 0,
                                        no_deposit=not balance_unavailable and connected_balance is None,
                                    )
                                else:
                                    alert = services.render_auto_alert(
                                        plan, symbol, side.upper(), conf,
                                        deposit=saved_deposit,
                                        risk_pct=settings.get("risk_pct", services.TRADE_CFG["default_risk_pct"]),
                                        leverage=settings.get("lev", services.TRADE_CFG["default_lev"]),
                                        lang=lang,
                                    )
                                alert = services._with_signal_identity(
                                    alert, signal_id, symbol, side, services.get_lang(user_id),
                                )
                                if await services.notifier.send_message_to_user(
                                    chat_id,
                                    alert,
                                    reply_markup=services._alert_keyboard(signal_id, services.get_lang(user_id)),
                                ):
                                    delivered_count += 1
                                    services.st.grant_signal_access(user_id, signal_id)
                            if services.st.should_persist_sent_marker(delivered_count):
                                services.st.mark_sent(symbol, side, conf, plan)
                                sent += 1
                            await asyncio.sleep(0.5)
                    services.logger.info("plan scanner continuous batch: scanned=%s alerts=%s cursor=%s/%s",
                                         len(results), sent, cursor, len(symbols))
                    summary, decisions = summarize_scan(batch, results, strategy_version=services.core_plan.VERSION)
                    summary.update(alerts_sent=sent, signals_persisted=persisted,
                                   universe_size=len(symbols), continuous_batch=True,
                                   rate_limited=rate_limited or time.monotonic() < rate_limit_until)
                    journal_saved = await loop.run_in_executor(
                        None, services.st.record_scan_run, scan_id, now, summary, decisions,
                    )
                    summary["journal_saved"] = journal_saved
                    services.st.record_runtime_health(
                        "plan_scanner", success=summary["failed"] == 0 and journal_saved
                        and budget is not None and not summary["rate_limited"],
                        duration_seconds=time.monotonic() - scan_started_at, details=summary,
                    )
                except Exception as e:
                    services.st.record_runtime_health(
                        "plan_scanner", success=False,
                        duration_seconds=time.monotonic() - scan_started_at,
                        details={"error": type(e).__name__},
                    )
                    services.logger.warning("plan scanner error: %s", type(e).__name__)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                services.logger.warning("plan_scanner_loop error: %s", type(exc).__name__)

            await asyncio.sleep(30)

    async def signal_lifecycle_loop():
        """Track public BingX prices and send one TP1/BE update per recipient."""
        while True:
            started_at = time.monotonic()
            try:
                loop = asyncio.get_running_loop()
                trackable = await loop.run_in_executor(None, services.st.load_trackable_signals)
                replay_pending = [
                    signal for signal in trackable
                    if signal.get("status") == "replay_pending"
                ][:services.SIGNAL_REPLAY_BATCH_SIZE]
                live = [
                    signal for signal in trackable
                    if signal.get("status") != "replay_pending"
                ]
                prices = {}
                if trackable:
                    prices = await loop.run_in_executor(None, services._public_signal_prices)
                replayed = 0
                audited = 0
                transitioned = 0
                unsupported = 0
                replay_errors = 0
                hourly_candle_cache: dict[str, list[dict]] = {}
                minute_candle_cache: dict[str, list[dict]] = {}
                hourly_failed_symbols: set[str] = set()
                minute_failed_symbols: set[str] = set()
                for signal in replay_pending:
                    symbol = str(signal.get("symbol") or "").upper()
                    if symbol not in prices:
                        # Old MEXC-era symbols and delisted instruments cannot be
                        # reconstructed from BingX. Their entry window is already
                        # over, so close them safely instead of blocking the queue.
                        result = await loop.run_in_executor(
                            None, services.st.replay_signal_lifecycle, int(signal["id"]), [],
                        )
                        replayed += int(bool(result))
                        unsupported += 1
                        continue
                    created_at = signal.get("created_at")
                    use_minute_candles = bool(
                        isinstance(created_at, datetime)
                        and datetime.now(timezone.utc) - created_at <= timedelta(hours=23)
                    )
                    cache = minute_candle_cache if use_minute_candles else hourly_candle_cache
                    failed_symbols = (
                        minute_failed_symbols if use_minute_candles else hourly_failed_symbols
                    )
                    if symbol in failed_symbols:
                        continue
                    if symbol not in cache:
                        try:
                            interval, limit = ("1m", 1440) if use_minute_candles else ("1h", 400)
                            cache[symbol] = await loop.run_in_executor(
                                None, services._public_signal_candles, symbol, interval, limit,
                            )
                        except Exception as exc:
                            failed_symbols.add(symbol)
                            replay_errors += 1
                            services.logger.warning(
                                "signal replay market data failed symbol=%s: %s",
                                symbol, type(exc).__name__,
                            )
                            continue
                    signal_id = int(signal["id"])
                    rows = cache[symbol]
                    resolution = 60 if use_minute_candles else 3600
                    result = await loop.run_in_executor(
                        None,
                        lambda sid=signal_id, data=rows, seconds=resolution: services.st.replay_signal_lifecycle(
                            sid, data, candle_seconds=seconds
                        ),
                    )
                    replayed += int(bool(result))
                    if result and result.get("status") in {"active", "tp1_reached"}:
                        current = await loop.run_in_executor(
                            None,
                            services.st.update_signal_lifecycle,
                            int(signal["id"]),
                            prices.get(symbol),
                        )
                        if current and current.get("events"):
                            transitioned += 1

                now = datetime.now(timezone.utc)
                audit_results: dict[int, dict] = {}
                audit_candidates = []
                for signal in live:
                    if signal.get("status") != "waiting_entry":
                        continue
                    last_audit = signal.get("entry_path_checked_at")
                    audit_due = not isinstance(last_audit, datetime) or (
                        now - last_audit >= timedelta(
                            seconds=services.SIGNAL_ENTRY_AUDIT_INTERVAL_SECONDS
                        )
                    )
                    if not audit_due:
                        continue
                    audit_candidates.append(signal)

                for signal in audit_candidates[:services.SIGNAL_ENTRY_AUDIT_BATCH_SIZE]:
                    symbol = str(signal.get("symbol") or "").upper()
                    if symbol in minute_failed_symbols:
                        continue
                    if symbol not in minute_candle_cache:
                        try:
                            minute_candle_cache[symbol] = await loop.run_in_executor(
                                None, services._public_signal_candles, symbol, "1m", 1440,
                            )
                        except Exception as exc:
                            minute_failed_symbols.add(symbol)
                            replay_errors += 1
                            services.logger.warning(
                                "waiting signal audit data failed symbol=%s: %s",
                                symbol, type(exc).__name__,
                            )
                            continue
                    result = await loop.run_in_executor(
                        None,
                        services.st.audit_waiting_signal_lifecycle,
                        int(signal["id"]),
                        minute_candle_cache[symbol],
                    )
                    if result:
                        audit_results[int(signal["id"])] = result
                        audited += 1
                        if result.get("events"):
                            transitioned += 1

                for signal in live:
                    audited_result = audit_results.get(int(signal["id"]))
                    if audited_result and audited_result.get("status") not in {
                        "waiting_entry", "active", "tp1_reached"
                    }:
                        continue
                    result = await loop.run_in_executor(
                        None,
                        services.st.update_signal_lifecycle,
                        int(signal["id"]),
                        prices.get(str(signal.get("symbol") or "").upper()),
                    )
                    if result and result.get("events"):
                        transitioned += 1

                # Resolve terminal prices first so a queued TP1/BE instruction is
                # cancelled instead of reaching users after Stop or TP2.
                pending_updates, delivered = await services._deliver_pending_signal_updates(loop)
                services.st.record_runtime_health(
                    "signal_lifecycle",
                    success=True,
                    duration_seconds=time.monotonic() - started_at,
                    details={
                        "trackable": len(trackable),
                        "replay_pending": len(replay_pending),
                        "replayed": replayed,
                        "audited_waiting": audited,
                        "unsupported": unsupported,
                        "replay_errors": replay_errors,
                        "transitioned": transitioned,
                        "pending_updates": pending_updates,
                        "delivered": delivered,
                    },
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                services.st.record_runtime_health(
                    "signal_lifecycle",
                    success=False,
                    duration_seconds=time.monotonic() - started_at,
                    details={"error": type(exc).__name__},
                )
                services.logger.warning("signal_lifecycle_loop error: %s", type(exc).__name__)
            await asyncio.sleep(services.SIGNAL_TRACKER_INTERVAL_SECONDS)

    async def listing_watcher_loop():
        while True:
            try:
                for item in (await services.listing_watcher.check_new_announcements())[:10]:
                    symbol = item["symbols"][0] if item.get("symbols") else ""
                    coin_info = await services.coin_info_svc.get_coin_info(symbol) if symbol else {}
                    listing_symbol = services._listing_symbol(symbol)
                    announcement = item
                    details = coin_info
                    await services._broadcast_personal(
                        lambda lang, news=announcement, info=details: services.notifier.format_listing_news_alert(
                            news, coin_info=info, lang=lang
                        ),
                        {
                            "symbol": listing_symbol,
                            "side": "LONG",
                            "confidence": 0,
                            "source": "listing",
                            "price": None,
                        } if listing_symbol else None,
                    )
                    await asyncio.sleep(0.2)
                for symbol in (await services.listing_watcher.check_new_markets(services.exchange))[:20]:
                    coin_info = await services.coin_info_svc.get_coin_info(symbol)
                    listing_symbol = services._listing_symbol(symbol)
                    market = symbol
                    details = coin_info
                    await services._broadcast_personal(
                        lambda lang, pair=market, info=details: services.notifier.format_listing_alert(
                            pair, coin_info=info, lang=lang
                        ),
                        {
                            "symbol": listing_symbol,
                            "side": "LONG",
                            "confidence": 0,
                            "source": "listing",
                            "price": None,
                        } if listing_symbol else None,
                    )
                    await asyncio.sleep(0.2)
                await asyncio.sleep(services.BINGX_LISTING_CHECK_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                services.logger.warning("listing_watcher_loop error: %s", type(exc).__name__)
                await asyncio.sleep(60)

    return SimpleNamespace(
        account_tracker_loop=account_tracker_loop,
        group_shadow_loop=group_shadow_loop,
        plan_scanner_loop=plan_scanner_loop,
        signal_lifecycle_loop=signal_lifecycle_loop,
        listing_watcher_loop=listing_watcher_loop,
    )
