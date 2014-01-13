# -*- coding: utf-8 -*-

import sys
sys.path.insert(0, '../../../projects/lithoxyl')
sys.path.insert(0, '../../../projects/clastic')

import base64
import hashlib

import clastic
from clastic import Application, Middleware, BaseResponse
from clastic.errors import BadRequest, UpgradeRequired

import gevent
from gevent.pywsgi import WSGIServer, WSGIHandler
from _websocket import WebSocket

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class InvalidWebSocketRequest(BadRequest):
    pass


class WebSocketFactory(object):
    SUPPORTED_VERSIONS = ('13', '8', '7')

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

    def get_websocket_response(self, request):
        try:
            self._validate_request(request)
        except Exception as e:
            print e
            raise
        environ = request.environ
        ws_conn = WebSocketConnection(environ)
        environ['wsgi.websocket'] = ws_conn
        if self.protocols and ws_conn.protocol not in self.protocols:
            # TODO
            pass
        return WebSocketResponse(ws_conn)


class WebSocketConnection(object):
    def __init__(self, environ, read=None, write=None):
        self.environ = environ
        self.key = environ.get('HTTP_SEC_WEBSOCKET_KEY', '').strip()
        try:
            self.read = read or environ['wsgi.rfile'].read
        except (KeyError, AttributeError):
            raise ValueError('unreadable; did you monkeypatch pywsgi?')
        try:
            self.write = write or environ['wsgi.socket'].sendall
        except (KeyError, AttributeError):
            raise ValueError('unwritable; did you monkeypatch pywsgi?')

        self.websocket = WebSocket(self)  # TODO: look into merging these

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


class WebSocketResponse(BaseResponse):
    def __init__(self, connection):
        self.loop_func = None
        self.connection = connection
        key = connection.key
        protocol = connection.protocol
        accept_token = base64.b64encode(hashlib.sha1(key + WS_GUID).digest())
        headers = [("Upgrade", "websocket"),
                   ("Connection", "Upgrade"),
                   ("Sec-WebSocket-Accept", accept_token)]
        if protocol:  # hm
            headers.append(("Sec-WebSocket-Protocol", protocol))
        super(WebSocketResponse, self).__init__('Switching Protocols',
                                                status='101 Switching Protocols',
                                                headers=headers)

    def set_loop(self, loop_func):
        if not callable(loop_func):
            raise TypeError('expected a callable, got: %r' % loop_func)
        self.loop_func = loop_func

    def __call__(self, environ, start_response):
        ret = super(WebSocketResponse, self).__call__(environ, start_response)
        # return is ignored
        if callable(self.loop_func):
            gevent.spawn(self.loop_func, self.connection)
        else:
            "log"
        return ret


class WebSocketMiddleware(Middleware):
    provides = ('websocket_factory',)

    def request(self, next, request):
        wsf = WebSocketFactory()
        print wsf.is_websocket_request(request)
        return next(websocket_factory=wsf)


clients = []


def ws_loop(ws_conn):
    print 'what what'
    i = 0
    clients.append(ws_conn)
    #gevent.spawn_later(3, lambda: ws_conn.websocket.send('{"hi": %s}' % i))
    while True:
        #i += 1
        print i
        try:
            msg = ws_conn.websocket.receive()
            ws_conn.websocket.send(msg)
        except Exception as e:
            print e
            break
    return
    #while True:
    #    gevent.sleep(1.0)
    #    print i
    #
    #    i += 1


def ws_endpoint(request, websocket_factory):
    resp = websocket_factory.get_websocket_response(request)
    resp.set_loop(ws_loop)
    return resp


def create_app():
    routes = [('/', ws_endpoint, clastic.render_json_dev)]
    middlewares = [WebSocketMiddleware()]
    resources = {}
    return Application(routes, resources, middlewares=middlewares)


wsgi_app = create_app()


# monkey patchin
def run_application(self):
    def wrapped_start_response(status, headers, exc_info=None):
        if self.environ.get('wsgi.websocket'):
            # So that `finalize_headers` doesn't write a Content-Length header
            self.provided_content_length = False
            # The websocket is now controlling the response
            self.response_use_chunked = False
            # Once the request is over, the connection must be closed
            self.close_connection = True
            # Prevents the Date header from being written
            self.provided_date = True
        return self.start_response(status, headers, exc_info=exc_info)
    self.environ['wsgi.rfile'] = self.rfile
    self.environ['wsgi.socket'] = self.socket
    self.result = self.application(self.environ, wrapped_start_response)

    self.process_result()
    #self._old_run_application()


WSGIHandler._old_run_application = WSGIHandler.run_application
WSGIHandler.run_application = run_application
# end monkeypatchin

if __name__ == '__main__':
    wsgi_server = WSGIServer(('', 9000), application=wsgi_app)
    wsgi_server.serve_forever()
