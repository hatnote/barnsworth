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

from boltons.strutils import ordinalize
sys.path.insert(0, '../../wikimon')  # or pip install wikimon, maybe
from wikimon.parsers import parse_irc_message

import ransom


import events


DEBUG = False

# TODO: extract/reconstruct upload URL
# TODO: handle nick already in use
# TODO: hashtags

DEFAULT_IRC_NICK = 'barnsworth'
DEFAULT_IRC_SERVER = 'irc.wikimedia.org'
DEFAULT_IRC_PORT = 6667
DEFAULT_IRC_CHANNELS = ['en.wikipedia']


_JOIN_CODE = '001'

_USERINFO_URL_TMPL = u"http://en.wikipedia.org/w/api.php?action=query&meta=globaluserinfo&guiuser=%s&guiprop=editcount|merged&format=json"
_USERDAILY_URL_TMPL = u"http://en.wikipedia.org/w/api.php?action=userdailycontribs&user=%s&daysago=90&format=json"


MILESTONE_EDITS = [1, 5, 10, 20, 50, 100, 200, 300, 500]


EVENT_MAP = {'edit': [],  # events.MilestoneEdit, events.BirthdayEdit],
             'block': [],
             'new_user': [],
             'create': [events.NewUser]}


class ActionContext(object):
    "Supports adding user info and maybe article/content info"
    def __init__(self, action, events=None):
        self.action = action
        self.events = list(events or [])

    @property
    def action_type(self):
        try:
            return self.action['action']
        except:
            return None

    def add_event(self, event):
        self.events.append(event)


# TODO: whats the best way to organize these?
def is_milestone_edit(msg):
    count = msg['total_edits']
    if msg['action'] != 'edit':
        return False
    if count > 0 and (count % 1000 == 0 or count in MILESTONE_EDITS):
        return True
    return False


def is_new_user(msg):
    if msg['page_title'] != 'Special:Log/newusers':
        return False
    if msg['action'] != 'create':
        return False
    if msg['wiki_age'] < 1:
        return False
    return True


def is_new_article(msg):
    if not msg['is_new']:
        return False
    if msg['ns'] != 'Main':
        return False
    return True


def is_new_large(msg):
    if is_new_article(msg) or msg['change_size'] > 2000:
        return True
    return False


def is_welcome(msg):
    if not msg['is_new']:
        return False
    if msg['ns'] != 'User talk':
        return False
    if not 'welcome' in msg['summary'].lower():
        return False
    return True


def is_wiki_birthday(msg):
    if msg['is_wiki_birthday'] and msg['wiki_age'] > 0:
        return True
    return False


def parse_timestamp(timestamp):
    return datetime.datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%SZ')


def parse_timestamp_nopunct(timestamp):
    return datetime.datetime.strptime(timestamp, '%Y%m%d%H%M%S')


class UserInfo(object):
    def __init__(self, username, user_id, reg_date, edit_count, home_wiki,
                 per_wiki_info=None):
        self.username = username
        self.user_id = user_id
        self.reg_date = reg_date
        self.edit_count = edit_count
        self.home_wiki = home_wiki
        self.per_wiki_info = per_wiki_info

    @classmethod
    def from_dict(cls, username, query_resp):
        qr = query_resp
        reg_date = qr.get('registration', None)
        if reg_date:
            reg_date = parse_timestamp(reg_date)
        return cls(username, qr['id'], reg_date, qr['editcount'],
                   qr.get('home'), qr.get('merged'))


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
        self.publish_activity(action_ctx)
        return

    def publish_activity(self, action_ctx):
        action_json = json.dumps(action_ctx.action, sort_keys=True)
        for addr, ws_client in self.ws_server.clients.iteritems():
            ws_client.ws.send(action_json)

        # TODO: store action for activity batch service?
        # TODO: handle augmentation
        event_list = self._detect_events(action_ctx)
        for event in event_list:
            action_ctx.add_event(event)
            event_json = event.to_json()
            for addr, ws_client in self.ws_server.clients.iteritems():
                ws_client.ws.send(event_json)
        return

    def _detect_events(self, action_ctx):
        try:
            event_types = EVENT_MAP[action_ctx.action_type]
        except KeyError:
            return []
        event_list = []
        for event_type in event_types:
            try:
                event_list.append(event_type.from_action_context(action_ctx))
            except events.Uneventful as ue:
                print 'event not applicable', ue
            except Exception as e:
                print 'event exception', e
        return event_list


    def augment_message(self, msg_dict):
        ret = []
        msg_dict['is_wiki_birthday'] = False
        msg_dict['wiki_age'] = 0
        msg_dict['total_edits'] = 0
        username = msg_dict['user']
        if not msg_dict['is_anon']:
            rc = ransom.Client()
            resp = rc.get(_USERDAILY_URL_TMPL % username)
            try:
                udc_dict = json.loads(resp.text)['userdailycontribs']
            except KeyError:
                pass
            user_daily = UserDailyInfo.from_dict(username, udc_dict)
            if user_daily.reg_date:
                today = datetime.date.today()
                user_reg_date = user_daily.reg_date.date()
                wiki_age = round((today - user_reg_date).days / 365.0, 2)
                msg_dict['wiki_age'] = wiki_age
                if today == user_reg_date:
                    msg_dict['is_wiki_birthday'] = True
            total_edits = user_daily.total_edits
            msg_dict['total_edits'] = total_edits
        #if is_welcome(msg_dict):
        #    ret.append(EditEvent('welcome', username))
        #if is_new_large(msg_dict):
        #    ret.append(EditEvent('newlargepage', username, msg_dict['page_title']))
        #if is_wiki_birthday(msg_dict):
        #    ret.append(EditEvent('birthday', username, msg_dict['wiki_age']))
        #if is_milestone_edit(msg_dict):
        #    ret.append(EditEvent('milestone', username, total_edits))
        #if is_new_user(msg_dict):
        #    ret.append(EditEvent('newuser', username))
        return ret

    def _global_user_info_compare(self, msg_dict):
        if not msg_dict['is_anon']:
            username = msg_dict['name']
            rc = ransom.Client()
            resp = rc.get(_USERINFO_URL_TMPL % username)
            ui_dict = json.loads(resp.text)['query']['globaluserinfo']
            if 'missing' in ui_dict:
                return  # TODO: glitch (log)
            user_info = UserInfo.from_dict(username, ui_dict)
            username = msg_dict['user']
            resp2 = rc.get(_USERDAILY_URL_TMPL % username)
            udc_dict = json.loads(resp2.text)['userdailycontribs']
            user_daily = UserDailyInfo.from_dict(username, udc_dict)
            #diff = user_info.edit_count - user_daily.total_edits
            #print user_info.username, user_info.edit_count, '-', user_daily.total_edits, '=', diff
            timediff = user_info.reg_date - user_daily.reg_date
            print user_info.username, '(', user_info.home_wiki, '):', user_info.reg_date, '-', user_daily.reg_date, '=', timediff
        return msg_dict

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
    barnsworth.start()
