# Route all read requests to the replica databases
# Route all write requests to the default database

import random
import environ
env = environ.Env()


class DatabaseRouter:
    def db_for_read(self, model, **hints):
        if env.str('PGHOST_REPLICA_1') and env.str('PGHOST_REPLICA_2'):
            return random.choice(['replica_1', 'replica_2'])
        return 'replica_1'

    def db_for_write(self, model, **hints):
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return True
