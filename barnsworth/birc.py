
import json
import sys
sys.path.insert(0, '../../wikimon')  # or pip install wikimon, maybe


from geventwebsocket import (WebSocketServer,
                             WebSocketApplication,
                             Resource)
from geventirc import Client as IRCClient
from geventirc.message import Join

from wikimon.parsers import parse_irc_message

# TODO: extract/reconstruct upload URL
# TODO: gevent websockets spinning too hard when there are no clients?
# TODO: handle nick already in use
# TODO: hashtags

server = None

DEFAULT_IRC_NICK = 'barnsworth'
DEFAULT_IRC_SERVER = 'irc.wikimedia.org'
DEFAULT_IRC_PORT = 6667
DEFAULT_IRC_CHANNELS = ['en.wikipedia']


_JOIN_CODE = '001'


class Barnsworth(object):
    def __init__(self, **kwargs):
        self.irc_nick = kwargs.pop('irc_nick', DEFAULT_IRC_NICK)
        self.irc_server = kwargs.pop('irc_server', DEFAULT_IRC_SERVER)
        self.irc_port = kwargs.pop('irc_port', DEFAULT_IRC_PORT)
        self.irc_channels = [x.strip('#') for x in
                             kwargs.pop('irc_channels', DEFAULT_IRC_CHANNELS)]
        # TODO: validate channel formatting?
        self.irc_client = IRCClient(self.irc_server,
                                    self.irc_nick,
                                    self.irc_port)
        self.irc_client.add_handler(self.join_handler, _JOIN_CODE)
        self.irc_client.add_handler(self.pub_handler, 'PRIVMSG')

        defer_start = kwargs.pop('defer_start', False)
        if not defer_start:
            self._start_irc()

    def join_handler(self, client, msg):
        # TODO: need another handler to register a join failure?
        for channel in self.irc_channels:
            client.send_message(Join(channel))

    def pub_handler(self, client, msg):
        msg_content = ' '.join(msg.params[1:]).decode('utf-8')
        try:
            msg_dict = parse_irc_message(msg_content)
        except Exception as e:
            # log
            return
        json_msg = json.dumps(msg_dict)
        for addr, ws_client in server.clients.items():
            ws_client.ws.send(json_msg)
        return

    def _start_irc(self):
        self.irc_client.start()


class EchoApplication(WebSocketApplication):
    def on_open(self):
        print "Connection opened"

    def on_close(self, reason):
        print reason


def main():
    global server  # todo
    server = WebSocketServer(('', 9000),
                             Resource({'/': EchoApplication}))
    barnsworth = Barnsworth()
    server.serve_forever()


if __name__ == '__main__':
    main()
