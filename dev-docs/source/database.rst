Database Notes
==============

Database Roles
--------------

The end-user context is provided to the database. This helps:

* Restrict table/field access on a database level using PostgreSQL roles.
* The database logs show who performed a query (by setting application name).
* The application can't accidentally query sensitive data (by switching roles).

For every internal user, there should be a :samp:`{username}_role` present in the database.
This is created by our internal *dp-infra* repository.

When such user is not present, all ``@amsterdam.nl`` addresses will fallback to an
internal ``medewerker_role``. The other accounts fallback to a ``anonymous_role``.

Switching Roles
~~~~~~~~~~~~~~~

The application user has been granted a role that includes *all* user roles
with ``NOINHERIT``. This way, the application-user can perform a ``SET ROLE`` command,
to switch the user role based on the session. There is a separate role for anonymous access.

The application-user is configured to switch to a role that
has sufficient permission to read metadata about datasets after ``LOGIN``

Note that when switching to a role, another ``SET ROLE`` command is still possible
because the current user doesn't change; only the current role does.

Installing Roles
~~~~~~~~~~~~~~~~

The ``schema permission apply`` command will parse all Amsterdam Schema files,
and install the database roles and grants for all permission types.

Each user-role becomes a member of these groups, based on their membership in Active Directory.
