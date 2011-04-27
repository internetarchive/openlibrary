"""Broker for dispaching messages in Open Library.

Message Broker or the pub/sub messaging patten allows publishers and
subscribers of messages to communite without the knowledge of each other. This
usally leads to a loosely-coupled design.

For examaple, the borrow module can send messages about loan-created and
loan-completed and the stats module can subscribe to these events and update
the database used for displaying loan graphs.
"""

from collections import defaultdict
import sys
import traceback
import web

_subscribers = defaultdict(list)

def send_message(topic, data):
    """Notifies all the listener of the given topic.

    Each listener is called with given data as argument.
    """
    listeners = _subscribers[None] + _subscribers[topic]

    for listener in listeners:
        try:
            listener(data)
        except Exception, e:
            print >> sys.stderr, "Failed to notify a listener. listener: %s, topic: %s" % (listener, topic)
            traceback.print_exc()

def subscribe(topic, listener):
    """Subscribes the listener to all messages of the specified topic.

    If topic is None, the listsner is subscribed to messages of all topics.
    """
    _subscribers[topic].append(listener)

def unsubscribe(topc, listener):
    """Unsubscribes the listener from messages of the specified topic.
    """
    try:
        _subscribers[topic].remove(listener)
    except ValueError:
        # ignore if the listener is not subscribed to the given topic.
        pass