# UCB Trading — product walkthrough

UCB Trading is a Telegram bot plus a Mini App. The bot brings a setup. The panel opens that same setup.

Screenshots of the old dense card are not part of this walkthrough. The current screens are the ones below.

## 1. First minute in chat

`/start` asks for a language and shows only the five language buttons. After a language is chosen, the next message asks for a deposit amount, with `5000` as the example. After that amount is saved, one message shows the deposit, the default risk, «Открыть», and «План по BTC». Language buttons are not attached to later messages. `/help` stays in the command menu.

## 2. A short alert

An automatic alert, `/scan`, and the detail under `/digest` use one block of at most eight lines: symbol and side, entry, stop, TP1, position size, and one caveat when leverage was cut or the contract is below the minimum. Each of those messages has «Открыть» for that `signal_id` and «Позже». The longer plan text is only the `/plan` screen.

## 3. The plan screen

The Mini App home is the latest plan: symbol, side, price, the rules-estimate sentence next to the confidence percent, entry/stop/TP lines on the chart, then position size, margin, and stop risk. The bot calculates the size. The person places the order.

## 4. The signal list

Each row is the symbol, the side, reward/risk to TP1, and age. A tap opens that plan. An empty list says whether the scanner was silent or the LONG/SHORT filter is empty, and it shows the time of the last scan.

## 5. Settings and payment

Settings is one screen: deposit, risk, leverage, margin, and language. `/set` answers that the change was saved and includes a button that opens the panel. Payment is one sheet with three states: waiting for the check, it did not match, and access is open until a date.
