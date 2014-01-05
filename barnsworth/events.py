# -*- coding: utf-8 -*-


class EventValueError(ValueError):
    pass


class Event(object):
    def to_dict(self):
        return {'event': self.event,
                'name': self.name,
                'value': self.value}

    def to_json(self):
        return json.dumps(self.to_dict())

    @classmethod
    def from_edit_message(cls, msg_dict):
        raise NotImplementedError()


class MilestoneEdit(Event):
    @classmethod
    def from_edit_message(cls, msg_dict):
        pass


class NewUser(
