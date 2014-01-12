from gevent.pywsgi import WSGIServer

from .handler import WebSocketHandler
from .logging import create_logger


class WebSocketServer(WSGIServer):
    debug_log_format = (
        '-' * 80 + '\n' +
        '%(levelname)s in %(module)s [%(pathname)s:%(lineno)d]:\n' +
        '%(message)s\n' +
        '-' * 80
    )

    def __init__(self, *args, **kwargs):
        self.debug = kwargs.pop('debug', False)
        self._logger = None
        self.clients = {}

        kwargs['handler_class'] = WebSocketHandler
        super(WebSocketServer, self).__init__(*args, **kwargs)

    def handle(self, socket, address):
        # wtf 3: this is exactly what's in gevent's pywsgi
        handler = self.handler_class(socket, address, self)
        handler.handle()

    @property
    def logger(self):
        if not self._logger:
            self._logger = create_logger(
                __name__, self.debug, self.debug_log_format)

        return self._logger
