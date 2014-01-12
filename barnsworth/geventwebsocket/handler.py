import base64
import hashlib

from gevent.pywsgi import WSGIHandler
from .websocket import WebSocket, Stream
from .logging import LOG

from clastic.errors import BadRequest, UpgradeRequired


class InvalidWebSocketRequest(BadRequest):
    pass


class Client(object):
    def __init__(self, address, ws):
        self.address = address
        self.ws = ws


class WebSocketFactory(object):
    SUPPORTED_VERSIONS = ('13', '8', '7')
    GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def __init__(self, protocols=None):
        self.protocols = protocols or []

    def _validate_request(self, request):
        IWSR = InvalidWebSocketRequest
        if request.method != 'GET':
            msg = 'WebSockets expect GET HTTP method, not %s' % request.method
            raise IWSR(msg)
        # HTTP/1.1 check probably redundant given the following
        environ = request.environ
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
        protocol = environ.get('HTTP_SEC_WEBSOCKET_PROTOCOL', '')
        if self.protocols and protocol not in self.protocols:
            # TODO
            pass
        pass


class WebSocketHandler(WSGIHandler):
    SUPPORTED_VERSIONS = ('13', '8', '7')
    GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

    def run_application(self):
        self.result = self.upgrade_websocket()

        if hasattr(self, 'websocket'):
            if self.status and not self.headers_sent:
                self.write('')

            self.run_websocket()
        else:
            if self.status:
                # A status was set, likely an error so just send the response
                if not self.result:
                    self.result = []

                self.process_result()
                return

            # This handler did not handle the request, so defer it to the
            # underlying application object
            return super(WebSocketHandler, self).run_application()

    def start_response(self, status, headers, exc_info=None):
        """
        Called when the handler is ready to send a response back to the remote
        endpoint. A websocket connection may have not been created.
        """
        writer = super(WebSocketHandler, self).start_response(
            status, headers, exc_info=exc_info)

        if not self.environ.get('wsgi.websocket'):
            # a WebSocket connection is not established, do nothing
            return

        # So that `finalize_headers` doesn't write a Content-Length header
        self.provided_content_length = False
        # The websocket is now controlling the response
        self.response_use_chunked = False
        # Once the request is over, the connection must be closed
        self.close_connection = True
        # Prevents the Date header from being written
        self.provided_date = True

        return writer

    def upgrade_websocket(self):
        req_method = self.environ.get('REQUEST_METHOD', '')
        if req_method != 'GET':
            LOG.debug('method check').failure('needs GET, not {}', req_method)
            return

        if self.request_version != 'HTTP/1.1':
            self.start_response('402 Bad Request', [])  # wtf 402 Payment Required?
            LOG.debug('HTTP version check').failure('needs HTTP/1.1, not {}',
                                                    self.request_version)
            return ['websockets requires an HTTP/1.1 client']

        upgrade = self.environ.get('HTTP_UPGRADE', '').lower()
        if upgrade != 'websocket':
            return
        connection = self.environ.get('HTTP_CONNECTION', '').lower()
        if 'upgrade' not in connection:
            return

        if self.environ.get('HTTP_SEC_WEBSOCKET_VERSION'):
            return self.upgrade_connection()
        else:
            self.start_response('426 Upgrade Required', [
                ('Sec-WebSocket-Version', ', '.join(self.SUPPORTED_VERSIONS))])
            return ['No Websocket protocol version defined']

    def upgrade_connection(self):
        version = self.environ.get("HTTP_SEC_WEBSOCKET_VERSION")

        if version not in self.SUPPORTED_VERSIONS:
            LOG.info('ws version').failure('unsupported: {}', version)
            self.start_response('400 Bad Request', [
                ('Sec-WebSocket-Version', ', '.join(self.SUPPORTED_VERSIONS))])
            return ['unsupported websocket version %s' % version]

        key = self.environ.get("HTTP_SEC_WEBSOCKET_KEY", '').strip()
        if not key:
            # 5.2.1 (3)
            msg = "Sec-WebSocket-Key header is missing/empty"
            self.start_response('400 Bad Request', [])
            return [msg]

        try:
            key_len = len(base64.b64decode(key))
        except TypeError:
            msg = "Invalid key: %r" % key
            self.start_response('400 Bad Request', [])
            return [msg]

        if key_len != 16:
            # 5.2.1 (3)
            msg = "Invalid key: %r" % key
            self.start_response('400 Bad Request', [])
            return [msg]

        # Check for WebSocket Protocols
        protocol = None
        if hasattr(self.application, 'app_protocol'):
            req_protocols = self.environ.get('HTTP_SEC_WEBSOCKET_PROTOCOL', '')
            allowed_protocol = self.application.app_protocol(
                self.environ['PATH_INFO'])

            if allowed_protocol and allowed_protocol in req_protocols:
                protocol = allowed_protocol

        self.websocket = WebSocket(self.environ, Stream(self), self)
        self.environ.update({'wsgi.websocket_version': version,
                             'wsgi.websocket': self.websocket})

        accept_token = base64.b64encode(hashlib.sha1(key + self.GUID).digest())
        headers = [("Upgrade", "websocket"),
                   ("Connection", "Upgrade"),
                   ("Sec-WebSocket-Accept", accept_token)]
        if protocol:  # hm
            headers.append(("Sec-WebSocket-Protocol", protocol))
        self.start_response("101 Switching Protocols", headers)

    def run_websocket(self):
        # In case WebSocketServer is not used
        if not hasattr(self.server, 'clients'):
            self.server.clients = {}

        # Since we're now a websocket connection, we don't care what the
        # application actually responds with for the http response

        try:
            self.server.clients[self.client_address] = Client(
                self.client_address, self.websocket)
            self.application(self.environ, lambda s, h: [])
        finally:
            del self.server.clients[self.client_address]
            if not self.websocket.closed:
                self.websocket.close()
