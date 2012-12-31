"""
Test the sigev module.
"""

import unittest
import random

import sigev

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
                event = sigev.Event(inner_context, kwargs=kwargs)
                sigev.post_event(event)
                kwargs['dispatch'] = dispatch
                kwargs['context'] = event.context
                kwargs['parent'] = context
            log.append(parent)

        with sigev.dispatcher() as dispatch:
            self.assertIs(dispatch.context, None)

            kwargs = {}
            event = sigev.Event(inner_context, kwargs=kwargs)
            sigev.post_event(event)
            kwargs['dispatch'] = dispatch
            kwargs['context'] = event.context
            kwargs['parent'] = None

        self.assertEqual(len(log), 8)
        self.assertIs(log[0], None)
        self.assertIs(log[1], event.context)


    def test_event(self):
        """Test posting and dispatching of events"""
        container = []
        def store(key):
            container.append(key)

        key = random.random()
        with sigev.dispatcher():
            sigev.post_event(sigev.Event(store, args=(key,)))
        self.assertEqual(len(container), 1)
        self.assertEqual(container[-1], key)

        key = random.random()
        with sigev.dispatcher():
            sigev.post_event(store, args=(key,))
        self.assertEqual(len(container), 2)
        self.assertEqual(container[-1], key)


if __name__ == '__main__':
    unittest.main()

