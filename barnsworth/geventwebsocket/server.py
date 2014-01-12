from gevent.pywsgi import WSGIServer

from .handler import WebSocketHandler


class WebSocketServer(WSGIServer):
    def __init__(self, *args, **kwargs):
        self.debug = kwargs.pop('debug', False)
        self.clients = {}

        kwargs['handler_class'] = WebSocketHandler
        super(WebSocketServer, self).__init__(*args, **kwargs)

    def handle(self, socket, address):
        # wtf 3: this is exactly what's in gevent's pywsgi
        handler = self.handler_class(socket, address, self)
        handler.handle()
