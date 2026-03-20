"""
Declarative Shadow DOM (DSD) helpers for Lit web components.

Uses the official @lit-labs/ssr package to render components server-side,
producing <template shadowrootmode="open"> HTML that the browser renders
instantly during HTML parsing — before any JavaScript loads.

The rendering is done by a persistent Node.js subprocess that runs
@lit-labs/ssr with the real Lit component code. This means:
- No manual HTML replication — components render themselves
- Lit template markers are included for proper client-side hydration
- Adding a new component requires zero Python code changes

Architecture:
    Python (dsd.py) ←→ Node.js (ssr/server.mjs) ←→ @lit-labs/ssr ←→ Lit components

Usage in Templetor templates:
    $:dsd_read_more(max_height="80px", more_text="Read More", less_text="Read Less")
        <p>Content here...</p>
    $:dsd_read_more_close()

    $:dsd_pagination(current_page=1, total_pages=10)
"""

import atexit
import json
import logging
import os
import subprocess
import threading
from html import escape

logger = logging.getLogger(__name__)

# Path to the Node.js SSR server script
_SSR_SERVER_SCRIPT = os.path.join(
    os.path.dirname(__file__),
    '..',
    'components',
    'lit',
    'ssr',
    'server.mjs',
)

# Persistent Node.js SSR subprocess (lazy-started, thread-safe)
_ssr_process: subprocess.Popen | None = None
_ssr_lock = threading.Lock()
_ssr_available: bool | None = None


def _start_ssr_server() -> subprocess.Popen | None:
    """Start the persistent Node.js SSR server subprocess."""
    global _ssr_process, _ssr_available

    if _ssr_available is False:
        return None

    try:
        proc = subprocess.Popen(
            ['node', _SSR_SERVER_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait for the "ready" signal
        assert proc.stdout is not None  # guaranteed by stdout=PIPE
        ready_line = proc.stdout.readline()
        if not ready_line:
            logger.warning('SSR server failed to start (no output)')
            proc.kill()
            _ssr_available = False
            return None

        ready = json.loads(ready_line)
        if not ready.get('ready'):
            logger.warning('SSR server sent unexpected ready signal: %s', ready)
            proc.kill()
            _ssr_available = False
            return None

        _ssr_available = True
        _ssr_process = proc
        atexit.register(_shutdown_ssr_server)
        return proc

    except FileNotFoundError:
        logger.warning('Node.js not found — SSR disabled, components will render client-side')
        _ssr_available = False
        return None
    except Exception:
        logger.warning('Failed to start SSR server', exc_info=True)
        _ssr_available = False
        return None


def _shutdown_ssr_server():
    """Cleanly shut down the SSR server on process exit."""
    global _ssr_process
    if _ssr_process and _ssr_process.poll() is None:
        if _ssr_process.stdin:
            _ssr_process.stdin.close()
        _ssr_process.wait(timeout=5)
        _ssr_process = None


def _get_ssr_server() -> subprocess.Popen | None:
    """Get the running SSR server, starting it if needed. Thread-safe."""
    global _ssr_process

    if _ssr_available is False:
        return None

    if _ssr_process and _ssr_process.poll() is None:
        return _ssr_process

    with _ssr_lock:
        # Double-check after acquiring lock
        if _ssr_process and _ssr_process.poll() is None:
            return _ssr_process
        return _start_ssr_server()


def _ssr_render(tag: str, attrs: dict[str, str], content: str = '') -> str | None:
    """
    Render a component via the Node.js SSR server.

    Returns the rendered HTML string, or None if SSR is unavailable.
    """
    proc = _get_ssr_server()
    if not proc:
        return None

    request = {'tag': tag, 'attrs': attrs, 'content': content}

    with _ssr_lock:
        try:
            assert proc.stdin is not None  # guaranteed by stdin=PIPE
            assert proc.stdout is not None  # guaranteed by stdout=PIPE
            proc.stdin.write(json.dumps(request) + '\n')
            proc.stdin.flush()
            response_line = proc.stdout.readline()
            if not response_line:
                logger.warning('SSR server returned empty response')
                return None
            response = json.loads(response_line)
            if 'error' in response:
                logger.warning('SSR render error: %s', response['error'])
                return None
            return response.get('html')
        except (BrokenPipeError, OSError):
            logger.warning('SSR server connection lost', exc_info=True)
            _shutdown_ssr_server()
            return None


def _build_attrs(
    component_attrs: dict[str, str | None], extra_attrs: dict[str, str]
) -> dict[str, str]:
    """Build the combined attribute dict for a component."""
    attrs = {}
    for key, value in component_attrs.items():
        if value is not None:
            attrs[key] = str(value)
    for key, value in extra_attrs.items():
        attr_name = key.replace('_', '-')
        attrs[attr_name] = str(value)
    return attrs


def dsd_read_more(
    max_height: str = '80px',
    more_text: str = 'Read More',
    less_text: str = 'Read Less',
    label_size: str = 'medium',
    background_color: str | None = None,
    **attrs: str,
) -> str:
    """
    Generate the opening tag + DSD for an ol-read-more component.

    Returns the <ol-read-more ...><template shadowrootmode="open">...</template>
    opening. Caller must close with dsd_read_more_close() after the slot content.

    The shadow DOM HTML is rendered by the official @lit-labs/ssr package using
    the real component code — no manual HTML replication needed.

    Args:
        max_height: CSS max-height value (default "80px")
        more_text: "Read More" button text
        less_text: "Read Less" button text
        label_size: "medium" or "small"
        background_color: Optional background color for gradient
        **attrs: Additional HTML attributes (class, style, id, etc.)
    """
    component_attrs = {
        'max-height': max_height,
        'more-text': more_text,
        'less-text': less_text,
        'label-size': label_size if label_size != 'medium' else None,
        'background-color': background_color,
    }
    all_attrs = _build_attrs(component_attrs, attrs)

    # Try SSR rendering via @lit-labs/ssr
    # We render with a placeholder slot content, then split to extract
    # just the opening tag + DSD template
    ssr_html = _ssr_render('ol-read-more', all_attrs, '')
    if ssr_html:
        # The SSR output is a complete element. We need just the opening part
        # (everything up to and including </template>) so the template can
        # inject slot content before the closing tag.
        close_tag = '</ol-read-more>'
        # Find where </template> ends — everything after is the closing tag area
        template_end = ssr_html.find('</template>')
        if template_end != -1:
            # Return everything up to and including </template>
            return ssr_html[: template_end + len('</template>')]

    # Fallback: return a plain custom element (no DSD, client-side rendering)
    attr_str = ' '.join(
        f'{k}="{escape(v)}"' for k, v in all_attrs.items()
    )
    return f'<ol-read-more {attr_str}>'


def dsd_read_more_close() -> str:
    """Close an ol-read-more component opened with dsd_read_more()."""
    return '</ol-read-more>'


def dsd_pagination(
    current_page: int = 1,
    total_pages: int = 1,
    base_url: str = '',
    label_previous_page: str = 'Go to previous page',
    label_next_page: str = 'Go to next page',
    label_go_to_page: str = 'Go to page {page}',
    label_current_page: str = 'Page {page}, current page',
    label_pagination: str = 'Pagination',
    **attrs: str,
) -> str:
    """
    Generate a complete ol-pagination component with DSD.

    Returns the full <ol-pagination>...</ol-pagination> element with
    pre-rendered shadow DOM from @lit-labs/ssr.
    """
    component_attrs = {
        'total-pages': str(total_pages),
        'current-page': str(current_page),
        'base-url': base_url or None,
        'label-previous-page': (
            label_previous_page
            if label_previous_page != 'Go to previous page'
            else None
        ),
        'label-next-page': (
            label_next_page if label_next_page != 'Go to next page' else None
        ),
        'label-go-to-page': (
            label_go_to_page
            if label_go_to_page != 'Go to page {page}'
            else None
        ),
        'label-current-page': (
            label_current_page
            if label_current_page != 'Page {page}, current page'
            else None
        ),
        'label-pagination': (
            label_pagination if label_pagination != 'Pagination' else None
        ),
    }
    all_attrs = _build_attrs(component_attrs, attrs)

    # Try SSR rendering via @lit-labs/ssr
    ssr_html = _ssr_render('ol-pagination', all_attrs)
    if ssr_html:
        return ssr_html

    # Fallback: plain custom element (client-side rendering)
    attr_str = ' '.join(
        f'{k}="{escape(v)}"' for k, v in all_attrs.items()
    )
    return f'<ol-pagination {attr_str}></ol-pagination>'
