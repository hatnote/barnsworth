# -*- coding: utf-8 -*-

import re
import json


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


class MilestoneEdit(Event):
    @classmethod
    def from_action_context(cls, action_ctx):
        raise NotImplementedError()


class BirthdayEdit(Event):
    pass


class NewArticle(Event):
    pass


class NewLargeArticle(Event):
    pass


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
    pass
