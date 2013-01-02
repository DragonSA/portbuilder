"""
Utility classes for internal use of sigev.
"""

import threading

__all__ = ['LocalStack', 'Singleton']

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
