# -*- coding: utf-8 -*-

import sys
import json
import datetime

from gevent import monkey
monkey.patch_socket()
from geventwebsocket import (WebSocketServer,
                             WebSocketApplication,
                             Resource)
from geventirc import Client as IRCClient
from geventirc.message import Join
from geventirc.handlers import ping_handler

sys.path.insert(0, '../../wikimon')  # or pip install wikimon, maybe
from wikimon.parsers import parse_irc_message

import ransom


import events
from logger import BarnsworthLogger

BLOG = BarnsworthLogger('barnsworth',
                        min_level='info',
                        enable_begin=False)

DEBUG = False

DEFAULT_IRC_NICK = 'barnsworth'
DEFAULT_IRC_SERVER = 'irc.wikimedia.org'
DEFAULT_IRC_PORT = 6667
DEFAULT_IRC_CHANNELS = ['en.wikipedia']


_JOIN_CODE = '001'

_USERINFO_URL_TMPL = u"http://en.wikipedia.org/w/api.php?action=query&meta=globaluserinfo&guiuser=%s&guiprop=editcount|merged&format=json"
_USERDAILY_URL_TMPL = u"http://en.wikipedia.org/w/api.php?action=userdailycontribs&user=%s&daysago=90&format=json"


class UserInfoPool(object):
    def __init__(self, max_size=1024):
        self.cache = {}

    def get_user_info(self, username):
        try:
            return self.cache[username]
        except KeyError:
            pass  # do API call

    def add_action(self, username, action):
        pass

    def register_new_user(self, username):
        pass


EVENT_MAP = {'edit': [events.NewUserWelcome,
                      events.BirthdayEdit,
                      events.NewArticle,
                      events.MilestoneEdit],
             'block': [],
             'create': [events.NewUser]}


class ActionContext(object):
    "Supports adding user info and maybe article/content info"
    def __init__(self, action, events=None):
        self.action = action
        self.events = list(events or [])
        self.user_daily_info = None

    @property
    def action_type(self):
        try:
            return self.action['action']
        except:
            return None

    def add_event(self, event):
        self.events.append(event)


def parse_timestamp(timestamp):
    return datetime.datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')


def parse_timestamp_nopunct(timestamp):
    return datetime.datetime.strptime(timestamp, '%Y%m%d%H%M%S')


class UserDailyInfo(object):
    def __init__(self, username, user_id, reg_date, total_edits,
                 timeframe_edits, start_date=None, end_date=None):
        self.username = username
        self.user_id = user_id
        self.reg_date = reg_date
        self.total_edits = total_edits
        self.timeframe_edits = timeframe_edits
        self.start_date = start_date
        self.end_date = end_date

    @classmethod
    def from_dict(cls, username, query_resp):
        qr = query_resp
        reg_date = qr.get('registration', None)
        if reg_date:
            if reg_date == '0':
                reg_date = None
            else:
                reg_date = parse_timestamp_nopunct(reg_date)
        return cls(username, qr['id'], reg_date,
                   qr['totalEdits'], qr['timeFrameEdits'])

    def __repr__(self):
        cn = self.__class__.__name__
        return ('<%s username=%s total_edits=%s>' %
                (cn, self.username, self.total_edits))


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
                                    self.irc_port,
                                    reconnect=True)
        self.irc_client.add_handler(ping_handler, 'PING')
        self.irc_client.add_handler(self.on_irc_connect, _JOIN_CODE)
        self.irc_client.add_handler(self.on_message, 'PRIVMSG')

        self.ws_server = WebSocketServer(('', 9000),  # TODO: config port
                                         Resource({'/': WebSocketApplication}))
        defer_start = kwargs.pop('defer_start', False)
        if not defer_start:
            self.start()

    def start(self):
        self._start_irc()
        self._start_ws()

    def on_irc_connect(self, client, msg):
        # TODO: need another handler to register a join failure?
        for channel in self.irc_channels:
            with BLOG.critical('joining channel %s' % channel):
                client.send_message(Join(channel))

    def on_message(self, client, msg):
        msg_content = ' '.join(msg.params[1:]).decode('utf-8')
        msg_content.replace(u'\x02', '')  # hmm, TODO
        try:
            action_dict = parse_irc_message(msg_content)
        except Exception as e:
            # log
            return
        action_ctx = ActionContext(action_dict)
        with BLOG.debug('activity publish'):
            self.publish_activity(action_ctx)
        return

    def publish_activity(self, action_ctx):
        action_json = json.dumps(action_ctx.action, sort_keys=True)
        for addr, ws_client in self.ws_server.clients.iteritems():
            ws_client.ws.send(action_json)

        # TODO: store action for activity batch service?
        with BLOG.info('action context augmentation'):
            self._augment_action_ctx(action_ctx)
        with BLOG.debug('event detection') as _r:
            event_list = self._detect_events(action_ctx)
            _r.success('detected %s events' % len(event_list))
        for event in event_list:
            with BLOG.critical('publishing %r' % event.__class__.__name__):
                action_ctx.add_event(event)
                event_json = event.to_json()
                for addr, ws_client in self.ws_server.clients.iteritems():
                    ws_client.ws.send(event_json)
        return

    def _augment_action_ctx(self, action_ctx):
        action = action_ctx.action
        if action['is_anon']:
            # TODO: geo-augmentor
            return  # TODO?
        username = action['user']
        rc = ransom.Client()
        resp = rc.get(_USERDAILY_URL_TMPL % username)
        try:
            udc_dict = json.loads(resp.text)['userdailycontribs']
        except KeyError:
            return  # Log?
        user_daily = UserDailyInfo.from_dict(username, udc_dict)
        action_ctx.user_daily_info = user_daily
        return

    def _detect_events(self, action_ctx):
        try:
            event_types = EVENT_MAP[action_ctx.action_type]
        except KeyError:
            return []
        event_list = []
        for event_type in event_types:
            try:
                event = event_type.from_action_context(action_ctx)
                event_list.append(event)
            except events.Uneventful:
                # probably won't even log this
                # Uneventful is uneventful for a reason
                #print 'event not applicable: ', ue
                pass
            except Exception:
                BLOG.critical('event detection error').exception()
        return event_list

    def _start_irc(self):
        self.irc_client.start()

    def _start_ws(self):
        self.ws_server.serve_forever()


_PDBed = False


def signal_handler(signal, frame):
    global _PDBed
    if _PDBed:
        return
    _PDBed = True

    gstacks = []
    try:
        import gc
        import traceback
        from greenlet import greenlet
        for ob in gc.get_objects():
            if isinstance(ob, greenlet):
                gstacks.append(''.join(traceback.format_stack(ob.gr_frame)))
    except Exception:
        print "couldn't collect (all) greenlet stacks"
    for i, gs in enumerate(gstacks):
        print '==== Stack', i + 1, '===='
        print gs
        print '------------'

    import pdb;pdb.set_trace()
    _PDBed = False


if DEBUG:
    # NOTE: if this is enabled, you may have to use ctrl+z
    # and run "kill %%" to terminate the process
    import signal
    signal.signal(signal.SIGINT, signal_handler)


barnsworth = BW = Barnsworth(defer_start=True)

if __name__ == '__main__':
    try:
        barnsworth.start()
    finally:
        print repr(BLOG.quantile_sink)
