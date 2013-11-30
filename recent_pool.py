import sys
import json
import time

from collections import deque
from pprint import pformat

from twisted.internet import reactor
from twisted.web.wsgi import WSGIResource
from autobahn.websocket import (WebSocketClientFactory,
                                WebSocketClientProtocol,
                                connectWS)
from twisted.python import log
from twisted.web.server import Site
from twisted.application import internet, service

from clastic import Application
from clastic.render import JSONPRender


DEFAULT_WEBSOCKET = 'ws://wikimon.hatnote.com:9000'
DEFAULT_WINDOW = 120
MAX_ITEM_COUNT = 300

EDIT_POOL = deque()


def get_recent(edit_pool, count=None):
    return list(edit_pool)

def create_app():
    render_jsonp = JSONPRender()
    routes = [('/recent', get_recent, render_jsonp)]
    resources = {'edit_pool': EDIT_POOL}
    return Application(routes, resources)


app = create_app()


class RecordClientProtocol(WebSocketClientProtocol):
    def onMessage(self, msg, binary):
        try:
            msg = json.loads(msg)
        except ValueError:
            return
        cur_time = time.time()
        msg['recv_time'] = cur_time
        EDIT_POOL.append(msg)
        #while (cur_time - EDIT_POOL[0]['recv_time']) > DEFAULT_WINDOW:
        while len(EDIT_POOL) > MAX_ITEM_COUNT:
            EDIT_POOL.popleft()
        log.msg(msg)


def create_parser():
    from argparse import ArgumentParser
    desc = "Save edits from wikimon"
    prs = ArgumentParser(description=desc)
    prs.add_argument('--logfile', help='file to save log')
    prs.add_argument('--websocket', default=DEFAULT_WEBSOCKET,
                     help='wikimon websocket url')
    prs.add_argument('--debug', action='store_true',
                     help='print log in the console')
    return prs


def main():
    parser = create_parser()
    args = parser.parse_args()
    if args.debug or not args.logfile:
        print 'debug logging to console'
        log.addObserver(log.FileLogObserver(sys.stdout).emit)
    if isinstance(args.logfile, basestring):
        log_file = open(args.logfile, 'a')
        print 'logging to ' + str(log_file)
        log.startLogging(log_file)
    ws_factory = WebSocketClientFactory(args.websocket)
    ws_factory.protocol = RecordClientProtocol
    connectWS(ws_factory)

    wsgi_resource = WSGIResource(reactor, reactor.getThreadPool(), app)
    site = Site(wsgi_resource)
    web_service = internet.TCPServer(5000, site)
    application = service.Application('BarnTown')
    web_service.setServiceParent(application)
    reactor.listenTCP(5000, site)
    reactor.run()

if __name__ == '__main__':
    main()
