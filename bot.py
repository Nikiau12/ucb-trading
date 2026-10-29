"""Production entry point for UCB Trading."""
import asyncio

from bot_mexc import main


if __name__ == "__main__":
    asyncio.run(main())
