# Route all read requests to the replica databases
# Route all write requests to the default database

import random
import environ
env = environ.Env()

replicas = []
for replica in range(1, 11):
    if env.str(f'PGHOST_REPLICA_{replica}', False):
        replicas.append(f'replica_{replica}')
    else:
        break

class DatabaseRouter:
    def db_for_read(self, model, **hints):
        if replicas:
            return random.choice(replicas)
        return 'replica_1'

    def db_for_write(self, model, **hints):
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return True
