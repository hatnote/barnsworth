
from geventwebsocket import (WebSocketServer,
                             WebSocketApplication,
                             Resource)

from geventirc import Client, message

irc = Client('irc.wikimedia.org', 'mahmoud', port=6667)


def print_handler(client, msg):
    #print len(msg.encode())
    pass


def pub_handler(client, msg):
    import json
    json_msg = json.dumps({'length': len(msg.encode())})
    for addr, ws_client in server.clients.items():
        ws_client.ws.send(json_msg)


def join_handler(client, msg):
    client.send_message(message.Join('#en.wikipedia'))


irc.start()
irc.add_handler(print_handler)
irc.add_handler(join_handler, '001')
irc.add_handler(pub_handler)


class EchoApplication(WebSocketApplication):
    def on_open(self):
        print "Connection opened"

    def on_close(self, reason):
        print reason


server = WebSocketServer(('', 9000),
                         Resource({'/': EchoApplication}))

server.serve_forever()
