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
        const url = window.localStorage.getItem("exportURL")
        if (url) {
            getData(url, {
                Authorization: `Bearer ${token.access_token}`,
            })
            window.localStorage.removeItem("exportURL")
        }
    },
}

// Entra ID module init
const msalInstance = new msal.PublicClientApplication(msalConfig)
let isInitialized = false

function onPageLoad() {
    // Check if token is received when redirected from Entra log in
    document.addEventListener("DOMContentLoaded", initializeMsal)
    initializeMsal()

    confidential_links = Array.from(
        document.getElementsByClassName("confidential")
    )
    confidential_links.map((link) => {
        link.addEventListener("click", (e) => {
            e.preventDefault()
            const url = link.href
            const token = JSON.parse(window.localStorage.getItem("authToken"))
            if (token) {
                var accessToken = token.access_token || token.accessToken
                tokenPayload = JSON.parse(atob(accessToken.split(".")[1]))
                const exp = new Date(tokenPayload.exp * 1000)
                const now = new Date()
                if (exp > now) {
                    getData(url, {
                        Authorization: `Bearer ${accessToken}`,
                    })
                } else {
                    window.localStorage.setItem("exportURL", url)
                    if (token.accessToken) {
                        authorizeKeycloak()
                    } else {
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

function showAuthAlert(event) {
    // Show alert with authorization buttons
    const parent = event.target.parentNode.parentNode.parentNode


    const alert_banner = document.createElement("div")
    alert_banner.id = "auth-alert"
    alert_banner.style.backgroundColor = "#c5dcf1"
    alert_banner.style.borderRadius = "5px"
    alert_banner.style.padding = "15px"
    alert_banner.style.margin = "10px"
    alert_banner.innerHTML =
        "<strong>Voor deze actie moet je ingelogd zijn. Kies één van onderstaande inlogmethodes:</strong>"
    const btnDiv = document.createElement("div")
    btnDiv.id = "auth-btn-div"
    btnDiv.style.marginTop = "10px"

    // Entra button
    const entraButton = document.createElement("button")
    entraButton.className = "btn btn-primary"
    entraButton.style.backgroundColor = "green"
    entraButton.innerText = "Authorize Entra ID"
    entraButton.style.marginRight = "10px"
    entraButton.addEventListener("click", authorizeEntra)
    if (AUTHORITY_ENTRA == "None") {
        entraButton.disabled = true
        entraButton.title = "Entra authority is niet geconfigureerd."
    }
    btnDiv.appendChild(entraButton)

    // KeyCloak button
    const kcButton = document.createElement("button")
    kcButton.className = "btn btn-primary"
    kcButton.style.backgroundColor = "green"
    kcButton.innerText = "Authorize KeyCloak"
    kcButton.addEventListener("click", authorizeKeycloak)
    if (OAUTHURI == "None") {
        kcButton.disabled = true
        kcButton.title = "Keycloak auth url is niet geconfigureerd."
    }
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
    if (isInitialized) return

    try {
        const response = await msalInstance.handleRedirectPromise()
        if (response) {
            isInitialized = true
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
        console.error("Redirect processing failed:")
        console.log(error)
    }
}
