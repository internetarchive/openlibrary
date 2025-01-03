import time

from pyinstrument import Profiler


def pre_request(worker, req):
    worker.profiler = Profiler()
    worker.profiler.start()


def post_request(worker, req, environ, resp):
    worker.profiler.stop()
    # print(JSONRenderer().render(session=worker.profiler.last_session))
    # print(worker.profiler.output_text(unicode=True, color=True))

    location = f"profiles/{int(time.time())}_{req.path.replace('/', '_')}.html"
    if not any(ext in req.path for ext in ['.gif', '.png', '.js', '_partials']):
        worker.profiler.write_html(location)
