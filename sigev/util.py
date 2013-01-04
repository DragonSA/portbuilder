"""
Utility classes for internal use of sigev.
"""

import threading
import weakref

__all__ = ['LocalStack', 'Singleton']


class FactoryProperty(object):
    """Create a property based on a factory."""

    def __init__(self, factory):
        self.factory = factory
        self.objs = weakref.WeakKeyDictionary()
        self.clsobj = None

    def __delete__(self, _instance):
        raise AttributeError('factory property cannot be deleted')

    def __get__(self, instance, _owner):
        if instance is None:
            if self.clsobj is None:
                self.clsobj = self.factory()
            return self.clsobj
        else:
            if instance not in self.objs:
                self.objs[instance] = self.factory()
            return self.objs[instance]

    def __set__(self, _instance, _value):
        raise AttributeError('factory property cannot be overwritten')


class LocalStack(threading.local):
    """Thread local stack"""

    def __init__(self, default=None):
        super(LocalStack, self).__init__()
        self._stack = [] if default is None else default

    def __len__(self):
        return len(self._stack)

    def push(self, item):
        """Push item to the top of the stack"""
        self._stack.append(item)

    def get(self):
        """Return top item of the stack"""
        return self._stack[-1]

    def pop(self):
        """Remove top item of the stack"""
        return self._stack.pop()


class Singleton(type):
    def __init__(cls, name, bases, namespace):
        super(Singleton, cls).__init__(name, bases, namespace)
        cls._instance = None

    def __call__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instance
