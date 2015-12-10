"""Broker for dispaching messages in Open Library.

Message Broker or the pub/sub messaging patten allows publishers and
subscribers of messages to communite without the knowledge of each other. This
usally leads to a loosely-coupled design.

For examaple, the borrow module can send messages about loan-created and
loan-completed and the stats module can subscribe to these events and update
the database used for displaying loan graphs.
"""

import eventer

send_message = eventer.trigger
subscribe = eventer.bind
unsubscribe = eventer.unbind
