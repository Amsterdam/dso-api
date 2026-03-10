if (document.addEventListener) {
    document.addEventListener("DOMContentLoaded", onPageLoad)
}

// Override the same object from browsable_api.js, as this one we don't want to alter the DOM
// This is just for Keycloak
window.swaggerUIRedirectOauth2 = {
    state: null,
    redirectUrl: REDIRECTURI,
    auth: {
        schema: {
            get: (t) => {
                return "implicit"
            },
        },
        code: null,
    },
    errCb: (err) => console.log("err callback", err),
    callback: (authorizationResult) => {
        const token = authorizationResult.token
        window.localStorage.setItem("authToken", JSON.stringify(token))

        // If exportURL is saved in local storage, download export
        if (window.localStorage.getItem("exportURL")) {
            const url = window.localStorage.getItem("exportURL")
            getData(url, {
                Authorization: `Bearer ${token.access_token}`,
            })
            window.localStorage.removeItem("exportURL")
        }
    },
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
let isInitialized = false;


function onPageLoad() {
    console.log("Loading doc page now!")
    // Check if token is received when redirected from Entra log in
    document.addEventListener('DOMContentLoaded', initializeMsal);
    initializeMsal();

    confidential_links = Array.from(
        document.getElementsByClassName("confidential")
    )
    console.log("Now logging all confidential links:")
    console.log(confidential_links)
    confidential_links.map((link) => {
        link.addEventListener("click", (e) => {
            console.log("Confidential link clicked!!")
            e.preventDefault()
            const url = link.href
            const token = JSON.parse(window.localStorage.getItem("authToken"))
            console.log("Token:")
            console.log(token)
            if (token) {
                if (token.access_token) {
                    // This is a Keycloak token
                    access_token = token.access_token
                    console.log("Keycloak token")
                }
                else {
                    // This is an Etra token
                    access_token = token.accessToken
                    console.log("Entra token")
                }
                tokenPayload = JSON.parse(
                    atob(access_token.split(".")[1])
                )
                const exp = new Date(tokenPayload.exp * 1000)
                const now = new Date()
                console.log(exp)
                if (exp > now) {
                    console.log("Token still valid, but showing alert for dev purposes:")
                    getData(url, {
                        Authorization: `Bearer ${access_token}`,
                    })
                } else {
                    console.log("Token is expired! Refreshing now.")
                    window.localStorage.setItem("exportURL", url)
                    if (token.access_token) {
                        authorizeKeycloak()
                        //window.localStorage.setItem("authToken", JSON.stringify(response))

                        //getData(url, {
                            //Authorization: `Bearer ${access_token}`,
                        //})
                    }
                    else {
                        console.log("Refreshing Entra token")
                        authorizeEntra()
                        //getData(url, {
                            //Authorization: `Bearer ${access_token}`,
                        //})
                    }
                }
            } else {
                console.log("No token found in local storage, please authorize with Keycloak or Entra")
                window.localStorage.setItem("exportURL", url)
                showAuthAlert(e)
            }
        })
    })
}

function showAuthAlert(event){
    // Show alert with authorization buttons
    const parent = event.target.parentNode.parentNode

    const alert_banner = document.createElement("div")
    alert_banner.id = "auth-alert"
    alert_banner.style.backgroundColor = "#c5dcf1"
    alert_banner.style.borderRadius = "5px"
    alert_banner.style.padding = "15px"
    alert_banner.style.margin = "10px"
    alert_banner.innerHTML = "<strong>Voor deze actie moet je ingelogd zijn. Kies één van onderstaande inlogmethodes:</strong>"
    //alert_banner.innerHTML = "Voor deze actie moet je ingelogd zijn. Kies één van onderstaande inlogmethodes:"

    const btnDiv = document.createElement("div")
    btnDiv.id = 'auth-btn-div'
    btnDiv.style.marginTop = "10px"

    // Entra button
    const entraButton = document.createElement("btn")
    entraButton.className = "btn btn-primary {% if not oauth_authority_entra %}disabled{% endif %}"
    entraButton.style.backgroundColor = "green"
    entraButton.innerText = "Authorize Entra ID"
    entraButton.style.marginRight = "10px"
    entraButton.addEventListener('click', authorizeEntra)
    btnDiv.appendChild(entraButton)

    // KeyCloak button
    const kcButton = document.createElement("btn")
    kcButton.className = "btn btn-primary {% if not oauth_url %}disabled{% endif %}"
    kcButton.style.backgroundColor = "green"
    kcButton.innerText = "Authorize KeyCloak"
    kcButton.addEventListener('click', authorizeKeycloak)
    btnDiv.appendChild(kcButton)

    alert_banner.appendChild(btnDiv)
    parent.appendChild(alert_banner)

}

window.dsoShowToken = () => {}

async function getData(blobUrl, headers) {
    await fetch(blobUrl, { method: "GET", headers })
        .then((response) => {
            if (!response.ok) {
                throw new Error(response.statusText)
            }
            return response.blob()
        })
        .then((response) => {
            const fileName = blobUrl.replace(/^.*[\\/]/, "")
            const url = window.URL.createObjectURL(response)
            const a = document.createElement("a")
            a.style.display = "none"
            a.href = url
            a.download = fileName
            document.body.appendChild(a)
            a.click()
            window.URL.revokeObjectURL(url)
        })
        .catch((error) => {
            console.error("Error downloading file:", error)
        })
        const alert_banner = window.document.getElementById("auth-alert")
        alert_banner.remove()
}

async function initializeMsal() {
    console.log("Checking if msal is initialised")
    if (isInitialized) return;

    try {
        console.log("Awaitng handleRedirectPromise:")
        const response = await msalInstance.handleRedirectPromise();
        if (response) {
            console.log('Login complete, token saved');
            console.log(response)
            window.localStorage.setItem("authToken", JSON.stringify(response))

            // If exportURL is saved in local storage, download export
            if (window.localStorage.getItem("exportURL")) {
                const url = window.localStorage.getItem("exportURL")
                getData(url, {
                    Authorization: `Bearer ${response.accessToken}`,
                })
                window.localStorage.removeItem("exportURL")
            }
        }
        else {
            console.log("No response")
        }
    } catch (error) {
        console.error('Redirect processing failed:');
        console.log(error)
    }
    isInitialized = true;
}


async function authorizeEntra() {
    console.log("AuthorizeEntra button pressed!")
    const request = {scopes: [`${CLIENTID_ENTRA}/.default`]}
    try {
        const accounts = msalInstance.getAllAccounts();
        console.log(accounts)
        if (accounts.length === 0) {
            console.log("Calling loginRedirect")
            await msalInstance.loginRedirect({
                scopes: [`${CLIENTID_ENTRA}/.default`]
            });
        }
        else if (accounts.length === 1) {
            console.log("Found 1 account")
            console.log(accounts[0])
            request.account = accounts[0]
            try {
                console.log("Trying acquireTokenRedirect")
                await msalInstance.acquireTokenRedirect(request)
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

function authorizeKeycloak() {
    console.log("AuthorizeKeycloak button pressed!")
    // Start authorization flow
    authUrl = new URL(OAUTHURI)
    authUrl.searchParams.set("client_id", CLIENTID)
    authUrl.searchParams.set("redirect_uri", REDIRECTURI)
    authUrl.searchParams.set("response_type", "token")
    window.open(authUrl, "_blank")
}
