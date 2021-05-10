Creating Azure AD Application for OAuth2 Authentication
=======================================================

In order to use Azure AD as authentication backend for DSO API
we need to create Application Registration.

1. In Azure Portal Navigate to ``Azure Active Directory``
2. Go to ``App Registrations``
3. Click on ``+ New Registration``


.. figure:: /images/azure_ad_config_1.png
   :width: 818
   :height: 592
   :scale: 100%
   :alt: Creating new Application Registration via Azure Portal


Now it's time to create Application Registration:

1. Enter user friendly name for your Application (we use ``DSO-API-D``).
2. Select first option within ``Supported Account Types`` (Accounts in this organisation directory only)
3. Enter ``http://localhost:8000/v1/oauth2-redirect.html`` as Redirect URI
4. Press "Register"

.. figure:: /images/azure_ad_config_2.png
   :width: 827 
   :height: 1087
   :scale: 100%
   :alt: Creating new Application Registration via Azure Portal



Now we have Application registered and almost ready to go.
From Overview page we can get settings for environment variables used by DSO API:

1. Application ID for ``AZURE_AD_CLIENT_ID``
2. Directory ID for ``AZURE_AD_TENANT_ID``

.. figure:: /images/azure_ad_config_4.png
   :width: 712
   :height: 507
   :scale: 100%
   :alt: Creating new Application Registration via Azure Portal

Last, but not least:

.. figure:: /images/azure_ad_config_3.png
   :width: 848
   :height: 996
   :scale: 100%
   :alt: Creating new Application Registration via Azure Portal

Navigate to Authentication page and in Implicit grant and hybrid flows section select ``Access Tokens`` checkbox and save settings.
