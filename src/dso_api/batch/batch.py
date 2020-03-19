import gc
import logging

log = logging.getLogger(__name__)


class BasicJob:
    """Interface for jobs"""

    name = None

    def tasks(self) -> list:
        pass


def execute(job: BasicJob):
    log.info("Starting job: %s [%s]", job.name, job.__class__.__name__)

    for task in job.tasks():
        _execute_task(task)

    log.info("Finished job: %s: [%s]", job.name, job.__class__.__name__)


def _execute_task(task):

    if callable(task):
        task_name = task.__name__
        execute_func = task
    else:
        task_name = getattr(task, "name", "no name specified")
        execute_func = task.execute

    log.debug("Starting task: %s", task_name)

    execute_func()


class BasicTask:
    """
    Abstract task that splits execution into three parts:

    * ``before``
    * ``process``
    * ``after``

    """

    name = "Basic Task"

    def execute(self):
        self.before()
        self.process()
        self.after()
        gc.collect()

    def before(self):
        pass

    def after(self):
        pass

    def process(self):
        pass
