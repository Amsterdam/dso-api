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
    },
}

window.dsoShowToken = () => {}

function onPageLoad() {
    confidential_links = Array.from(
        document.getElementsByClassName("confidential")
    )
    confidential_links.map((link) => {
        link.addEventListener("click", (e) => {
            e.preventDefault()
            const url = link.href
            const token = JSON.parse(window.localStorage.getItem("authToken"))
            if (token) {
                const tokenPayload = JSON.parse(
                    atob(token.access_token.split(".")[1])
                )
                const exp = new Date(tokenPayload.exp * 1000)
                const now = new Date()
                if (exp > now) {
                    getData(url, {
                        Authorization: `Bearer ${token.access_token}`,
                    })
                } else {
                    authorize()
                }
            } else {
                authorize()
            }
        })
    })
}

function authorize() {
    // Start authorization flow
    authUrl = new URL(OAUTHURI)
    authUrl.searchParams.set("client_id", CLIENTID)
    authUrl.searchParams.set("redirect_uri", REDIRECTURI)
    authUrl.searchParams.set("response_type", "token")
    window.open(authUrl, "_blank")
}

async function getData(url, headers) {
    await fetch(url, { method: "GET", headers })
        .then((response) => {
            if (!response.ok) {
                throw new Error(response.statusText)
            }
            return response.blob()
        })
        .then((response) => {
            const fileName = url.replace(/^.*[\\/]/, "")
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
