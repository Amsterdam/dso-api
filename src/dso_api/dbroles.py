"""Providing end-user context to the database.

This ensures that:

* the database logs show who performed a query (by setting application name).
* the application can't accidentally query sensitive data (by switching roles).

For every user, there should be a "{username}_role" present in the database.
This is created through the dp-infra repository.
The main DSO-API application-user has been granted a role that has all user roles
with NOINHERIT. This way, the application-user can SET ROLE to the user role
based on the session. There is a separate role for anonymous access.

The DSO-API application-user is configured to switch to a role that
has sufficient permission to read metadata about datasets after LOGIN

Note that when switching to a role, another ``SET ROLE`` command is still possible
because the current user doesn't change; only the current role does.
"""
from __future__ import annotations

import logging

from asgiref.local import Local
from django.conf import settings
from django.core.signals import request_finished
from django.db import DataError
from django.db import connection as default_connection
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.signals import connection_created
from django.db.utils import DatabaseError
from django.dispatch import receiver
from psycopg2.extensions import STATUS_IN_TRANSACTION

logger = logging.getLogger(__name__)


def is_internal(user_email: str) -> bool:
    """Tell whether a user is an internal user."""
    return user_email.endswith("@amsterdam.nl")


@receiver(connection_created)
def _connection_created(sender, connection: BaseDatabaseWrapper, **kwargs):
    """Perform the user switch when a database connection is made.
    This catches any late initialized connections, after middleware ran.
    """
    DatabaseRoles.activate_end_user(connection, log_source="connection_created")


@receiver(request_finished)
def _request_finished(sender, **kwargs):
    """Make sure the connection is reset on completion, so it can be reused for another session."""
    DatabaseRoles.deactivate_end_user()


class DatabaseRoles:
    """Handling altering PostgreSQL options."""

    #: The current user, tracked locally here by this class.
    current_user = Local()

    @classmethod
    def set_end_user(cls, user_email: str):
        """Tell which end user should be used for the database connection"""
        setattr(cls.current_user, "email", user_email)

        # Immediately activate the user too, in case a connection was already established.
        # Otherwise, the request waits for the 'connection_created' signal.
        # In case of static files, no database connection might be created at all.
        if default_connection.connection is not None:
            cls.activate_end_user(default_connection, log_source="set_end_user")

    @classmethod
    def _get_end_user(cls) -> str | None:
        """Tell which user was selected"""
        return getattr(cls.current_user, "email", None)

    @classmethod
    def activate_end_user(cls, user_connection: BaseDatabaseWrapper, *, log_source: str):
        """Switch to the end-user role in the database."""
        if not settings.DATABASE_SET_ROLE:
            # Feature flag for previous hosting location
            logger.info("%s: End-user feature disabled (DATABASE_SET_ROLE=false)", log_source)
            return

        if cls._get_role(user_connection):
            logger.debug("%s: End-user already set, no need to switch roles again", log_source)
            return

        user_email = cls._get_end_user()
        if not user_email:
            logger.debug("%s: No end-user email, switching to anonymous role", log_source)
            cls._set_role(user_connection, settings.ANONYMOUS_ROLE, settings.ANONYMOUS_APP_NAME)
            return

        logger.debug("%s: Activating end-user context for %s", log_source, user_email)

        # Log which role was activated
        # Define which role to switch to
        role_name = settings.USER_ROLE.format(user_email=user_email)
        try:
            # BBN2: Exact account for specific access.
            cls._set_role(user_connection, role_name, user_email)
        except DataError as e:
            # The role didn't exist.
            if is_internal(user_email):
                # BBN1: Internal employee, no specific account
                cls._set_role(user_connection, settings.INTERNAL_ROLE, user_email)
            else:
                logger.exception("External user %s has no database role %s", user_email, role_name)
                raise PermissionError(f"User {user_email} is not available in database") from e

    @classmethod
    def _original_role(cls):
        return getattr(cls.current_user, "original_role", None)

    @classmethod
    def _set_role(cls, user_connection: BaseDatabaseWrapper, role_name: str, app_name: str):
        # By starting a transaction (if needed), any connection pooling (e.g. PgBouncer)
        # can also ensure the connection is not reused for another session.
        with user_connection.cursor() as c:
            try:
                if not c.connection.status == STATUS_IN_TRANSACTION:
                    logger.debug("Starting transaction for user-context: %s", role_name)
                    c.execute("BEGIN TRANSACTION;")
                else:
                    # If we dont create a transaction here, we need to
                    # remember which role was active before the context
                    # started
                    c.execute("SELECT current_user;")
                    original_role = c.fetchone()[0]
                    logger.debug(
                        "Transaction already in progress storing original role: %s", original_role
                    )
                    setattr(cls.current_user, "original_role", original_role)

                c.execute(
                    "SAVEPOINT user_ctx; SET LOCAL ROLE %s; set application_name to %s;",
                    (role_name, app_name),
                )
            except DatabaseError as e:
                logger.debug("Switch role failed for %s: %s", role_name, e)
                c.execute("ROLLBACK TO user_ctx;")
                cls._revert_role(c)
                raise
            else:
                setattr(user_connection, "_active_user_role", role_name or "NONE")
                logger.info("Activated end-user database role '%s' for '%s'", role_name, app_name)

    @classmethod
    def _get_role(cls, user_connection: BaseDatabaseWrapper) -> str | None:
        return getattr(user_connection, "_active_user_role", None)

    @classmethod
    def _revert_role(cls, cursor):
        if cls._original_role():
            cursor.execute("SET ROLE %s;", (cls._original_role(),))

        setattr(cls.current_user, "original_role", None)

    @classmethod
    def deactivate_end_user(cls):
        """Rollback the transaction when the local user was activated."""
        user_email = cls._get_end_user()
        if not cls._get_role(default_connection):
            logger.debug("No end-user to revert")
            return

        # Close
        if default_connection.connection is not None:
            # Release the database connection for this user.
            # Either it now closes, or a connection pooler can re-use it.
            logger.info(
                "Terminating end-user-context for %s, switching to %s.",
                user_email,
                cls._original_role(),
            )
            with default_connection.cursor() as c:
                if not cls._original_role():
                    # Note that we cannot ROLLBACK because intermediate
                    # state that Django depends on will be removed.
                    c.execute("COMMIT;")

                cls._revert_role(c)
                setattr(default_connection, "_active_user_role", None)
