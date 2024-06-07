# Route all read requests to the replica databases
# Route all write requests to the default database

import random

import environ
from django.conf import settings

env = environ.Env()

replicas = []
for replica in range(1, settings.MAX_REPLICA_COUNT + 1):
    if env.str(f"PGHOST_REPLICA_{replica}", False):
        replicas.append(f"replica_{replica}")
    else:
        break


class DatabaseRouter:
    """
    When using replica databases, route all read requests to the
    replica database(s) and all write requests to the default database.
    """

    def db_for_read(self, model, **hints):
        """
        Assign the replica databases to read requests.
        When multple replica databases are available, choose one at random
        """
        if len(replicas) > 1:
            return random.choice(replicas)  # nosec: B311
        return "replica_1"

    def db_for_write(self, model, **hints):
        return "default"

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return True
