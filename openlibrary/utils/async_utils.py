import asyncio
import threading

# Start a persistent event loop in a background thread.
# This avoids creating/destroying a loop on every call to select().
# More importantly, this lets us call async code from sync code.
# This is important to avoid having duplicate code paths while we start
# experimenting with async code.
# In the ideal world we won't need this as we'll be async all the way down.

# You may be wondering why we don't use syncify from asyncer. The reason is that it just doesn't work.
# Also, who needs an extra library when these few lines work for us.


class AsyncBridge:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def run(self, coro):
        try:
            # Check if we're in an async context
            asyncio.get_running_loop()
            # If we are, return the coroutine to be awaited
            return coro
        except RuntimeError:
            # No running loop, we can use asyncio.run()
            return asyncio.run_coroutine_threadsafe(coro, self._loop).result()


async_bridge = AsyncBridge()
