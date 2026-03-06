function authorizeKeycloak() {
    console.log("AuthorizeKeycloak button pressed!")
    // Start authorization flow
    authUrl = new URL(OAUTHURI)
        if (typeof oaSpec !== 'undefined' && oaSpec !== null) {
        authUrl = new URL(
            oaSpec.components.securitySchemes.oauth2.flows.implicit.authorizationUrl
        )
    }
    authUrl.searchParams.set("client_id", CLIENTID)
    authUrl.searchParams.set("redirect_uri", REDIRECTURI)
    authUrl.searchParams.set("response_type", "token")
    window.open(authUrl, "_blank")
}


// Add token to headers and setting
function addHeadersSetting(response){
    if (typeof addSetting === 'function') {
        addSetting("Authorization", "Bearer " + response.accessToken)
    }
    if (typeof showHeaders === 'function') {
        showHeaders()
    }
}

// Entra ID authorization config
const msalConfig = {
    auth: {
        clientId: CLIENTID_ENTRA,
        authority: AUTHORITY_ENTRA,
        redirectUri: window.location.origin + '/v1',
    }
};

// Entra ID module init
const msalInstance = new msal.PublicClientApplication(msalConfig);

async function authorizeEntra() {
    console.log("AuthorizeEntra button pressed!")
    const request = {
        scopes: [`${CLIENTID_ENTRA}/.default`]
    }
    try {
        const accounts = msalInstance.getAllAccounts();
        console.log(accounts)
        if (accounts.length === 0) {
            console.log("Trying loginPopup")
            const response = await msalInstance.loginPopup({
                scopes: [`${CLIENTID_ENTRA}/.default`]
            });
            window.localStorage.setItem("authToken", JSON.stringify(response))
            // for browsable api
            addHeadersSetting(response)

            // for doc downloads
            const alert = window.document.getElementById("auth-alert")
            if (alert){
                console.log(alert)
                alert.innerHTML = "<strong>Inloggen gelukt! Je kunt de actie nu uitvoeren.</strong>"
            }
        }
        else if (accounts.length === 1) {
            console.log("Found 1 account")
            console.log(accounts[0])
            request.account = accounts[0]
            try {
                console.log("iframe check")
                console.log(window.self === window.top)
                console.log("Trying acquireTokenPopup")
                const response = await msalInstance.acquireTokenPopup(request)

                window.localStorage.setItem("authToken", JSON.stringify(response))

                // for browsable api
                addHeadersSetting(response)

                // for doc downloads
                const alert = window.document.getElementById("auth-alert")
                if (alert){
                    console.log(alert)
                    alert.innerHTML = "<strong>Inloggen gelukt! Je kunt de actie nu uitvoeren.</strong>"
                }

            } catch (error) {
                console.log("Retrieving access token failed")
                console.log(error)
            }
        }
        else {
            console.log("Found multiple accounts, clearing session storage")
            sessionStorage.clear();
        }
    } catch (error) {
        console.log(error)
        if (error.errorCode === 'interaction_in_progress') {
            sessionStorage.clear();
        }
    }
}
