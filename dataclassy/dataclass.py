"""
 Copyright (C) 2020 biqqles.
 This Source Code Form is subject to the terms of the Mozilla Public
 License, v. 2.0. If a copy of the MPL was not distributed with this
 file, You can obtain one at http://mozilla.org/MPL/2.0/.

 This file contains the internal mechanism that makes data classes
 work, as well as functions which operate on them.
"""
from types import FunctionType
from typing import Any, Dict, Generic, TypeVar

DataClass = Any  # type hint for variables that should be data class instances
T = TypeVar('T')


class Internal(Generic[T]):
    """This type hint wrapper represents a field that is internal to the data class and is, for example, not to be
    shown in a repr."""
    @classmethod
    def is_internal(cls, annotation):
        return getattr(annotation, '__origin__', None) is cls or \
               (type(annotation) is str and cls.__name__ in annotation)


class DataClassMeta(type):
    """The metaclass for a data class."""
    DEFAULT_OPTIONS = dict(init=True, repr=True, eq=True, iter=False, frozen=False, kwargs=False, slots=False,
                           hide_internals=True)

    def __new__(mcs, name, bases, dict_, **kwargs):
        # collect annotations, defaults, slots and options from this class' ancestors, in definition order
        all_annotations = {}
        all_defaults = {}
        all_slots = set()
        options = dict(mcs.DEFAULT_OPTIONS)

        dataclass_bases = [vars(b) for b in bases if hasattr(b, '__dataclass__')]
        for b in dataclass_bases + [dict_]:
            all_annotations.update(b.get('__annotations__', {}))
            all_defaults.update(b.get('__defaults__', dict_))
            all_slots.update(b.get('__slots__', set()))
            options.update(b.get('__dataclass__', {}))
        options.update(kwargs)

        # fill out this class' dict and store defaults, annotations and decorator options for future subclasses
        dict_.update(all_defaults)
        dict_['__defaults__'] = all_defaults
        dict_['__annotations__'] = all_annotations
        dict_['__dataclass__'] = options

        # delete what will become stale references so that Python creates new ones
        del dict_['__dict__'], dict_['__weakref__']

        # create/apply generated methods and attributes
        if options['slots']:
            # values with default values must only be present in slots, not dict, otherwise Python will interpret them
            # as read only
            for d in all_annotations.keys() & all_defaults.keys():
                del dict_[d]
            dict_['__slots__'] = all_annotations.keys() - all_slots
        elif '__slots__' in dict_:
            # if the slots option has been removed from an inheriting dataclass we must remove descriptors and __slots__
            for d in all_annotations.keys() - all_defaults.keys() & dict_.keys():
                del dict_[d]
            del dict_['__slots__']
        if options['init']:
            dict_.setdefault('__init__', _generate_init(all_annotations, all_defaults, options['kwargs']))
        if options['repr']:
            dict_.setdefault('__repr__', _generated_repr)
        if options['eq']:
            dict_.setdefault('__eq__', _generated_eq)
        if options['iter']:
            dict_.setdefault('__iter__', _generated_iter)
        if options['frozen']:
            dict_['__delattr__'] = dict_['__setattr__'] = _generated_attr

        return type.__new__(mcs, name, bases, dict_)


def _generate_init(class_annotations: Dict[str, Any], defaults: Dict[str, Any], gen_kwargs: bool) -> FunctionType:
    """Generate and return an __init__ method for a data class."""
    arguments = [str(a) for a in class_annotations if a not in defaults]
    default_arguments = [f'{a}={a}' for a in class_annotations if a in defaults]
    kwargs = ['**kwargs' if gen_kwargs else '']
    assignments = [f'object.__setattr__(self, {k!r}, {k}.copy() if hasattr({k}, "copy") else {k})' for k
                   in class_annotations]

    signature = f'lambda self, {", ".join(arguments + default_arguments + kwargs)}: '
    body = ' or '.join(assignments) or 'None'
    function = eval(signature + body, {}, defaults)  # an empty globals ensures defaults is not polluted with builtins
    function.__annotations__ = class_annotations
    return function


# method implementations which are constant for all data classes
from .functions import fields, as_tuple

_generated_eq = lambda self, other: as_tuple(self) == as_tuple(other)
_generated_iter = lambda self: iter(as_tuple(self))
_generated_repr = lambda self: f'{self.__class__.__name__}(' \
        f'{", ".join(f"{f}={v!r}" for f, v in fields(self, not self.__dataclass__["hide_internals"]).items())})'
_generated_attr = lambda *args: exec('raise AttributeError("Frozen class")')
