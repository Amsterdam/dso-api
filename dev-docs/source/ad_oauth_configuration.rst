Creating Azure AD Application for OAuth2 Authentication
=======================================================

In order to use Azure AD as authentication backend for DSO API
we need to create Application Registration.


* Go to Azure Portal
* Navigate to ``Azure Active Directory``
* Go to ``App Registrations``
* Click on ``+ New Registration``
* Enter user friendly name for your Application (we use DSO-D).
* Select first option within ``Supported Account Types`` (Accounts in this organisation directory only)
* Enter http://localhost:8000/v1/oauth2-redirect.html as Redirect URI
* Press "Register"

Now we have Application registered and almost ready to go.

From Overview page we can get settings for environment variables used by DSO API:

* Application ID for ``AZURE_AD_CLIENT_ID``
* Directory ID for ``AZURE_AD_TENANT_ID``

Last, but not least:

Navigate to Authentication page and in Implicit grant and hybrid flows section select ``Access Tokens`` checkbox and save settings.