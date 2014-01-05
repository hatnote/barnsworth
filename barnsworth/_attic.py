# only used to demonstrate issues with APIs
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


class _Barnsworth(object):
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
