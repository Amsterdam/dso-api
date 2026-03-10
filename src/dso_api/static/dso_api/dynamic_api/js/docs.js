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
        const alert = document.getElementById("auth-alert")
        alert.remove()

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

// Entra ID module init
const msalInstance = new msal.PublicClientApplication(msalConfig);
let isInitialized = false;


function onPageLoad() {
    // Check if token is received when redirected from Entra log in
    document.addEventListener('DOMContentLoaded', initializeMsal);
    initializeMsal();

    confidential_links = Array.from(
        document.getElementsByClassName("confidential")
    )
    confidential_links.map((link) => {
        link.addEventListener("click", (e) => {
            e.preventDefault()
            const url = link.href
            const token = JSON.parse(window.localStorage.getItem("authToken"))
            if (token) {
                var access_token = (token.access_token) ? token.access_token : token.accessToken
                tokenPayload = JSON.parse(
                    atob(access_token.split(".")[1])
                )
                const exp = new Date(tokenPayload.exp * 1000)
                const now = new Date()
                if (exp > now) {
                    getData(url, {
                        Authorization: `Bearer ${access_token}`,
                    })
                } else {
                    console.log("Token is expired! Refreshing now.")
                    window.localStorage.setItem("exportURL", url)
                    if (token.access_token) {
                        authorizeKeycloak()
                    }
                    else {
                        authorizeEntra()
                    }
                }
            } else {
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
}

async function initializeMsal() {
    if (isInitialized) return;

    try {
        const response = await msalInstance.handleRedirectPromise();
        if (response) {
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
    } catch (error) {
        console.error('Redirect processing failed:');
        console.log(error)
    }
    isInitialized = true;
}
