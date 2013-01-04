"""
Test the sigev module.
"""

import unittest
import random

import sigev


class TestDispatcherContext(unittest.TestCase):
    """
    Test dispatcher context manager.
    """

    def test_exp(self):
        """Test exceptions raised during a context"""
        log = []
        def confirm():
            log.append(True)

        exc = None
        try:
            with sigev.dispatcher():
                sigev.post_event(confirm)
                raise RuntimeError()
        except BaseException, e:
            exc = e

        self.assertTrue(isinstance(exc, RuntimeError))
        self.assertEqual(len(log), 0)

    def test_exp_run(self):
        """Test exceptions raised during run"""
        log = []
        def store_and_raise(key):
            log.append(key)
            raise RuntimeError()

        exc = None
        try:
            with sigev.dispatcher():
                sigev.post_event(store_and_raise, args=(1,))
                sigev.post_event(store_and_raise, args=(2,))
                log.append(0)
        except BaseException, e:
            exc = e

        self.assertEqual(len(log), 2)
        self.assertEqual(log[0], 0)
        self.assertEqual(log[1], 1)

    def test_nesting(self):
        """Test nesting of contexts"""
        log = []
        def store(key):
            log.append(key)
        def store_and_nest(key):
            log.append(key)
            with sigev.dispatcher():
                sigev.post_event(store, args=(key + 1,))
            log.append(key + 2)

        with sigev.dispatcher():
            log.append(0)
            sigev.post_event(store, args=(6,))
            sigev.post_event(store_and_nest, args=(7,))

            with sigev.dispatcher():
                log.append(1)
                sigev.post_event(store, args=(2,))
                sigev.post_event(store_and_nest, args=(3,))

        self.assertEqual(len(log), 10)
        for i in range(10):
            self.assertEqual(log[i], i)


class TestEvent(unittest.TestCase):
    """
    Test events and event properties.
    """

    def test_context(self):
        """Test context information of events"""
        log = []
        def inner_context(dispatch, context, parent):
            self.assertIs(dispatch.context, context)
            self.assertIs(context.context, parent)
            self.assertGreater(context.time_dispatched,
                    context.time_created)
            self.assertIs(context.time_duration, None)

            if parent is None:
                self.assertEqual(context.time_created, 0)
            else:
                self.assertGreater(context.time_created,
                        parent.time_dispatched)
                self.assertGreater(context.time_dispatched,
                        parent.time_dispatched + parent.time_duration)
            if len(log) < 7:
                kwargs = {}
                event = sigev.FuncEvent(inner_context, kwargs=kwargs)
                sigev.post_event(event)
                kwargs['dispatch'] = dispatch
                kwargs['context'] = event.context
                kwargs['parent'] = context
            log.append(parent)

        with sigev.dispatcher() as dispatch:
            self.assertIs(dispatch.context, None)

            kwargs = {}
            event = sigev.FuncEvent(inner_context, kwargs=kwargs)
            sigev.post_event(event)
            kwargs['dispatch'] = dispatch
            kwargs['context'] = event.context
            kwargs['parent'] = None

        self.assertEqual(len(log), 8)
        self.assertIs(log[0], None)
        self.assertIs(log[1], event.context)

    def test_context_exc(self):
        """Test the context after an exception"""
        def die():
            raise RuntimeError()

        event = sigev.FuncEvent(die)
        exc = None
        try:
            with sigev.dispatcher() as dispatch:
                sigev.post_event(event)
        except RuntimeError, e:
            exc = e
        self.assertTrue(isinstance(exc, RuntimeError))
        self.assertIs(dispatch.context, event.context)

    def test_AdaptFuncEvent(self):
        """Test AdaptFuncEvent() with classes; posting and dispatching"""
        log = []
        class AClass(object):
            def __init__(self, key, defarg=None):
                log.append(key)

        class Class(object):
            def __call__(self, key, defarg=None):
                log.append(key)

            def amethod(self, key, defarg=None):
                log.append(key)

        def afunc(key, defarg=None):
            log.append(key)

        alambda = lambda key, defarg=None: log.append(key)

        for obj in (AClass, Class(), Class().amethod, afunc, alambda):
            self.assertEqual(len(log), 0)
            with sigev.dispatcher():
                sig = sigev.Signal().connect(obj)
                # Normal calls
                sig.emit(0)
                sig.emit(1, 1)
                sig.emit(2, defarg=1)
                sig.emit(key=3)
                sig.emit(key=4, defarg=1)
                # Extra args
                sig.emit(5, 1, 2)
                # Extra kwargs
                sig.emit(6, 1, extra=2)
                sig.emit(7, defarg=1, extra=2)
                sig.emit(key=8, defarg=1, extra=2)
            self.assertEqual(len(log), 9)
            for i in reversed(range(9)):
                self.assertEqual(log[i], i)
                del log[i]

    def test_AdaptFuncEvent_exc(self):
        """Test AdaptFuncEvent() error messages"""
        def do_typeerror(func, *args, **kwargs):
            try:
                func(*args, **kwargs)
            except TypeError, e:
                msg = e.message
            try:
                sigev.AdaptFuncEvent(func, args, kwargs).dispatch()
            except TypeError, e:
                self.assertEqual(msg, e.message)
                return True
            print func, args, kwargs

        class AClass(object):
            def __init__(self, key, defarg=None):
                pass

        class Class(object):
            def __call__(self, key, defarg=None):
                pass

            def amethod(self, key, defarg=None):
                pass

        def afunc(key, defarg=None):
            pass

        def afunc2(key, _key, defarg=None):
            pass

        alambda = lambda key, defarg=None: key

        for obj in (AClass, Class(), Class().amethod, afunc, alambda):
            self.assertTrue(do_typeerror(obj))
            self.assertTrue(do_typeerror(obj, 1, key=1))
            self.assertTrue(do_typeerror(obj, 1, 2, defarg=2))
        self.assertTrue(do_typeerror(afunc2, 1, 2, key=1))

    def test_Event_subclass(self):
        """Test Event() subclassing; posting and dispatching"""
        container = []
        class Store(sigev.Event):
            def __call__(self, key):
                container.append(key)

            def dispatch(self):
                container.append(True)

        with sigev.dispatcher():
            sigev.post_event(Store())
        self.assertEqual(len(container), 1)
        self.assertEqual(container[-1], True)

        key = random.random()
        with sigev.dispatcher():
            sigev.post_event(Store(), args=(key,))
        self.assertEqual(len(container), 2)
        self.assertEqual(container[-1], key)

        key = random.random()
        with sigev.dispatcher():
            sigev.post_event(Store(), kwargs={'key': key})
        self.assertEqual(len(container), 3)
        self.assertEqual(container[-1], key)

    def test_FuncEvent(self):
        """Test Event(); posting and dispatching"""
        container = []
        def store(key):
            container.append(key)
        def storeNone():
            container.append(None)

        key = random.random()
        with sigev.dispatcher():
            sigev.post_event(sigev.FuncEvent(store, args=(key,)))
        self.assertEqual(len(container), 1)
        self.assertEqual(container[-1], key)

        key = random.random()
        with sigev.dispatcher():
            sigev.post_event(sigev.FuncEvent(store, kwargs={'key': key}))
        self.assertEqual(len(container), 2)
        self.assertEqual(container[-1], key)

        with sigev.dispatcher():
            sigev.post_event(sigev.FuncEvent(storeNone))
        self.assertEqual(len(container), 3)
        self.assertEqual(container[-1], None)

    def test_post_event(self):
        """Test post_event(): posting and dispatching"""
        container = []
        def store(key):
            container.append(key)
        def storeNone():
            container.append(None)

        key = random.random()
        with sigev.dispatcher():
            sigev.post_event(store, args=(key,))
        self.assertEqual(len(container), 1)
        self.assertEqual(container[-1], key)

        key = random.random()
        with sigev.dispatcher():
            sigev.post_event(store, kwargs={'key': key})
        self.assertEqual(len(container), 2)
        self.assertEqual(container[-1], key)

        with sigev.dispatcher():
            sigev.post_event(storeNone)
        self.assertEqual(len(container), 3)
        self.assertEqual(container[-1], None)


class TestSignal(unittest.TestCase):
    """Test the Signal() class"""

    def test_connect_emit(self):
        """Test connecting and emitting of signals"""
        log = []
        def store(key):
            log.append(key)
        def storeOne():
            log.append(1)

        with sigev.dispatcher():
            sig = sigev.Signal()
            sig.connect(storeOne)
            sig.emit()
            sig = sigev.Signal()
            sig.connect(store)
            sig.emit(2)
            sig.emit(key=3)
            log.append(0)
        self.assertEqual(len(log), 4)
        for i in range(4):
            self.assertEqual(log[i], i)

    def test_disconnect_chain(self):
        """Test disconnecting and chaining of signals"""
        log = []
        def store(key):
            log.append(key)

        with sigev.dispatcher():
            sig = sigev.Signal()
            sig.connect(store).emit(0).disconnect(store).emit(1)
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0], 0)


class TestSignalProperty(unittest.TestCase):
    """Test the SignalProperty() class"""

    def test_sigprop(self):
        """Test the SignalProperty() as a property"""
        class AClass(object):
            sig = sigev.SignalProperty()

        for obj in (AClass.sig, AClass().sig):
            self.assertTrue(isinstance(obj, sigev.Signal))


if __name__ == '__main__':
    unittest.main()

