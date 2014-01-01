
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


def is_milestone_edit(count):
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
    if not is_new_article(msg):
        return False
    if msg['change_size'] < 2000:
        return False
    return True


def is_welcome(msg):
    if not msg['is_new']:
        return False
    if msg['ns'] != 'User talk':
        return False
    if not 'welcome' in msg['summary'].lower():
        return False
    return True


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
        self.irc_client.add_handler(self.join_handler, _JOIN_CODE)
        self.irc_client.add_handler(self.pub_handler, 'PRIVMSG')

        self.ws_server = WebSocketServer(('', 9000),  # TODO: config port
                                         Resource({'/': WebSocketApplication}))

        defer_start = kwargs.pop('defer_start', False)
        if not defer_start:
            self.start()

    def start(self):
        self._start_irc()
        self._start_ws()

    def join_handler(self, client, msg):
        # TODO: need another handler to register a join failure?
        for channel in self.irc_channels:
            client.send_message(Join(channel))

    def pub_handler(self, client, msg):
        msg_content = ' '.join(msg.params[1:]).decode('utf-8')
        msg_content.replace(u'\x02', '')  # hmm, TODO
        try:
            msg_dict = parse_irc_message(msg_content)
        except Exception as e:
            # log
            return
        #if msg_dict.get('action') =='edit' \
        #    and msg_dict.get('change_size') is None:
        #    #log
        self.augment_message(msg_dict)  # in-place mutation for now, i guess
        json_msg = json.dumps(msg_dict)
        for addr, ws_client in self.ws_server.clients.items():
            ws_client.ws.send(json_msg)
        return

    def augment_message(self, msg_dict):
        if not msg_dict['is_anon']:
            username = msg_dict['user']
            rc = ransom.Client()
            resp = rc.get(_USERDAILY_URL_TMPL % username)
            udc_dict = json.loads(resp.text)['userdailycontribs']
            user_daily = UserDailyInfo.from_dict(username, udc_dict)
            if user_daily.reg_date:
                today = datetime.date.today()
                user_reg_date = user_daily.reg_date.date()
                wiki_age = round((today - user_reg_date).days / 365.0, 2)
                msg_dict['wiki_age'] = wiki_age
                if today == user_reg_date:
                    msg_dict['is_wiki_birthday'] = True
                else:
                    msg_dict['is_wiki_birthday'] = False
            total_edits = user_daily.total_edits
            msg_dict['total_edits'] = total_edits
            if is_welcome(msg_dict):
                print 'welcomed user', username
            if is_new_large(msg_dict):
                print 'new page created by', username, 'page:', msg_dict['page_title']
            if msg_dict.get('is_wiki_birthday') and msg_dict['wiki_age'] > 0:
                print 'wiki birthday for', username, 'age:', msg_dict['wiki_age'] 
            if is_milestone_edit(total_edits):
                msg_dict['milestone_edit'] = ordinalize(total_edits)
                print username, 'milestone edit:', msg_dict['milestone_edit']
            if is_new_user(msg_dict):
                print 'new user:    ', username
        return msg_dict

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
