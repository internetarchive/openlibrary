"""
Threaded context for infogami.
"""
import web

class InfogamiContext:
    """
    Threaded context for infogami.
    Uses web.ctx for providing a thread-specific context for infogami.
    """
    def __getattr__(self, key):
        return getattr(web.ctx.infogami_ctx, key)

    def __setattr__(self, key, value):
        setattr(web.ctx.infogami_ctx, key, value)

    def load(self):
        """Initializes context for the calling thread."""
        web.ctx.infogami_ctx = web.storage()

context = InfogamiContext()
