class ExternDatabaseRouter:
    """
    A router to control all database operations on models in the
    apps that have data in other databases like bag
    """

    route_app_labels = {"bag"}

    def db_for_read(self, model, **hints):
        """
        Attempts to read bag go to bag_v11.
        """
        if model._meta.app_label in self.route_app_labels:
            return "bag_v11"
        return None

    def db_for_write(self, model, **hints):
        """
        Attempts to write.
        """
        return None

    def allow_relation(self, obj1, obj2, **hints):
        """
        For now return None. Then relations are only allowed id they are in the same database.
        """
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Do not allow migration for 'bag'
        """
        if app_label in self.route_app_labels:
            return False
        return None
