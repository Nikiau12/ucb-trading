# ReleaseProof check for UCB Trading

This repository has an opt-in ReleaseProof check for changes to text shown by the bot. Add the `releaseproof` label to a pull request from this repository to run it.

The check renders four fixed, synthetic situations from the base and candidate commits:

1. Signal price reached TP1 without a confirmed personal order fill.
2. A linked personal TP1 order fill was confirmed.
3. Futures balance is zero.
4. Market data is stale.

ReleaseProof compares the two sets of replies against the saved project requirements and links a private report from the GitHub Actions job summary. The fixture does not call BingX, use account credentials, place orders, or verify live market state. A successful check covers these four text paths only.

The workflow reads `RELEASEPROOF_TOKEN` from this repository's Actions secrets. Keep the value out of commits and pull request descriptions.
