"""
Test the sigev.util module.
"""

import threading
import unittest

from sigev import util

class TestLocalStack(unittest.TestCase):
    """Test the LocalStack() class"""

    def test_default(self):
        """Test default value of stack"""
        default = [True]
        stack = util.LocalStack([default])
        def do_test(key):
            stack.get()[0] = key
            self.assertIs(stack.get(), default)

        do_test(False)
        self.assertIs(default[0], False)

        thread = threading.Thread(target=do_test, args=(None,))
        thread.start()
        thread.join()
        self.assertIs(default[0], None)

    def test_multistack(self):
        """Test multiple stacks are independent"""
        stack1 = util.LocalStack()
        stack2 = util.LocalStack()

        stack1.push(True)
        stack2.push(False)
        self.assertIsNot(stack1.get(), stack2.get())


    def test_stack(self):
        """Test stacking"""
        stack = util.LocalStack()
        wait_stack = threading.Lock()
        wait_stack.acquire()
        wait_unstack = threading.Lock()
        wait_unstack.acquire()
        def do_stack(objs):
            for obj in objs:
                stack.push(obj)
                self.assertIs(stack.get(), obj)
            self.assertEqual(len(stack), len(objs))
        def do_unstack(objs):
            self.assertEqual(len(stack), len(objs))
            for obj in reversed(objs):
                self.assertIs(stack.pop(), obj)
        def do_test(objs):
            self.assertEqual(len(stack), 0)
            do_stack(objs)
            wait_stack.release()
            wait_unstack.acquire()
            do_unstack(objs)

        local_objs = [object() for i in range(8)]
        thread_objs = [object() for i in range(4)]
        thread = threading.Thread(target=do_test, args=(thread_objs,))

        do_stack(local_objs)
        thread.start()
        wait_stack.acquire()
        do_unstack(local_objs)
        wait_unstack.release()
        thread.join()


class TestSingleton(unittest.TestCase):
    """Test the Singleton() class"""

    def test_singleton(self):
        log = []
        class AClass(object):
            __metaclass__ = util.Singleton

            def __init__(self):
                log.append('AClass.__init__')

            def method(self):
                log.append('AClass.method')

        inst1 = AClass()
        inst1.method()
        inst2 = AClass()
        inst2.method()

        self.assertIs(inst1, inst2)
        self.assertEqual(inst1.method, inst2.method)
        self.assertEqual(id(inst1), id(inst2))
        self.assertEqual(id(inst1.method), id(inst2.method))
        self.assertEqual(len(log), 3)
        self.assertEqual(log[0], 'AClass.__init__')
        for i in range(1, 3):
            self.assertEqual(log[i], 'AClass.method')


if __name__ == '__main__':
    unittest.main()
