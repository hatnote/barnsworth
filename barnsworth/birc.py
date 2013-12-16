
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

sys.path.insert(0, '../../wikimon')  # or pip install wikimon, maybe
from wikimon.parsers import parse_irc_message

import ransom

# TODO: extract/reconstruct upload URL
# TODO: gevent websockets spinning too hard when there are no clients?
# TODO: handle nick already in use
# TODO: hashtags

DEFAULT_IRC_NICK = 'barnsworth'
DEFAULT_IRC_SERVER = 'irc.wikimedia.org'
DEFAULT_IRC_PORT = 6667
DEFAULT_IRC_CHANNELS = ['en.wikipedia']


_JOIN_CODE = '001'

_USERINFO_URL_TMPL = u"http://en.wikipedia.org/w/api.php?action=query&meta=globaluserinfo&guiuser=%s&guiprop=editcount|merged&format=json"
_USERDAILY_URL_TMPL = u"http://en.wikipedia.org/w/api.php?action=userdailycontribs&user=%s&daysago=90&format=json"


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
                                    self.irc_port)
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
        rc = ransom.Client()
        if not msg_dict['is_anon']:
            username = msg_dict['user']
            resp = rc.get(_USERINFO_URL_TMPL % username)
            ui_dict = json.loads(resp.text)['query']['globaluserinfo']
            if 'missing' in ui_dict:
                pass  # TODO: glitch (log)
            else:
                user_info = UserInfo.from_dict(username, ui_dict)
                try:
                    if not TMP_DEBUG_REG_MAP[username] == user_info.reg_date:
                        import pdb;pdb.set_trace()
                except KeyError:
                    TMP_DEBUG_REG_MAP[username] = user_info.reg_date
                resp2 = rc.get(_USERDAILY_URL_TMPL % username)
                udc_dict = json.loads(resp2.text)['userdailycontribs']
                user_daily = UserDailyInfo.from_dict(username, udc_dict)
                #diff = user_info.edit_count - user_daily.total_edits
                #print user_info.username, user_info.edit_count, '-', user_daily.total_edits, '=', diff
                timediff = user_info.reg_date - user_daily.reg_date
                print user_info.username, '(', user_info.home_wiki, '):', user_info.reg_date, '-', user_daily.reg_date, '=', timediff
        json_msg = json.dumps(msg_dict)
        for addr, ws_client in self.ws_server.clients.items():
            ws_client.ws.send(json_msg)
        return

    def _start_irc(self):
        self.irc_client.start()

    def _start_ws(self):
        self.ws_server.serve_forever()


TMP_DEBUG_REG_MAP = {}

def main():
    barnsworth = Barnsworth()
    barnsworth.start()

if __name__ == '__main__':
    main()
