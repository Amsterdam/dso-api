if (document.addEventListener) {
    document.addEventListener("DOMContentLoaded", onPageLoad)
}

// Override the same object from browsable_api.js, as this one we don't want to alter the DOM
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

        const alert = window.document.getElementById("auth-alert")
        if (alert){
            console.log(alert)
            alert.innerHTML = "<strong>Inloggen gelukt! Je kunt de actie nu uitvoeren.</strong>"
        }
    },
}


function onPageLoad() {
    console.log("Loading doc page now!")
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
                    if (token.access_token) {
                        const token = authorizeKeycloak()
                        console.log(token)
                        getData(url, {
                            Authorization: `Bearer ${access_token}`,
                        })
                    }
                    else {
                        console.log("Refreshing Entra token")
                        const token = authorizeEntra()
                        console.log(token)
                        getData(url, {
                            Authorization: `Bearer ${access_token}`,
                        })
                    }
                }
            } else {
                console.log("No token found in local storage, please authorize with Keycloak or Entra")
                showAuthAlert(e)
            }
        })
    })
}

function showAuthAlert(event){
    // Show alert with authorization buttons
    parent = event.target.parentNode.parentNode

    alert = document.createElement("div")
    alert.id = "auth-alert"
    alert.style.backgroundColor = "#c5dcf1"
    alert.style.borderRadius = "5px"
    alert.style.padding = "15px"
    alert.style.margin = "10px"
    alert.innerHTML = "<strong>Voor deze actie moet je ingelogd zijn. Kies één van onderstaande inlogmethodes:</strong>"
    //alert.innerHTML = "Voor deze actie moet je ingelogd zijn. Kies één van onderstaande inlogmethodes:"

    btnDiv = document.createElement("div")
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

    alert.appendChild(btnDiv)
    parent.appendChild(alert)

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
        const alert = window.document.getElementById("auth-alert")
        alert.remove()
}
