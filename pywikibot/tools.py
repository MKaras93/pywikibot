# -*- coding: utf-8  -*-
"""Miscellaneous helper functions (not wiki-dependent)"""
#
# (C) Pywikibot team, 2008
#
# Distributed under the terms of the MIT license.
#
from __future__ import print_function
__version__ = '$Id$'

import sys
import threading
import time
from collections import Mapping

if sys.version_info[0] > 2:
    import queue as Queue
else:
    import Queue


# These variables are functions debug(str) and warning(str)
# which are initially the builtin print function.
# They exist here as the deprecators in this module rely only on them.
# pywikibot updates these function variables in bot.init_handlers()
debug = warning = print


class UnicodeMixin(object):

    """Mixin class to handle defining the proper __str__/__unicode__
       methods in Python 2 or 3.
    """

    if sys.version_info[0] >= 3:
        def __str__(self):
            return self.__unicode__()
    else:
        def __str__(self):
            return self.__unicode__().encode('utf8')


# From http://python3porting.com/preparing.html
class ComparableMixin(object):
    def _compare(self, other, method):
        try:
            return method(self._cmpkey(), other._cmpkey())
        except (AttributeError, TypeError):
            # _cmpkey not implemented, or return different type,
            # so I can't compare with "other".
            return NotImplemented

    def __lt__(self, other):
        return self._compare(other, lambda s, o: s < o)

    def __le__(self, other):
        return self._compare(other, lambda s, o: s <= o)

    def __eq__(self, other):
        return self._compare(other, lambda s, o: s == o)

    def __ge__(self, other):
        return self._compare(other, lambda s, o: s >= o)

    def __gt__(self, other):
        return self._compare(other, lambda s, o: s > o)

    def __ne__(self, other):
        return self._compare(other, lambda s, o: s != o)


class ThreadedGenerator(threading.Thread):

    """Look-ahead generator class.

    Runs a generator in a separate thread and queues the results; can
    be called like a regular generator.

    Subclasses should override self.generator, I{not} self.run

    Important: the generator thread will stop itself if the generator's
    internal queue is exhausted; but, if the calling program does not use
    all the generated values, it must call the generator's stop() method to
    stop the background thread.  Example usage:

    >>> gen = ThreadedGenerator(target=xrange, args=(20,))
    >>> try:
    ...     for data in gen:
    ...         print data,
    ... finally:
    ...     gen.stop()
    0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19

    """

    def __init__(self, group=None, target=None, name="GeneratorThread",
                 args=(), kwargs=None, qsize=65536):
        """Constructor.  Takes same keyword arguments as threading.Thread.

        target must be a generator function (or other callable that returns
        an iterable object).

        @param qsize: The size of the lookahead queue. The larger the qsize,
        the more values will be computed in advance of use (which can eat
        up memory and processor time).
        @type qsize: int

        """
        if kwargs is None:
            kwargs = {}
        if target:
            self.generator = target
        if not hasattr(self, "generator"):
            raise RuntimeError("No generator for ThreadedGenerator to run.")
        self.args, self.kwargs = args, kwargs
        threading.Thread.__init__(self, group=group, name=name)
        self.queue = Queue.Queue(qsize)
        self.finished = threading.Event()

    def __iter__(self):
        """Iterate results from the queue."""
        if not self.isAlive() and not self.finished.isSet():
            self.start()
        # if there is an item in the queue, yield it, otherwise wait
        while not self.finished.isSet():
            try:
                yield self.queue.get(True, 0.25)
            except Queue.Empty:
                pass
            except KeyboardInterrupt:
                self.stop()

    def stop(self):
        """Stop the background thread."""
        self.finished.set()

    def run(self):
        """Run the generator and store the results on the queue."""
        self.__gen = self.generator(*self.args, **self.kwargs)
        for result in self.__gen:
            while True:
                if self.finished.isSet():
                    return
                try:
                    self.queue.put_nowait(result)
                except Queue.Full:
                    time.sleep(0.25)
                    continue
                break
        # wait for queue to be emptied, then kill the thread
        while not self.finished.isSet() and not self.queue.empty():
            time.sleep(0.25)
        self.stop()


def itergroup(iterable, size):
    """Make an iterator that returns lists of (up to) size items from iterable.

    Example:

    >>> i = itergroup(xrange(25), 10)
    >>> print i.next()
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    >>> print i.next()
    [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
    >>> print i.next()
    [20, 21, 22, 23, 24]
    >>> print i.next()
    Traceback (most recent call last):
     ...
    StopIteration

    """
    group = []
    for item in iterable:
        group.append(item)
        if len(group) == size:
            yield group
            group = []
    if group:
        yield group


class ThreadList(list):

    """A simple threadpool class to limit the number of simultaneous threads.

    Any threading.Thread object can be added to the pool using the append()
    method.  If the maximum number of simultaneous threads has not been reached,
    the Thread object will be started immediately; if not, the append() call
    will block until the thread is able to start.

    >>> pool = ThreadList(limit=10)
    >>> def work():
    ...     time.sleep(1)
    ...
    >>> for x in xrange(20):
    ...     pool.append(threading.Thread(target=work))
    ...

    """
    def __init__(self, limit=128, *args):
        self.limit = limit
        list.__init__(self, *args)
        for item in list(self):
            if not isinstance(threading.Thread, item):
                raise TypeError("Cannot add '%s' to ThreadList" % type(item))

    def active_count(self):
        """Return the number of alive threads, and delete all non-alive ones."""
        count = 0
        for item in list(self):
            if item.isAlive():
                count += 1
            else:
                self.remove(item)
        return count

    def append(self, thd):
        if not isinstance(thd, threading.Thread):
            raise TypeError("Cannot append '%s' to ThreadList" % type(thd))
        while self.active_count() >= self.limit:
            time.sleep(2)
        list.append(self, thd)
        thd.start()


class CombinedError(KeyError, IndexError):

    """An error that gets caught by both KeyError and IndexError."""


class EmptyDefault(str, Mapping):

    """
    A default for a not existing siteinfo property.

    It should be chosen if there is no better default known. It acts like an
    empty collections, so it can be iterated through it savely if treated as a
    list, tuple, set or dictionary. It is also basically an empty string.

    Accessing a value via __getitem__ will result in an combined KeyError and
    IndexError.
    """

    def __init__(self):
        """Initialise the default as an empty string."""
        str.__init__(self)

    # http://stackoverflow.com/a/13243870/473890
    def _empty_iter(self):
        """An iterator which does nothing."""
        return
        yield

    def __getitem__(self, key):
        """Raise always a L{CombinedError}."""
        raise CombinedError(key)

    iteritems = itervalues = iterkeys = __iter__ = _empty_iter


EMPTY_DEFAULT = EmptyDefault()


def deprecated(instead=None):
    """Decorator to output a method deprecation warning.

    @param instead: if provided, will be used to specify the replacement
    @type instead: string
    """
    def decorator(method):
        def wrapper(*args, **kwargs):
            funcname = method.__name__
            classname = args[0].__class__.__name__
            if instead:
                warning(u"%s.%s is DEPRECATED, use %s instead."
                        % (classname, funcname, instead))
            else:
                warning(u"%s.%s is DEPRECATED." % (classname, funcname))
            return method(*args, **kwargs)
        wrapper.__name__ = method.__name__
        return wrapper
    return decorator


def deprecate_arg(old_arg, new_arg):
    """Decorator to declare old_arg deprecated and replace it with new_arg."""
    _logger = ""

    def decorator(method):
        def wrapper(*__args, **__kw):
            meth_name = method.__name__
            if old_arg in __kw:
                if new_arg:
                    if new_arg in __kw:
                        warning(
u"%(new_arg)s argument of %(meth_name)s replaces %(old_arg)s; cannot use both."
                            % locals())
                    else:
                        warning(
u"%(old_arg)s argument of %(meth_name)s is deprecated; use %(new_arg)s instead."
                            % locals())
                        __kw[new_arg] = __kw[old_arg]
                else:
                    debug(
u"%(old_arg)s argument of %(meth_name)s is deprecated."
                        % locals(), _logger)
                del __kw[old_arg]
            return method(*__args, **__kw)
        wrapper.__doc__ = method.__doc__
        wrapper.__name__ = method.__name__
        return wrapper
    return decorator


if __name__ == "__main__":
    def _test():
        import doctest
        doctest.testmod()
    _test()
