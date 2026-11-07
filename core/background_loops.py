"""Long-running market, signal, and listing workers for the Telegram bot."""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from trading.scan_diagnostics import summarize_scan


def bind_background_loops(services) -> SimpleNamespace:
    """Build loops with the entrypoint's shared services resolved at call time."""

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
        """Refresh 4H/1D plans hourly; state.py prevents overlapping or recycled setups."""
        while True:
            try:
                now = datetime.now(timezone.utc)
                block = now.hour                      # 0..23, меняется каждый час
                minutes_since = now.minute

                if minutes_since >= 5 and services._last_plan_1h_block != block:
                    services._last_plan_1h_block = block
                    services.logger.info("plan scanner 1h block %02d:00 starting", block)
                    scan_started_at = time.monotonic()
                    scan_id = uuid4().hex
                    try:
                        services.refresh_recipients()
                        loop = asyncio.get_event_loop()
                        symbols = await loop.run_in_executor(
                            None, services.snap.top_symbols_by_market_cap, services.SCAN_CFG["top_n_symbols"]
                        )
                        symbols = services._scan_symbols(symbols)
                        results = await loop.run_in_executor(
                            None,
                            lambda: services.sc.scan_all(
                                symbols,
                                deposit=1000,  # reference only — position sizes in auto alerts are indicative
                                risk_pct=services.TRADE_CFG["default_risk_pct"],
                                lev=services.TRADE_CFG["default_lev"],
                                margin=services.TRADE_CFG["default_margin"],
                                workers=services.SCAN_CFG["workers"],
                            ),
                        )
                        sent = 0
                        persisted = 0
                        for plan in services._rank_actionable_plans(results):
                            conf   = services._conf(plan)
                            symbol = plan.get("symbol", "")
                            side   = (plan.get("primary") or {}).get("side", "skip")

                            if not services.st.should_send_alert(symbol, side, conf, plan):
                                continue

                            signal_id = await services._save_plan_signal(plan, symbol, side, conf, source="scanner")
                            if signal_id is None:
                                # Another cycle may have claimed this market after the read-only precheck.
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
                                uses_reference = saved_deposit <= 0 and not balance_unavailable and connected_balance is None
                                deposit = 0 if balance_unavailable else (services.SCAN_REFERENCE_DEPOSIT if uses_reference else saved_deposit)
                                alert = services.render_auto_alert(
                                    plan,
                                    symbol,
                                    side.upper(),
                                    conf,
                                    deposit=deposit,
                                    risk_pct=settings.get("risk_pct", services.TRADE_CFG["default_risk_pct"]),
                                    leverage=settings.get("lev", services.TRADE_CFG["default_lev"]),
                                    lang=services.get_lang(user_id),
                                    uses_reference_deposit=uses_reference,
                                )
                                if balance_unavailable or connected_balance == 0:
                                    alert = services.render_unpriced_signal(plan, services.get_lang(user_id), empty_balance=connected_balance == 0)
                                alert = services._with_signal_identity(
                                    alert, signal_id, symbol, side, services.get_lang(user_id),
                                )
                                if await services.notifier.send_message_to_user(
                                    chat_id,
                                    alert,
                                    reply_markup=services._alert_keyboard(signal_id, services.get_lang(user_id)),
                                ):
                                    delivered_count += 1
                                    if signal_id:
                                        services.st.grant_signal_access(user_id, signal_id)
                            if services.st.should_persist_sent_marker(delivered_count):
                                services.st.mark_sent(symbol, side, conf, plan)
                                sent += 1
                            await asyncio.sleep(0.5)
                        services.logger.info("plan scanner done: scanned=%s alerts=%s", len(results), sent)
                        summary, decisions = summarize_scan(
                            symbols, results, strategy_version=services.core_plan.VERSION,
                        )
                        summary.update(alerts_sent=sent, signals_persisted=persisted)
                        journal_saved = await loop.run_in_executor(
                            None, services.st.record_scan_run, scan_id, now, summary, decisions,
                        )
                        summary["journal_saved"] = journal_saved
                        services.st.record_runtime_health(
                            "plan_scanner",
                            success=summary["failed"] == 0 and journal_saved,
                            duration_seconds=time.monotonic() - scan_started_at,
                            details=summary,
                        )
                    except Exception as e:
                        services.st.record_runtime_health(
                            "plan_scanner",
                            success=False,
                            duration_seconds=time.monotonic() - scan_started_at,
                            details={"error": type(e).__name__},
                        )
                        services.logger.warning("plan scanner error: %s", type(e).__name__)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                services.logger.warning("plan_scanner_loop error: %s", type(exc).__name__)

            await asyncio.sleep(60)

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
        plan_scanner_loop=plan_scanner_loop,
        signal_lifecycle_loop=signal_lifecycle_loop,
        listing_watcher_loop=listing_watcher_loop,
    )
