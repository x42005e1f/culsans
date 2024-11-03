# Some simple queue module tests, plus some failure conditions
# to ensure the Queue locks remain stable.
import threading
import time
import unittest

import culsans

QUEUE_SIZE = 5
SHORT_TIMEOUT = 30.0

def qfull(q):
    return q.maxsize > 0 and q.qsize() == q.maxsize

# from test.support.threading_helper
def join_thread(thread, timeout=None):
    """Join a thread. Raise an AssertionError if the thread is still alive
    after timeout seconds.
    """
    if timeout is None:
        timeout = SHORT_TIMEOUT
    thread.join(timeout)
    if thread.is_alive():
        msg = f"failed to join the thread in {timeout:.1f} seconds"
        raise AssertionError(msg)

# A thread to run a function that unclogs a blocked Queue.
class _TriggerThread(threading.Thread):
    def __init__(self, fn, args):
        self.fn = fn
        self.args = args
        self.startedEvent = threading.Event()
        threading.Thread.__init__(self)

    def run(self):
        # The sleep isn't necessary, but is intended to give the blocking
        # function in the main thread a chance at actually blocking before
        # we unclog it.  But if the sleep is longer than the timeout-based
        # tests wait in their blocking functions, those tests will fail.
        # So we give them much longer timeout values compared to the
        # sleep here (I aimed at 10 seconds for blocking functions --
        # they should never actually wait that long - they should make
        # progress as soon as we call self.fn()).
        time.sleep(0.1)
        self.startedEvent.set()
        self.fn(*self.args)


# Execute a function that blocks, and in a separate thread, a function that
# triggers the release.  Returns the result of the blocking function.  Caution:
# block_func must guarantee to block until trigger_func is called, and
# trigger_func must guarantee to change queue state so that block_func can make
# enough progress to return.  In particular, a block_func that just raises an
# exception regardless of whether trigger_func is called will lead to
# timing-dependent sporadic failures, and one of those went rarely seen but
# undiagnosed for years.  Now block_func must be unexceptional.  If block_func
# is supposed to raise an exception, call do_exceptional_blocking_test()
# instead.

class BlockingTestMixin:

    def do_blocking_test(self, block_func, block_args, trigger_func, trigger_args):
        thread = _TriggerThread(trigger_func, trigger_args)
        thread.start()
        try:
            self.result = block_func(*block_args)
            # If block_func returned before our thread made the call, we failed!
            if not thread.startedEvent.is_set():
                self.fail("blocking function %r appeared not to block" %
                          block_func)
            return self.result
        finally:
            join_thread(thread) # make sure the thread terminates

    # Call this instead if block_func is supposed to raise an exception.
    def do_exceptional_blocking_test(self,block_func, block_args, trigger_func,
                                   trigger_args, expected_exception_class):
        thread = _TriggerThread(trigger_func, trigger_args)
        thread.start()
        try:
            try:
                block_func(*block_args)
            except expected_exception_class:
                raise
            else:
                self.fail("expected exception of kind %r" %
                                 expected_exception_class)
        finally:
            join_thread(thread) # make sure the thread terminates
            if not thread.startedEvent.is_set():
                self.fail("trigger thread ended but event never set")


class BaseQueueTestMixin(BlockingTestMixin):
    def setUp(self):
        self.cum = 0
        self.cumlock = threading.Lock()

    def basic_queue_test(self, q):
        if q.qsize():
            raise RuntimeError("Call this function with an empty queue")
        self.assertTrue(q.empty())
        self.assertFalse(q.full())
        # I guess we better check things actually queue correctly a little :)
        q.put(111)
        q.put(333)
        q.put(222)
        target_order = dict(Queue = [111, 333, 222],
                            LifoQueue = [222, 333, 111],
                            PriorityQueue = [111, 222, 333])
        actual_order = [q.get(), q.get(), q.get()]
        self.assertEqual(actual_order, target_order[q.wrapped.__class__.__name__],
                         "Didn't seem to queue the correct data!")
        for i in range(QUEUE_SIZE-1):
            q.put(i)
            self.assertTrue(q.qsize(), "Queue should not be empty")
        self.assertTrue(not qfull(q), "Queue should not be full")
        last = 2 * QUEUE_SIZE
        full = 3 * 2 * QUEUE_SIZE
        q.put(last)
        self.assertTrue(qfull(q), "Queue should be full")
        self.assertFalse(q.empty())
        self.assertTrue(q.full())
        try:
            q.put(full, block=0)
            self.fail("Didn't appear to block with a full queue")
        except self.queue.SyncQueueFull:
            pass
        try:
            q.put(full, timeout=0.01)
            self.fail("Didn't appear to time-out with a full queue")
        except self.queue.SyncQueueFull:
            pass
        # Test a blocking put
        self.do_blocking_test(q.put, (full,), q.get, ())
        self.do_blocking_test(q.put, (full, True, 10), q.get, ())
        # Empty it
        for i in range(QUEUE_SIZE):
            q.get()
        self.assertTrue(not q.qsize(), "Queue should be empty")
        try:
            q.get(block=0)
            self.fail("Didn't appear to block with an empty queue")
        except self.queue.SyncQueueEmpty:
            pass
        try:
            q.get(timeout=0.01)
            self.fail("Didn't appear to time-out with an empty queue")
        except self.queue.SyncQueueEmpty:
            pass
        # Test a blocking get
        self.do_blocking_test(q.get, (), q.put, ('empty',))
        self.do_blocking_test(q.get, (True, 10), q.put, ('empty',))


    def worker(self, q):
        while True:
            x = q.get()
            if x < 0:
                q.task_done()
                return
            with self.cumlock:
                self.cum += x
            q.task_done()

    def queue_join_test(self, q):
        self.cum = 0
        threads = []
        for i in (0,1):
            thread = threading.Thread(target=self.worker, args=(q,))
            thread.start()
            threads.append(thread)
        for i in range(100):
            q.put(i)
        q.join()
        self.assertEqual(self.cum, sum(range(100)),
                         "q.join() did not block until all tasks were done")
        for i in (0,1):
            q.put(-1)         # instruct the threads to close
        q.join()                # verify that you can join twice
        for thread in threads:
            thread.join()

    def test_queue_task_done(self):
        # Test to make sure a queue task completed successfully.
        q = self.type2test().sync_q
        try:
            q.task_done()
        except ValueError:
            pass
        else:
            self.fail("Did not detect task count going negative")

    def test_queue_join(self):
        # Test that a queue join()s successfully, and before anything else
        # (done twice for insurance).
        q = self.type2test().sync_q
        self.queue_join_test(q)
        self.queue_join_test(q)
        try:
            q.task_done()
        except ValueError:
            pass
        else:
            self.fail("Did not detect task count going negative")

    def test_basic(self):
        # Do it a couple of times on the same queue.
        # Done twice to make sure works with same instance reused.
        q = self.type2test(QUEUE_SIZE).sync_q
        self.basic_queue_test(q)
        self.basic_queue_test(q)

    def test_negative_timeout_raises_exception(self):
        q = self.type2test(QUEUE_SIZE).sync_q
        with self.assertRaises(ValueError):
            q.put(1, timeout=-1)
        with self.assertRaises(ValueError):
            q.get(1, timeout=-1)

    def test_nowait(self):
        q = self.type2test(QUEUE_SIZE).sync_q
        for i in range(QUEUE_SIZE):
            q.put_nowait(1)
        with self.assertRaises(self.queue.SyncQueueFull):
            q.put_nowait(1)

        for i in range(QUEUE_SIZE):
            q.get_nowait()
        with self.assertRaises(self.queue.SyncQueueEmpty):
            q.get_nowait()

    def test_shrinking_queue(self):
        # issue 10110
        q = self.type2test(3).sync_q
        q.put(1)
        q.put(2)
        q.put(3)
        with self.assertRaises(self.queue.SyncQueueFull):
            q.put_nowait(4)
        self.assertEqual(q.qsize(), 3)
        q.maxsize = 2                       # shrink the queue
        with self.assertRaises(self.queue.SyncQueueFull):
            q.put_nowait(4)

    def test_shutdown_empty(self):
        q = self.type2test().sync_q
        q.shutdown()
        with self.assertRaises(self.queue.SyncQueueShutDown):
            q.put("data")
        with self.assertRaises(self.queue.SyncQueueShutDown):
            q.get()

    def test_shutdown_nonempty(self):
        q = self.type2test().sync_q
        q.put("data")
        q.shutdown()
        q.get()
        with self.assertRaises(self.queue.SyncQueueShutDown):
            q.get()

    def test_shutdown_immediate(self):
        q = self.type2test().sync_q
        q.put("data")
        q.shutdown(immediate=True)
        with self.assertRaises(self.queue.SyncQueueShutDown):
            q.get()

    def test_shutdown_allowed_transitions(self):
        # allowed transitions would be from alive via shutdown to immediate
        q = self.type2test().sync_q
        self.assertFalse(q.is_shutdown)

        q.shutdown()
        self.assertTrue(q.is_shutdown)

        q.shutdown(immediate=True)
        self.assertTrue(q.is_shutdown)

        q.shutdown(immediate=False)

    def _shutdown_all_methods_in_one_thread(self, immediate):
        q = self.type2test(2).sync_q
        q.put("L")
        q.put_nowait("O")
        q.shutdown(immediate)

        with self.assertRaises(self.queue.SyncQueueShutDown):
            q.put("E")
        with self.assertRaises(self.queue.SyncQueueShutDown):
            q.put_nowait("W")
        if immediate:
            with self.assertRaises(self.queue.SyncQueueShutDown):
                q.get()
            with self.assertRaises(self.queue.SyncQueueShutDown):
                q.get_nowait()
            with self.assertRaises(ValueError):
                q.task_done()
            q.join()
        else:
            self.assertIn(q.get(), "LO")
            q.task_done()
            self.assertIn(q.get(), "LO")
            q.task_done()
            q.join()
            # on shutdown(immediate=False)
            # when queue is empty, should raise ShutDown Exception
            with self.assertRaises(self.queue.SyncQueueShutDown):
                q.get() # p.get(True)
            with self.assertRaises(self.queue.SyncQueueShutDown):
                q.get_nowait() # p.get(False)
            with self.assertRaises(self.queue.SyncQueueShutDown):
                q.get(True, 1.0)

    def test_shutdown_all_methods_in_one_thread(self):
        return self._shutdown_all_methods_in_one_thread(False)

    def test_shutdown_immediate_all_methods_in_one_thread(self):
        return self._shutdown_all_methods_in_one_thread(True)

    def _write_msg_thread(self, q, n, results,
                            i_when_exec_shutdown, event_shutdown,
                            barrier_start):
        # All `write_msg_threads`
        # put several items into the queue.
        for i in range(0, i_when_exec_shutdown//2):
            q.put((i, 'LOYD'))
        # Wait for the barrier to be complete.
        barrier_start.wait()

        for i in range(i_when_exec_shutdown//2, n):
            try:
                q.put((i, "YDLO"))
            except self.queue.SyncQueueShutDown:
                results.append(False)
                break

            # Trigger queue shutdown.
            if i == i_when_exec_shutdown:
                # Only one thread should call shutdown().
                if not event_shutdown.is_set():
                    event_shutdown.set()
                    results.append(True)

    def _read_msg_thread(self, q, results, barrier_start):
        # Get at least one item.
        q.get(True)
        q.task_done()
        # Wait for the barrier to be complete.
        barrier_start.wait()
        while True:
            try:
                q.get(False)
                q.task_done()
            except self.queue.SyncQueueShutDown:
                results.append(True)
                break
            except self.queue.SyncQueueEmpty:
                pass

    def _shutdown_thread(self, q, results, event_end, immediate):
        event_end.wait()
        q.shutdown(immediate)
        results.append(q.qsize() == 0)

    def _join_thread(self, q, barrier_start):
        # Wait for the barrier to be complete.
        barrier_start.wait()
        q.join()

    def _shutdown_all_methods_in_many_threads(self, immediate):
        # Run a 'multi-producers/consumers queue' use case,
        # with enough items into the queue.
        # When shutdown, all running threads will be joined.
        q = self.type2test().sync_q
        ps = []
        res_puts = []
        res_gets = []
        res_shutdown = []
        write_threads = 4
        read_threads = 6
        join_threads = 2
        nb_msgs = 1024*64
        nb_msgs_w = nb_msgs // write_threads
        when_exec_shutdown = nb_msgs_w // 2
        # Use of a Barrier to ensure that
        # - all write threads put all their items into the queue,
        # - all read thread get at least one item from the queue,
        #   and keep on running until shutdown.
        # The join thread is started only when shutdown is immediate.
        nparties = write_threads + read_threads
        if immediate:
            nparties += join_threads
        barrier_start = threading.Barrier(nparties)
        ev_exec_shutdown = threading.Event()
        lprocs = [
            (self._write_msg_thread, write_threads, (q, nb_msgs_w, res_puts,
                                            when_exec_shutdown, ev_exec_shutdown,
                                            barrier_start)),
            (self._read_msg_thread, read_threads, (q, res_gets, barrier_start)),
            (self._shutdown_thread, 1, (q, res_shutdown, ev_exec_shutdown, immediate)),
            ]
        if immediate:
            lprocs.append((self._join_thread, join_threads, (q, barrier_start)))
        # start all threads.
        for func, n, args in lprocs:
            for i in range(n):
                ps.append(threading.Thread(target=func, args=args))
                ps[-1].start()
        for thread in ps:
            thread.join()

        self.assertTrue(True in res_puts)
        self.assertEqual(res_gets.count(True), read_threads)
        if immediate:
            self.assertListEqual(res_shutdown, [True])
            self.assertTrue(q.empty())

    def test_shutdown_all_methods_in_many_threads(self):
        return self._shutdown_all_methods_in_many_threads(False)

    def test_shutdown_immediate_all_methods_in_many_threads(self):
        return self._shutdown_all_methods_in_many_threads(True)

    def _get(self, q, go, results, shutdown=False):
        go.wait()
        try:
            msg = q.get()
            results.append(not shutdown)
            return not shutdown
        except self.queue.SyncQueueShutDown:
            results.append(shutdown)
            return shutdown

    def _get_shutdown(self, q, go, results):
        return self._get(q, go, results, True)

    def _get_task_done(self, q, go, results):
        go.wait()
        try:
            msg = q.get()
            q.task_done()
            results.append(True)
            return msg
        except self.queue.SyncQueueShutDown:
            results.append(False)
            return False

    def _put(self, q, msg, go, results, shutdown=False):
        go.wait()
        try:
            q.put(msg)
            results.append(not shutdown)
            return not shutdown
        except self.queue.SyncQueueShutDown:
            results.append(shutdown)
            return shutdown

    def _put_shutdown(self, q, msg, go, results):
        return self._put(q, msg, go, results, True)

    def _join(self, q, results, shutdown=False):
        try:
            q.join()
            results.append(not shutdown)
            return not shutdown
        except self.queue.SyncQueueShutDown:
            results.append(shutdown)
            return shutdown

    def _join_shutdown(self, q, results):
        return self._join(q, results, True)

    def _shutdown_get(self, immediate):
        q = self.type2test(2).sync_q
        results = []
        go = threading.Event()
        q.put("Y")
        q.put("D")
        # queue full

        if immediate:
            thrds = (
                (self._get_shutdown, (q, go, results)),
                (self._get_shutdown, (q, go, results)),
            )
        else:
            thrds = (
                # on shutdown(immediate=False)
                # one of these threads should raise Shutdown
                (self._get, (q, go, results)),
                (self._get, (q, go, results)),
                (self._get, (q, go, results)),
            )
        threads = []
        for func, params in thrds:
            threads.append(threading.Thread(target=func, args=params))
            threads[-1].start()
        q.shutdown(immediate)
        go.set()
        for t in threads:
            t.join()
        if immediate:
            self.assertListEqual(results, [True, True])
        else:
            self.assertListEqual(sorted(results), [False] + [True]*(len(thrds)-1))

    def test_shutdown_get(self):
        return self._shutdown_get(False)

    def test_shutdown_immediate_get(self):
        return self._shutdown_get(True)

    def _shutdown_put(self, immediate):
        q = self.type2test(2).sync_q
        results = []
        go = threading.Event()
        q.put("Y")
        q.put("D")
        # queue fulled

        thrds = (
            (self._put_shutdown, (q, "E", go, results)),
            (self._put_shutdown, (q, "W", go, results)),
        )
        threads = []
        for func, params in thrds:
            threads.append(threading.Thread(target=func, args=params))
            threads[-1].start()
        q.shutdown()
        go.set()
        for t in threads:
            t.join()

        self.assertEqual(results, [True]*len(thrds))

    def test_shutdown_put(self):
        return self._shutdown_put(False)

    def test_shutdown_immediate_put(self):
        return self._shutdown_put(True)

    def _shutdown_join(self, immediate):
        q = self.type2test().sync_q
        results = []
        q.put("Y")
        go = threading.Event()
        nb = q.qsize()

        thrds = (
            (self._join, (q, results)),
            (self._join, (q, results)),
        )
        threads = []
        for func, params in thrds:
            threads.append(threading.Thread(target=func, args=params))
            threads[-1].start()
        if not immediate:
            res = []
            for i in range(nb):
                threads.append(threading.Thread(target=self._get_task_done, args=(q, go, res)))
                threads[-1].start()
        q.shutdown(immediate)
        go.set()
        for t in threads:
            t.join()

        self.assertEqual(results, [True]*len(thrds))

    def test_shutdown_immediate_join(self):
        return self._shutdown_join(True)

    def test_shutdown_join(self):
        return self._shutdown_join(False)

    def _shutdown_put_join(self, immediate):
        q = self.type2test(2).sync_q
        results = []
        go = threading.Event()
        q.put("Y")
        # queue not fulled

        thrds = (
            (self._put_shutdown, (q, "E", go, results)),
            (self._join, (q, results)),
        )
        threads = []
        for func, params in thrds:
            threads.append(threading.Thread(target=func, args=params))
            threads[-1].start()
        self.assertEqual(q.unfinished_tasks, 1)

        q.shutdown(immediate)
        go.set()

        if immediate:
            with self.assertRaises(self.queue.SyncQueueShutDown):
                q.get_nowait()
        else:
            result = q.get()
            self.assertEqual(result, "Y")
            q.task_done()

        for t in threads:
            t.join()

        self.assertEqual(results, [True]*len(thrds))

    def test_shutdown_immediate_put_join(self):
        return self._shutdown_put_join(True)

    def test_shutdown_put_join(self):
        return self._shutdown_put_join(False)

    def test_shutdown_get_task_done_join(self):
        q = self.type2test(2).sync_q
        results = []
        go = threading.Event()
        q.put("Y")
        q.put("D")
        self.assertEqual(q.unfinished_tasks, q.qsize())

        thrds = (
            (self._get_task_done, (q, go, results)),
            (self._get_task_done, (q, go, results)),
            (self._join, (q, results)),
            (self._join, (q, results)),
        )
        threads = []
        for func, params in thrds:
            threads.append(threading.Thread(target=func, args=params))
            threads[-1].start()
        go.set()
        q.shutdown(False)
        for t in threads:
            t.join()

        self.assertEqual(results, [True]*len(thrds))

    def test_shutdown_pending_get(self):
        def get():
            try:
                results.append(q.get())
            except Exception as e:
                results.append(e)

        q = self.type2test().sync_q
        results = []
        get_thread = threading.Thread(target=get)
        get_thread.start()
        q.shutdown(immediate=False)
        get_thread.join(timeout=10.0)
        self.assertFalse(get_thread.is_alive())
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], self.queue.SyncQueueShutDown)


class QueueTest(BaseQueueTestMixin):

    def setUp(self):
        self.type2test = self.queue.Queue
        super().setUp()

class PyQueueTest(QueueTest, unittest.TestCase):
    queue = culsans


class LifoQueueTest(BaseQueueTestMixin):

    def setUp(self):
        self.type2test = self.queue.LifoQueue
        super().setUp()


class PyLifoQueueTest(LifoQueueTest, unittest.TestCase):
    queue = culsans


class PriorityQueueTest(BaseQueueTestMixin):

    def setUp(self):
        self.type2test = self.queue.PriorityQueue
        super().setUp()


class PyPriorityQueueTest(PriorityQueueTest, unittest.TestCase):
    queue = culsans


# A Queue subclass that can provoke failure at a moment's notice :)
class FailingQueueException(Exception): pass


class FailingQueueTest(BlockingTestMixin):

    def setUp(self):

        Queue = self.queue.Queue

        class FailingQueue(Queue):
            def __init__(self, *args):
                self.fail_next_put = False
                self.fail_next_get = False
                Queue.__init__(self, *args)
            def _put(self, item):
                if self.fail_next_put:
                    self.fail_next_put = False
                    raise FailingQueueException("You Lose")
                return Queue._put(self, item)
            def _get(self):
                if self.fail_next_get:
                    self.fail_next_get = False
                    raise FailingQueueException("You Lose")
                return Queue._get(self)

        self.FailingQueue = FailingQueue

        super().setUp()

    def failing_queue_test(self, q):
        if q.qsize():
            raise RuntimeError("Call this function with an empty queue")
        for i in range(QUEUE_SIZE-1):
            q.put(i)
        # Test a failing non-blocking put.
        q.wrapped.fail_next_put = True
        try:
            q.put("oops", block=0)
            self.fail("The queue didn't fail when it should have")
        except FailingQueueException:
            pass
        q.wrapped.fail_next_put = True
        try:
            q.put("oops", timeout=0.1)
            self.fail("The queue didn't fail when it should have")
        except FailingQueueException:
            pass
        q.put("last")
        self.assertTrue(qfull(q), "Queue should be full")
        # Test a failing blocking put
        q.wrapped.fail_next_put = True
        try:
            self.do_blocking_test(q.put, ("full",), q.get, ())
            self.fail("The queue didn't fail when it should have")
        except FailingQueueException:
            pass
        # Check the Queue isn't damaged.
        # put failed, but get succeeded - re-add
        q.put("last")
        # Test a failing timeout put
        q.wrapped.fail_next_put = True
        try:
            self.do_exceptional_blocking_test(q.put, ("full", True, 10), q.get, (),
                                              FailingQueueException)
            self.fail("The queue didn't fail when it should have")
        except FailingQueueException:
            pass
        # Check the Queue isn't damaged.
        # put failed, but get succeeded - re-add
        q.put("last")
        self.assertTrue(qfull(q), "Queue should be full")
        q.get()
        self.assertTrue(not qfull(q), "Queue should not be full")
        q.put("last")
        self.assertTrue(qfull(q), "Queue should be full")
        # Test a blocking put
        self.do_blocking_test(q.put, ("full",), q.get, ())
        # Empty it
        for i in range(QUEUE_SIZE):
            q.get()
        self.assertTrue(not q.qsize(), "Queue should be empty")
        q.put("first")
        q.wrapped.fail_next_get = True
        try:
            q.get()
            self.fail("The queue didn't fail when it should have")
        except FailingQueueException:
            pass
        self.assertTrue(q.qsize(), "Queue should not be empty")
        q.wrapped.fail_next_get = True
        try:
            q.get(timeout=0.1)
            self.fail("The queue didn't fail when it should have")
        except FailingQueueException:
            pass
        self.assertTrue(q.qsize(), "Queue should not be empty")
        q.get()
        self.assertTrue(not q.qsize(), "Queue should be empty")
        q.wrapped.fail_next_get = True
        try:
            self.do_exceptional_blocking_test(q.get, (), q.put, ('empty',),
                                              FailingQueueException)
            self.fail("The queue didn't fail when it should have")
        except FailingQueueException:
            pass
        # put succeeded, but get failed.
        self.assertTrue(q.qsize(), "Queue should not be empty")
        q.get()
        self.assertTrue(not q.qsize(), "Queue should be empty")

    def test_failing_queue(self):

        # Test to make sure a queue is functioning correctly.
        # Done twice to the same instance.
        q = self.FailingQueue(QUEUE_SIZE).sync_q
        self.failing_queue_test(q)
        self.failing_queue_test(q)



class PyFailingQueueTest(FailingQueueTest, unittest.TestCase):
    queue = culsans


if __name__ == "__main__":
    unittest.main()
