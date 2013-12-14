
import json
import sys
sys.path.insert(0, '../../wikimon')  # or pip install wikimon, maybe


from geventwebsocket import (WebSocketServer,
                             WebSocketApplication,
                             Resource)
from geventirc import Client, message

from wikimon.parsers import parse_irc_message

# TODO: extract/reconstruct upload URL

server = None

irc = Client('irc.wikimedia.org', 'mahmoud', port=6667)


def print_handler(client, msg):
    #print len(msg.encode())
    pass


def pub_handler(client, msg):
    if msg.command != 'PRIVMSG':
        print msg.command
        return
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


def join_handler(client, msg):
    client.send_message(message.Join('#en.wikipedia'))


class EchoApplication(WebSocketApplication):
    def on_open(self):
        print "Connection opened"

    def on_close(self, reason):
        print reason


def main():
    global server  # todo
    irc.start()
    irc.add_handler(print_handler)
    irc.add_handler(join_handler, '001')
    irc.add_handler(pub_handler)
    server = WebSocketServer(('', 9000),
                             Resource({'/': EchoApplication}))

    server.serve_forever()



if __name__ == '__main__':
    main()
