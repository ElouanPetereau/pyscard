"""Smart card insertion/removal monitoring classes.

CardObserver is a base class for objects that are to be notified
upon smart card insertion/removal.

CardMonitor is a singleton object notifying registered CardObservers
upon reader insertion/removal.

__author__ = "http://www.gemalto.com"

Copyright 2001-2012 gemalto
Author: Jean-Daniel Aussel, mailto:jean-daniel.aussel@gemalto.com

This file is part of pyscard.

pyscard is free software; you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation; either version 2.1 of the License, or
(at your option) any later version.

pyscard is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with pyscard; if not, write to the Free Software
Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
"""

from __future__ import print_function

import traceback
from threading import Thread, Event
from time import sleep

from smartcard.CardRequest import CardRequest
from smartcard.Observer import Observable
from smartcard.Observer import Observer
from smartcard.Synchronization import *


# CardObserver interface
class CardObserver(Observer):
    """
    CardObserver is a base abstract class for objects that are to be notified
    upon smart card insertion / removal.
    """

    def __init__(self):
        pass

    def update(self, observable, handlers):
        """Called upon smart card insertion / removal.

        @param observable:
        @param handlers:
          - addedcards: list of inserted smart cards causing notification
          - removedcards: list of removed smart cards causing notification
        """
        pass


class CardMonitor(Observable):
    """Class that monitors smart card insertion / removals.
    and notify observers

    note: a card monitoring thread will be running
    as long as the card monitor has observers, or CardMonitor.stop()
    is called. Do not forget to delete all your observers by
    calling deleteObserver, or your program will run forever...

    It implements the shared state design pattern, where objects
    of the same type all share the same state, in our case essentially
    the CardMonitoring Thread.
    """

    __shared_state = {}

    def __init__(self, startOnDemand=True, period=1, timeout=0.1):
        self.__dict__ = self.__shared_state
        Observable.__init__(self)
        self.startOnDemand = startOnDemand
        self.period = period
        if self.startOnDemand:
            self.rmthread = None
        else:
            self.rmthread = CardMonitoringThread(self, self.period, self.timeout)
            self.rmthread.start()
        self.timeout = timeout

    def addObserver(self, observer):
        """Add an observer."""
        Observable.addObserver(self, observer)

        # If self.startOnDemand is True, the card monitoring
        # thread only runs when there are observers.
        if self.startOnDemand:
            if 0 < self.countObservers():
                if not self.rmthread:
                    self.rmthread = CardMonitoringThread(self, self.period, self.timeout)

                    # start card monitoring thread in another thread to
                    # avoid a deadlock; addObserver and notifyObservers called
                    # in the CardMonitoringThread run() method are
                    # synchronized
                    try:
                        # Python 3.x
                        import _thread
                        _thread.start_new_thread(self.rmthread.start, ())
                    except:
                        # Python 2.x
                        import thread
                        thread.start_new_thread(self.rmthread.start, ())
        else:
            observer.update(self, (self.rmthread.cards, []))

    def deleteObserver(self, observer):
        """Remove an observer."""
        Observable.deleteObserver(self, observer)
        # If self.startOnDemand is True, the card monitoring
        # thread is stopped when there are no more observers.
        if self.startOnDemand:
            if 0 == self.countObservers():
                self.rmthread.stop()
                del self.rmthread
                self.rmthread = None


synchronize(CardMonitor,
            "addObserver deleteObserver deleteObservers " +
            "setChanged clearChanged hasChanged " +
            "countObservers")


class CardMonitoringThread(Thread):
    """Card insertion thread.
    This thread waits for card insertion.
    """

    __shared_state = {}

    def __init__(self, observable, period, timeout):
        self.__dict__ = self.__shared_state
        Thread.__init__(self)
        self.observable = observable
        self.stopEvent = Event()
        self.stopEvent.clear()
        self.cards = []
        self.setDaemon(True)
        self.setName('smartcard.CardMonitoringThread')
        self.period = period
        self.timeout = timeout
        self.cardrequest = None

    def run(self):
        """Runs until stopEvent is notified, and notify
        observers of all card insertion/removal.
        """
        self.cardrequest = CardRequest(self.timeout)
        while not self.stopEvent.isSet():
            try:
                # no need to monitor if no observers
                if 0 < self.observable.countObservers():
                    currentcards = self.cardrequest.waitforcardevent()

                    addedcards = []
                    for card in currentcards:
                        if not self.cards.__contains__(card):
                            addedcards.append(card)

                    removedcards = []
                    for card in self.cards:
                        if not currentcards.__contains__(card):
                            removedcards.append(card)

                    if addedcards != [] or removedcards != []:
                        self.cards = currentcards
                        self.observable.setChanged()
                        self.observable.notifyObservers(
                            (addedcards, removedcards))

                # wait every second on stopEvent
                self.stopEvent.wait(self.period)

            # when CardMonitoringThread.__del__() is invoked in
            # response to shutdown, e.g., when execution of the
            # program is done, other globals referenced by the
            # __del__() method may already have been deleted.
            # this causes ReaderMonitoringThread.run() to except
            # with a TypeError or AttributeError
            except TypeError:
                pass
            except AttributeError:
                pass
            except Exception:
                # FIXME Tighten the exceptions caught by this block
                traceback.print_exc()
                # Most likely raised during interpreter shutdown due
                # to unclean exit which failed to remove all observers.
                # To solve this, we set the stop event and pass the
                # exception to let the thread finish gracefully.
                self.stopEvent.set()

    def stop(self):
        self.stopEvent.set()
        self.join()


if __name__ == "__main__":
    print('insert or remove cards in the next 10 seconds')

    # a simple card observer that prints added/removed cards
    class printobserver(CardObserver):

        def __init__(self, obsindex):
            self.obsindex = obsindex

        def update(self, observable, handlers):
            addedcards, removedcards = handlers
            print("%d - added:   %s" % (self.obsindex, str(addedcards)))
            print("%d - removed: %s" % (self.obsindex, str(removedcards)))

    class testthread(Thread):

        def __init__(self, obsindex):
            Thread.__init__(self)
            self.readermonitor = CardMonitor()
            self.obsindex = obsindex
            self.observer = None

        def run(self):
            # create and register observer
            self.observer = printobserver(self.obsindex)
            self.readermonitor.addObserver(self.observer)
            sleep(10)
            self.readermonitor.deleteObserver(self.observer)

    t1 = testthread(1)
    t2 = testthread(2)
    t1.start()
    t2.start()
