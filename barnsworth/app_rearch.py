# -*- coding: utf-8 -*-

import sys
sys.path.insert(0, '../../../projects/lithoxyl')
sys.path.insert(0, '../../../projects/clastic')

import clastic
from clastic import Application, Middleware

from geventwebsocket.handler import WebSocketFactory
from gevent.pywsgi import WSGIServer


class WebSocketMiddleware(Middleware):
    provides = ('websocket',)

    def request(self, next, request):
        wsf = WebSocketFactory()
        print wsf.is_websocket_request(request)
        return next(websocket=wsf)


def ws_endpoint(websocket):
    print websocket
    import pdb;pdb.set_trace()
    return {'websocket': websocket}


def create_app():
    routes = [('/', ws_endpoint, clastic.render_json_dev)]
    middlewares = [WebSocketMiddleware()]
    resources = {}
    return Application(routes, resources, middlewares=middlewares)


wsgi_app = create_app()


from gevent.pywsgi import WSGIHandler


def run_application(self):
    self.environ['wsgi.rfile'] = self.rfile
    self.environ['wsgi.socket'] = self.socket
    self._old_run_application()


WSGIHandler._old_run_application = WSGIHandler.run_application
WSGIHandler.run_application = run_application


if __name__ == '__main__':
    wsgi_server = WSGIServer(('', 8000), application=wsgi_app)
    wsgi_server.serve_forever()
