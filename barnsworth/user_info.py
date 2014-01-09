# -*- coding: utf-8 -*-


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
