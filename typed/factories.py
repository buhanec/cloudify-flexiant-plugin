# coding=UTF-8

"""Provides two basic builtin alternatives: List and Dict. Bad, bad names."""

from typed import (factory, TypedList, TypedDict)


def List(item_type):
    return factory(TypedList, {'item_type': item_type})


def Dict(key_type, item_type):
    return factory(TypedDict, {'key_type': key_type, 'item_type': item_type})
