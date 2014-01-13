# -*- coding: utf-8 -*-

import sys
sys.path.insert(0, '../../../projects/lithoxyl')
sys.path.insert(0, '../../../projects/clastic')

import base64

import clastic
from clastic import Application, Middleware, BaseResponse
from clastic.errors import BadRequest, UpgradeRequired

from gevent.pywsgi import WSGIServer, WSGIHandler
from _websocket import WebSocket


class InvalidWebSocketRequest(BadRequest):
    pass


class WebSocketConnection(object):
    def __init__(self, environ, read=None, write=None):
        self.environ = environ
        try:
            self.read = read or environ['wsgi.rfile'].read
        except (KeyError, AttributeError):
            raise ValueError('unreadable; did you monkeypatch pywsgi?')

        try:
            self.write = write or environ['wsgi.socket'].sendall
        except (KeyError, AttributeError):
            raise ValueError('unwritable; did you monkeypatch pywsgi?')

    @property
    def origin(self):
        return (self.environ or {}).get('HTTP_ORIGIN')

    @property
    def protocol(self):
        return (self.environ or {}).get('HTTP_SEC_WEBSOCKET_PROTOCOL')

    @property
    def version(self):
        return (self.environ or {}).get('HTTP_SEC_WEBSOCKET_VERSION')

    @property
    def path(self):
        return (self.environ or {}).get('PATH_INFO')


class WebSocketFactory(object):
    SUPPORTED_VERSIONS = ('13', '8', '7')
    GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(self, protocols=None):
        self.protocols = protocols or []

    def _validate_request(self, request):
        IWSR = InvalidWebSocketRequest
        environ, method = request.environ, request.method
        if method != 'GET':
            raise IWSR('WebSockets expect GET HTTP method, not %s' % method)
        # HTTP/1.1 check probably redundant given the following

        upgrade = environ.get('HTTP_UPGRADE', '').lower()
        if upgrade != 'websocket':
            raise IWSR('WebSockets expect header: "Http-Upgrade: websocket"')
        http_conn = environ.get('HTTP_CONNECTION', '').lower()
        if 'upgrade' not in http_conn:
            raise IWSR('WebSockets expect Http-Connection: upgrade')
        ws_version = environ.get('HTTP_SEC_WEBSOCKET_VERSION')
        if not ws_version:
            raise UpgradeRequired()  # TODO: supported versions header
        elif ws_version not in self.SUPPORTED_VERSIONS:
            raise IWSR('unsupported WebSocket version: %r' % ws_version)
        key = environ.get('HTTP_SEC_WEBSOCKET_KEY', '').strip()
        if not key:
            raise IWSR('expected Sec-WebSocket-Key header')
        try:
            key_len = len(base64.b64decode(key))
        except:
            raise IWSR('could not decode WebSocket key: %r' % key)
        if key_len != 16:
            raise IWSR('invalid WebSocket key length for key: %r' % key)
        return True

    def is_websocket_request(self, request):
        try:
            self._validate_request(request)
        except BadRequest:
            return False
        return True

    def get_websocket(self, request):
        self._validate_request(request)
        environ = request.environ
        key = environ.get('HTTP_SEC_WEBSOCKET_KEY', '').strip()
        protocol = environ.get('HTTP_SEC_WEBSOCKET_PROTOCOL', '')
        if self.protocols and protocol not in self.protocols:
            # TODO
            pass
        websocket_conn = WebSocketConnection(environ)
        websocket = WebSocket(environ, websocket_conn)
        return WebSocketResponse(key, protocol)


class WebSocketResponse(BaseResponse):
    def __init__(self, key, protocol=None):
        accept_token = base64.b64encode(hashlib.sha1(key + self.GUID).digest())
        headers = [("Upgrade", "websocket"),
                   ("Connection", "Upgrade"),
                   ("Sec-WebSocket-Accept", accept_token)]
        if protocol:  # hm
            headers.append(("Sec-WebSocket-Protocol", protocol))
        super(WebSocketResponse, self).__init__('Switching Protocols',
                                                status=101,
                                                headers=headers)
    def set_loop(self, loop_func):
        if not callable(loop_func):
            raise TypeError('expected a callable, got: %r' % loop_func)

    #def __call__(self, environ, start_response):
    #    # TODO: might be better to override get_app_iter()
    #    app_iter, status, headers = self.get_wsgi_response


def ws_loop(websocket):
    while websocket.ok:
        websocket.lol()
    return


def ws_endpoint(ws_factory):
    websocket = ws_factory.initiate()
    return websocket.get_response()



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


# monkey patchin
def run_application(self):
    self.environ['wsgi.rfile'] = self.rfile
    self.environ['wsgi.socket'] = self.socket
    self._old_run_application()


WSGIHandler._old_run_application = WSGIHandler.run_application
WSGIHandler.run_application = run_application
# end monkeypatchin

if __name__ == '__main__':
    wsgi_server = WSGIServer(('', 8000), application=wsgi_app)
    wsgi_server.serve_forever()
