# -*- coding: utf-8 -*-

import re
import json
import datetime

_camel2under_re = re.compile('((?<=[a-z0-9])[A-Z]|(?!^)[A-Z](?=[a-z]))')


def camel2under(camel_string):
    """
    Converts a camelcased string to underscores. Useful for
    turning a class name into a function name.

    >>> camel2under('BasicParseTest')
    'basic_parse_test'
    """
    return _camel2under_re.sub(r'_\1', camel_string).lower()


class Uneventful(ValueError):
    pass


class Event(object):
    @property
    def event_type_name(self):
        return camel2under(self.__class__.__name__)

    def to_dict(self):
        # a bit inefficient, but effective
        ret = {}
        for k, v in self.__dict__.items():
            try:
                json.dumps(v)
            except:
                continue
            else:
                ret[k] = v
        ret['action'] = 'event'
        ret['event_type'] = self.event_type_name
        return ret

    def to_json(self):
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_action_context(cls, action_ctx):
        raise NotImplementedError()

    def __repr__(self):
        cn = self.__class__.__name__
        return '<%s %r>' % (cn, self.__dict__)


MILESTONE_EDITS = [1, 5, 10, 20, 50, 100, 200, 300, 500]


class MilestoneEdit(Event):
    def __init__(self, username, edit_count):
        self.username = username
        self.edit_count = edit_count

    @classmethod
    def from_action_context(cls, action_ctx):
        udi = action_ctx.user_daily_info
        if not udi:
            raise Uneventful('no user or no user daily info')
        count = udi.total_edits
        if count > 0 and (count % 1000 == 0 or count in MILESTONE_EDITS):
            return cls(udi.username, count)
        raise Uneventful('not a milestone edit: %s, %s edits' %
                         (udi.username, count))


class BirthdayEdit(Event):
    def __init__(self, username, age):
        self.username = username
        self.age = age

    @classmethod
    def from_action_context(cls, action_ctx):
        udi = action_ctx.user_daily_info
        if not udi or not udi.reg_date:
            raise Uneventful('no user or no user daily info')
        today = datetime.date.today()
        urd = udi.reg_date.date()
        if today == urd:
            raise Uneventful('not a user birthday: brand new user')
        wiki_age = round((today - urd).days / 365.0, 2)
        action_ctx.user_wiki_age = wiki_age  # cache?

        is_wiki_birthday = today.day == urd.day and today.month == urd.month
        if is_wiki_birthday:
            return cls(udi.username, wiki_age)
        raise Uneventful('not a user birthday: %s, %s years' %
                         (udi.username, wiki_age))


class NewArticle(Event):
    def __init__(self, page_title):
        self.page_title = page_title

    @classmethod
    def from_action_context(cls, action_ctx):
        action = action_ctx.action
        if action['is_new'] and action['ns'] == 'Main':
            return cls(action['page_title'])
        raise Uneventful('not a new article: %s' % action['url'])


class NewLargeArticle(Event):
    def __init__(self, page_title, size):
        self.page_title = page_title
        self.size = size

    @classmethod
    def from_action_context(cls, action_ctx):
        action = action_ctx.action
        if action['is_new'] and action['ns'] == 'Main':
            change_size = action['change_size']
            if change_size > 2000:
                return cls(action['page_title'], change_size)
        raise Uneventful('not a big new article: %s' % action['url'])


class NewUser(Event):
    def __init__(self, new_username):
        self.username = new_username
        # TODO: created by?

    @classmethod
    def from_action_context(cls, action_ctx):
        action = action_ctx.action
        page_title = action['page_title']
        if page_title == 'Special:Log/newusers':
            return cls(action['user'])
        raise Uneventful('unexpected page_title %r' % page_title)


class NewUserWelcome(Event):
    def __init__(self, welcomer, recipient):
        self.welcomer = welcomer
        self.recipient = recipient

    @classmethod
    def from_action_context(cls, action_ctx):
        action = action_ctx.action
        namespace, summary = action['ns'], action['summary']
        if namespace == 'User talk' and 'username' in action:
            if summary and 'welcom' in summary.lower():
                welcomer = action['username']
                recipient = action['page_title'].partition('/')[0]
                return cls(welcomer, recipient)
        raise Uneventful('not a welcome: %s' % action['url'])
