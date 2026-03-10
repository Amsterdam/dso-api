function authorizeKeycloak() {
    // Start authorization flow
    authUrl = new URL(OAUTHURI)
    authUrl.searchParams.set("client_id", CLIENTID)
    authUrl.searchParams.set("redirect_uri", REDIRECTURI)
    authUrl.searchParams.set("response_type", "token")
    window.open(authUrl, "_blank")
}

// Entra ID authorization config
const msalConfig = {
    auth: {
        clientId: CLIENTID_ENTRA,
        authority: AUTHORITY_ENTRA,
        redirectUri: window.location.origin + '/v1',
    }
};

async function authorizeEntra() {
    const request = {scopes: [`${CLIENTID_ENTRA}/.default`]}
    try {
        const accounts = msalInstance.getAllAccounts();
        if (accounts.length === 0) {
            await msalInstance.loginRedirect({
                scopes: [`${CLIENTID_ENTRA}/.default`]
            });
        }
        else if (accounts.length === 1) {
            request.account = accounts[0]
            try {
                await msalInstance.acquireTokenRedirect(request)
            } catch (error) {
                console.log("Retrieving access token failed")
                console.log(error)
            }
        }
        else {
            sessionStorage.clear();
        }
    } catch (error) {
        console.log(error)
        if (error.errorCode === 'interaction_in_progress') {
            sessionStorage.clear();
        }
    }
}
