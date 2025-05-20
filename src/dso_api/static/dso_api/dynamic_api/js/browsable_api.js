var PAGEURL = new URL(window.location.href)
var isPaginated = false

// Hack into swagger auth state
var swaggerUIRedirectOauth2 = {
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
        let headersEl = document.getElementById("request-headers")
        let token = authorizationResult.token
        window.localStorage.setItem("authToken", JSON.stringify(token))
        addSetting("Authorization", "Bearer " + token.access_token)
        showHeaders()
    },
}
var dsoShowToken = (token) => {}

// Open API variables
var oaParams = null
var oaSpec = null

if (document.readyState != "loading") {
    onPageLoad()
}
if (document.addEventListener) {
    document.addEventListener("DOMContentLoaded", onPageLoad)
}

function setURL(url) {
    // Update pageurl and sync query parameter settings
    PAGEURL = new URL(decodeURI(url))

    for (let paramkey of PAGEURL.searchParams.keys()) {
        let value = PAGEURL.searchParams.get(paramkey)
        let [key, operator] = splitKeyandOperator(paramkey)
        addSetting(key, value, operator, (type = "param"))
    }
}

window.onpopstate = function (e) {
    if (e.state) {
        setURL(e.state.url)
        setParams(e.state.params)
        updatePageRequest(e.state.url, e.state.method, false, e.state.headers)
    }
}

function onPageLoad() {
    let page = PAGEURL.searchParams.get("page")

    // Check if the URL has a trailing slash and we want to remove it
    if (PAGEURL.pathname.endsWith("/")) {
        let newPath = PAGEURL.pathname.slice(0, -1)
        let newUrl = new URL(PAGEURL)
        newUrl.pathname = newPath

        // Update the URL in the browser without reloading the page
        window.history.replaceState(null, "", newUrl)

        // Update PAGEURL
        PAGEURL = newUrl
    }

    setURL(PAGEURL.href)
    setParams()
    setHeaders()
    setPageLinks(page)

    getData(PAGEURL)
        .catch(parseException)
        .then((result) => {
            if (result.data) {
                parseData(result.data)
            }
            window.history.replaceState(
                JSON.parse(
                    JSON.stringify({
                        url: PAGEURL,
                        method: "get",
                        params: getRequestSettings(),
                        headers: getRequestSettings("headers"),
                    })
                ),
                "",
                PAGEURL
            )
        })

    getOpenApi((params) => {
        oaParams = params
        setParams()
        setHeaders()
        if (oaSpec) {
            document
                .getElementById("authorize-btn")
                .classList.remove("disabled")
        }
    })
    // Override the default DRF behaviour of the OPTIONS, and GET buttons,
    // which do not work with our script.
    // We make the request and replace the page content with the response.
    document.getElementById("options-button").onclick = (e) => {
        updatePageRequest(getUrlFromSettings(), "OPTIONS")
        e.preventDefault()
    }
    document.getElementById("get-button").onclick = (e) => {
        updatePageRequest(getUrlFromSettings())
        e.preventDefault()
    }
    for (let optEl of document.getElementsByClassName("format-option")) {
        optEl.onclick = (e) => {
            let formatValue = e.target.innerHTML
            url = getUrlFromSettings()
            url.searchParams.set("_format", formatValue)
            updateSetting("Accept", "*/*")
            updatePageRequest(url, "GET", true)
            e.preventDefault()
        }
    }

    document.getElementById("download-button").onclick = (e) => {
        url = getUrlFromSettings()
        formatValue = url.searchParams.get("_format") || "json"
        downloadData(url, "output." + formatValue)
        e.preventDefault()
    }
    for (let optEl of document.getElementsByClassName(
        "download-format-option"
    )) {
        optEl.onclick = (e) => {
            let formatValue = e.target.innerHTML
            url = getUrlFromSettings()
            url.searchParams.set("_format", formatValue)
            updateSetting("Accept", "*/*")
            downloadData(url, "output." + formatValue)
            e.preventDefault()
        }
    }
}

function downloadData(url, defaultFilename) {
    headerSettings = getRequestSettings("headers")
    headers = {}
    headerSettings.forEach((h) => {
        if (h.active) {
            headers[h.key] = h.value
        }
    })

    getData(url, "GET", headers, false, true)
        .catch(parseException)
        .then((result) => {
            let headerValue = result.response.getResponseHeader(
                "Content-Disposition"
            )
            let fileName = defaultFilename
            if (headerValue)
                fileName = /.*filename=\"(.*)\"/.exec(headerValue)[1]

            // the document has to be compatible with Excel, we export in UTF-8
            // we add the BOF for UTF-8, Excel requires this information to show chars with accents etc.
            let blob = new Blob(
                [new Uint8Array([0xef, 0xbb, 0xbf]), result.data],
                {
                    type: "text/plain;charset=utf-8",
                }
            )

            if (window.navigator.msSaveOrOpenBlob) {
                window.navigator.msSaveBlob(blob, filename)
            } else {
                let elem = window.document.createElement("a")
                elem.href = window.URL.createObjectURL(blob)
                elem.download = fileName
                document.body.appendChild(elem)
                elem.click()
                document.body.removeChild(elem)
            }
        })
}

function updatePageRequest(
    url,
    method = "GET",
    pushHistory = true,
    headerSettings = null
) {
    // Make a request to the api and update the page with the response
    let originalUrl = url

    // Check if the URL is without a trailing slash and we want to preserve it
    let urlObj = new URL(url)
    let preserveNoTrailingSlash = !urlObj.pathname.endsWith("/")

    setURL(url)

    if (headerSettings == null) {
        headerSettings = getRequestSettings("headers")
    }

    // Get the headers that should be used with the request
    headers = {}
    headerSettings.forEach((h) => {
        if (h.active) {
            headers[h.key] = h.value
        }
    })

    let reqInfoEl = document.getElementById("request-info")
    reqInfoEl.innerHTML = `<pre><b>${method}</b> ${PAGEURL}</pre>`
    document.getElementById("response-content").innerHTML = "Retrieving data..."
    document.getElementById("formatted-response-content").innerHTML =
        "Retrieving data..."
    let page = PAGEURL.searchParams.get("page")
    setPageLinks(page)

    // If we're preserving a URL without a trailing slash, add a trailing slash for the request
    // but keep the original URL for display and history
    let requestUrl = url
    if (preserveNoTrailingSlash) {
        requestUrl = urlObj.pathname + "/" + urlObj.search
    }

    getData(requestUrl, method, headers)
        .catch(parseException)
        .then((result) => {
            if (pushHistory) {
                window.history.pushState(
                    JSON.parse(
                        JSON.stringify({
                            url: originalUrl,
                            method: method,
                            params: getRequestSettings("params"),
                            headers: headerSettings,
                        })
                    ),
                    "",
                    originalUrl
                )
            }
            if (result.data) {
                parseData(result.data)
            }
            setParams()
            setHeaders(headerSettings)
        })
}

function authorize() {
    // Start authorization flow
    authUrl = new URL(OAUTHURI)
    if (oaSpec) {
        authUrl = new URL(
            oaSpec.components.securitySchemes.oauth2.flows.implicit.authorizationUrl
        )
    }
    authUrl.searchParams.set("client_id", CLIENTID)
    authUrl.searchParams.set("redirect_uri", REDIRECTURI)
    authUrl.searchParams.set("response_type", "token")
    window.open(authUrl, "_blank")
}

function getRequestSettings(type = "params") {
    // Get query parameter or header request settings from the form.
    let paramsEl = document.getElementById("request-" + type)
    return [...Array(paramsEl.childElementCount).keys()]
        .map((i) => {
            let paramEl = paramsEl.children.item(i)
            let key = paramEl.getElementsByClassName("param-key")[0].value
            let operator = paramEl.getElementsByClassName("param-op")[0].value
            let combinedKey = key
            if (operator != "eq") {
                combinedKey += `[${operator}]`
            }

            return {
                active: paramEl.getElementsByClassName("param-check")[0]
                    .checked,
                key: key,
                combinedKey: combinedKey,
                operator: operator,
                value: paramEl.getElementsByClassName("param-val")[0].value,
                element: paramEl,
            }
        })
        .filter((x) => x.key != "")
}

function getUrlFromSettings() {
    // Get the URL of this endpoint with new request parameter settings
    let url = new URL(PAGEURL)
    url.search = ""
    getRequestSettings().forEach((param) => {
        if (param.active && param.key != "") {
            url.searchParams.set(param.combinedKey, param.value)
        }
    })
    return url
}

function getPageUrl(page) {
    // Get the URL of another page of this endpoint
    let url = new URL(PAGEURL)
    url.searchParams.set("page", page)
    return url
}

function setPageLinks(page) {
    // Set the pagination links with the correct values for this page
    page = Number(page)

    let pageLinksEl = document.getElementById("page-links")
    pageLinksEl.innerHTML = `
          <li class="disabled"><a href="" aria-label="Previous"><span aria-hidden="true">«</span></a></li>
          <li class="hidden"><a href="">1</a></li>
          <li class="hidden"><a href="#"><span aria-hidden="true">…</span></a></li>
          <li class="hidden"><a href="#"></a></li>
          <li class="hidden"><a href="#"></a></li>
          <li class="active this-page"><a href="#"></a></li>
          <li class="hidden"><a href="#"></a></li>
          <li class="hidden"><a href=""></a></li>
          <li class="hidden"><a href="#"><span aria-hidden="true">…</span></a></li>
          <li class="hidden"><a href=""></a></li>
          <li class="disabled"><a href="#" aria-label="Next"><span aria-hidden="true">»</span></a></li>
    `

    if (isNaN(page) || page < 1) {
        isPaginated = false
        return
    }
    isPaginated = true

    let links = pageLinksEl.getElementsByTagName("li")
    links = [...Array(links.length).keys()].map((i) => {
        return {
            li: links.item(i),
            a: links.item(i).getElementsByTagName("a")[0],
        }
    })

    // Set forward page links, but leave disabled for now.
    links[PAGELINKS.NEXT]["a"].setAttribute("href", getPageUrl(page + 1))
    links[PAGELINKS.FORWARD1]["a"].setAttribute("href", getPageUrl(page + 1))
    links[PAGELINKS.FORWARD1]["a"].innerHTML = page + 1
    links[PAGELINKS.FORWARD2]["a"].setAttribute("href", getPageUrl(page + 2))
    links[PAGELINKS.FORWARD2]["a"].innerHTML = page + 2
    links[PAGELINKS.FORWARD3]["a"].setAttribute("href", getPageUrl(page + 3))
    links[PAGELINKS.FORWARD3]["a"].innerHTML = page + 3
    links[PAGELINKS.LAST]["a"].setAttribute("href", getPageUrl(page + 4))
    links[PAGELINKS.LAST]["a"].innerHTML = page + 4

    links.forEach((link) => {
        link["a"].onclick = (e) => {
            updateSetting(
                "page",
                new URL(e.target.href).searchParams.get("page"),
                "eq",
                (type = "param")
            )
            setURL(e.target.href)
            updatePageRequest(e.target.href)
            e.preventDefault()
        }
    })

    // Set self and previous links
    for (let i = 0; page - i && i < NUM_EXTRA_PAGES; i++) {
        let el = links[PAGELINKS.SELF - i]
        el["a"].setAttribute("href", getPageUrl(page - i))
        el["a"].innerHTML = page - i
        el["li"].classList.remove("hidden")
    }

    if (page > 1) {
        // Set previous link
        links[PAGELINKS.PREVIOUS]["a"].setAttribute(
            "href",
            getPageUrl(page - 1)
        )
        links[PAGELINKS.PREVIOUS]["li"].classList.remove("disabled")

        if (page > 4) {
            // Set page 1 link
            links[PAGELINKS.ONE]["a"].setAttribute("href", getPageUrl(1))
            links[PAGELINKS.ONE]["li"].classList.remove("hidden")
        }
        if (page > 5) {
            // Set ... link
            links[PAGELINKS.BACK3]["a"].innerHTML = "..."
            links[PAGELINKS.BACK3]["li"].classList.add("disabled")
        }
    }
    // Show the links
    let containerEl = document.getElementById("page-container")
    containerEl.classList.add("active")
}

function getData(
    url,
    method = "GET",
    headers = DEFAULT_HEADERS,
    doParseHeaders = true,
    raw = false
) {
    return new Promise(function (callback, err) {
        let http = new XMLHttpRequest()
        http.open(method, url, true)
        for (let k in headers) {
            http.setRequestHeader(k, headers[k])
        }

        http.send()
        http.onreadystatechange = function () {
            if (this.readyState === 2 && doParseHeaders) {
                parseResponseHeaders(this)
            }
            if (this.readyState === 4) {
                try {
                    let result = this.responseText
                    if (!raw && result.length > 0 && result[0] === "{") {
                        result = JSON.parse(this.responseText)
                    }
                    callback({ data: result, response: this })
                } catch (error) {
                    parseResponseHeaders(this)
                    err([error, this.responseText])
                }
            }
        }
    })
}

function showHeaders() {
    document.getElementById("headers-tab").dispatchEvent(new Event("click"))
}

function addSetting(key, value, op = "eq", type = "header", active = true) {
    // Add new setting if identical setting does not exist,
    // deactivate other settings with same key and operator.
    let requestSettings = getRequestSettings(type + "s")
    let sameSetting = requestSettings.find(
        (x) => x.key == key && x.operator == op && x.value == value
    )
    requestSettings
        .filter((x) => x.key == key && x.operator == op && x.active)
        .forEach((setting) => {
            setting.element.getElementsByClassName(
                "param-check"
            )[0].checked = false
            setting.element
                .getElementsByClassName("param-check")[0]
                .dispatchEvent(new Event("change"))
        })
    if (sameSetting) {
        sameSetting.element.getElementsByClassName("param-check")[0].checked =
            active
        sameSetting.element
            .getElementsByClassName("param-check")[0]
            .dispatchEvent(new Event("change"))
        return
    }
    pushSetting(key, value, active, op, type)
}

function updateSetting(key, value, op = "eq", type = "header") {
    // Update value of existing setting with same key or add new setting if it does not exist
    let requestSettings = getRequestSettings(type + "s")
    let sameSetting = requestSettings.find(
        (x) => x.key == key && x.operator == op && x.value == value
    )
    if (sameSetting) {
        return
    }
    let setting = requestSettings.find(
        (x) => x.key == key && x.operator == op && x.active
    )
    if (setting) {
        setting.element.getElementsByClassName("param-val")[0].value = value
    } else {
        pushSetting(key, value, true, op, type)
    }
}

function pushSetting(key, val, active, op = "eq", type = "header") {
    // Add setting to list
    let paramsEl = document.getElementById("request-" + type + "s")
    let lastChild = paramsEl.lastElementChild
    let newParam = createParamEl(key, val, op, active, type)
    if (lastChild) {
        paramsEl.replaceChild(newParam, paramsEl.lastElementChild)
        paramsEl.appendChild(lastChild)
    } else {
        paramsEl.appendChild(newParam)
        paramsEl.appendChild(createParamEl(null, null, "eq", true, type))
    }
}

function escapeString(string) {
    let element = document.createElement("div")
    element.innerHTML = string
    return element.innerHTML
}

function parseResponseHeaders(response) {
    // Set header fields
    let headersElement = document.getElementById("response-headers")
    headersElement.innerHTML = `<b>HTTP ${response.status} ${response.statusText}</b>\n`

    for (let header of HEADERS) {
        let headerValue = response.getResponseHeader(header)
        if (headerValue) {
            let headerline = `<b>${header}:</b> <span class="lit">${escapeString(
                headerValue
            )}</span>\n`
            headersElement.innerHTML += headerline
        }
    }

    // Remove page links if no pagination (for error pages)
    let page = response.getResponseHeader("X-Pagination-Page")
    if (!page) {
        document.getElementById("page-container").classList.remove("active")
    } else if (!isPaginated) {
        // If paginated but pagination has not yet been set (for page 1)
        setPageLinks(page)
    }
}

function parseException(err) {
    let exception = err[0],
        responseText = err[1] // promises only allow 1 argument.
    console.error(
        "Failed to retrieve JSON API response from server:",
        exception
    )

    let contentElement = document.getElementById("response-content")
    let formattedContentElement = document.getElementById(
        "formatted-response-content"
    )
    contentElement.innerHTML = `Failed to retrieve valid response from server.

  `
    contentElement.innerHTML += responseText
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;")
    document.getElementById("response-info").className = "show-raw"
    formattedContentElement.innerHTML =
        "Failed to retrieve valid response from server."
}

function parseData(data) {
    let contentElement = document.getElementById("response-content")
    let formattedContentElement = document.getElementById(
        "formatted-response-content"
    )

    if (typeof data === "string") {
        document.getElementById("response-info").className = "show-raw"
        contentElement.innerText = data
        formattedContentElement.innerHTML = "No formatting available"
        return
    }

    // We need to mark coordinates fields so we can make them collapsible.
    let markCoordinates = (key, value) => {
        if (key == "coordinates") {
            return "__coordinatestring__" + JSON.stringify(value, null, 4)
        }
        return value
    }

    // Activate next links
    let containerEl = document.getElementById("page-container")
    if (data["_links"] && data["_links"]["next"]) {
        let links = document
            .getElementById("page-links")
            .getElementsByTagName("li")
        links = [...Array(links.length).keys()].map((i) => {
            return {
                li: links.item(i),
                a: links.item(i).getElementsByTagName("a")[0],
            }
        })
        links[PAGELINKS.NEXT]["li"].classList.remove("disabled")
        links[PAGELINKS.FORWARD1]["li"].classList.remove("hidden")

        // If the count is known (because user explicitly requested),
        // we can show a bit more information
        if (data["page"] && data["page"]["totalPages"]) {
            const numPages = data["page"]["totalPages"]
            const available = numPages - data["page"]["number"]
            if (available > NUM_EXTRA_PAGES) {
                links[PAGELINKS.LAST]["a"].setAttribute(
                    "href",
                    getPageUrl(numPages)
                )
                links[PAGELINKS.LAST]["a"].innerHTML = numPages
                links[PAGELINKS.FORWARD3]["a"].innerHTML = "..."
                links[PAGELINKS.FORWARD3]["li"].classList.add("disabled")
            }

            for (var i = 1; i < NUM_EXTRA_PAGES && i < available; i++) {
                links[PAGELINKS.FORWARD1 + i]["li"].classList.remove("hidden")
            }
        }
        containerEl.classList.add("active")
    } else if (data["_links"] && data["_links"]["previous"]) {
        containerEl.classList.add("active")
    } else {
        containerEl.classList.remove("active")
    }

    // Create highlighted html string and set content
    let jsonString = JSON.stringify(data, markCoordinates, 4)
    contentElement.innerHTML = syntaxHighlight(jsonString)

    // Format response if formatter is available
    if (typeof FORMATTER !== "undefined") {
        try {
            formattedContentElement.innerHTML = FORMATTER(data)
        } catch (error) {
            document.getElementById("response-info").className = "show-raw"
            formattedContentElement.innerHTML = "No formatting available"
        }
    }
}

function syntaxHighlight(jsonString) {
    // Escape HTML but leave quotemarks in place.
    jsonString = escapeString(jsonString)
    return jsonString.replace(
        /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
        function (match) {
            let cls = "number"
            if (/^"https?:\/\//.test(match)) {
                // Create a link for strings containing an url.
                let uri = match.substring(1, match.length - 1)
                return `<a href="${uri}" rel="nofollow"><span class="link">${match}</span></a>`
            }
            if (/^"__coordinatestring__/.test(match)) {
                // Cut the marker and enclosing quotes from the coordinates string and unescape newlines.
                match = match
                    .substring(21, match.length - 1)
                    .replace(/\\n/g, "\n")

                // Grab the head and tail for the summary and remove whitespace.
                let head = match.substring(0, 100).replace(/\n| /g, "")
                let tail = match
                    .substring(match.length - 100)
                    .replace(/\n| /g, "")

                // If coordinates don't describe a point.
                // Show a summary that can be expanded with a click.
                if (/^\[\[/.test(head)) {
                    let result = `<span class="collapsible collapsed" onClick="this.classList.toggle(\'collapsed\')">`
                    result += `<span class="collapsible_summary">${syntaxHighlight(
                        head
                    )} ... ${syntaxHighlight(tail)}</span>`
                    result += `<span class="collapsible_content">${syntaxHighlight(
                        match
                    )}</span></span>`
                    return result
                } else {
                    match = match.replace(/\n\s*/g, " ")
                }
            }
            if (/^"/.test(match)) {
                if (/:$/.test(match)) {
                    cls = "key"
                } else {
                    cls = "string"
                }
            } else if (/true|false/.test(match)) {
                cls = "bool"
            } else if (/null/.test(match)) {
                cls = "null"
            }
            return `<span class="${cls}">${match}</span>`
        }
    )
}

function splitKeyandOperator(value) {
    // Split key and operator from parameter like 'key[op]'
    let key = value.split("[")[0]
    let op = "eq"
    if (key != value) {
        op = value.split("[")[1].split("]")[0]
    }
    return [key, op]
}

function addParamEnumDatalist(param, name = null) {
    if (param.schema.enum) {
        let datalistsEl = document.getElementById("datalists")
        let datalistEl = document.createElement("datalist")
        datalistEl.id = `datalist-${name || param.name}-enum`
        for (item of param.schema.enum) {
            let option = document.createElement("option")
            option.value = item
            option.text = item
            datalistEl.appendChild(option)
        }
        datalistsEl.appendChild(datalistEl)
    }
}

function addParamExampleDatalist(param, name = null) {
    if (param.examples) {
        let datalistsEl = document.getElementById("datalists")
        let datalistEl = document.createElement("datalist")
        datalistEl.id = `datalist-${name || param.name}-examples`
        for (k in param.examples) {
            let option = document.createElement("option")
            option.value = param.examples[k].value
            option.text = param.examples[k].value
            option.title = param.examples[k].description
            datalistEl.appendChild(option)
        }
        datalistsEl.appendChild(datalistEl)
    }
}

function findOAPath(searchPath, paths) {
    // Find the Open API path template that matches the searchPath.
    // Only get the last part of the searchPath
    searchPath = "/" + searchPath.split("/").pop()

    if (paths.hasOwnProperty(searchPath)) {
        return searchPath
    }

    let parentSearchPath = searchPath.split("/").slice(0, -2).join("/")
    return (result = Object.keys(paths).find((path) => {
        let parentPath = path.slice(0, -1).split("/")
        l = parentPath.pop()
        return l.startsWith("{") && parentSearchPath == parentPath.join("/")
    }))
}

function getOpenApi(callback) {
    // Get OpenApi spec and extract parameters
    let oaURL = new URL(PAGEURL)
    let params = JSON.parse(JSON.stringify(DEFAULT_PARAMS))
    // Add Default headers.
    for (k in params) {
        addParamEnumDatalist(params[k], params[k].name + "[eq]")
        addParamExampleDatalist(params[k], params[k].name + "[eq]")
    }

    if (!DATASET_URL) {
        return callback(params)
    }

    oaURL.pathname = DATASET_URL
    oaURL.search = "?format=json"
    return getData(
        oaURL.href,
        "GET",
        {
            Accept: "*/*",
        },
        false
    ).then((result) => {
        oaJSON = result.data
        oaSpec = oaJSON
        let oaPath = findOAPath(PAGEURL.pathname, oaJSON.paths)

        // Return if current page is not an OA endpoint
        if (!oaPath) {
            return callback(params)
        }

        oaJSON.paths[oaPath].get.parameters
            .filter((a) => !a.name.includes("["))
            .forEach((x) => {
                addParamEnumDatalist(x, x.name + "[eq]")
                addParamExampleDatalist(x, x.name + "[eq]")
                let name = x.name
                param = JSON.parse(JSON.stringify(x))
                equalOp = JSON.parse(JSON.stringify(x))
                equalOp.name = "eq"
                param.operators = [equalOp]
                params[name] = param
            })
        oaJSON.paths[oaPath].get.parameters
            .filter((a) => a.name.includes("["))
            .forEach((x) => {
                addParamEnumDatalist(x)
                addParamExampleDatalist(x)
                let param = JSON.parse(JSON.stringify(x))
                let [key, op] = splitKeyandOperator(x.name)
                param.name = op
                params[key].operators.push(param)
            })

        // Add each parameter to the datalist
        for (inside of ["query", "header"]) {
            let paramDatalistEl = document.getElementById(
                inside + "-parameter-options"
            )
            paramDatalistEl.innerHTML = ""
            for (const param in params) {
                if (params[param].in === inside) {
                    let option = document.createElement("option")
                    option.value = param
                    option.text = param
                    option.title = params[param].description
                    paramDatalistEl.appendChild(option)
                }
            }
        }
        return callback(params)
    })
}

function onParamKeySet(event) {
    if (oaParams == null) {
        return
    }

    let [key, selectedOp] = splitKeyandOperator(event.target.value)
    let opEl = event.target.parentElement.getElementsByClassName("param-op")[0]
    // Use operator from key field before value in operator field
    if (selectedOp == "eq") {
        selectedOp = opEl.value
    }
    if (oaParams.hasOwnProperty(key)) {
        param = oaParams[key]
        event.target.title = param.description
        event.target.setCustomValidity("")

        opEl.innerHTML = ""
        opEl.dataset.key = key
        param.operators.forEach((operator) => {
            let option = document.createElement("option")
            option.value = operator.name
            option.text = OPERATORS[operator.name] || operator.name
            option.title = operator.description
            if (operator.name === selectedOp) {
                option.setAttribute("selected", "selected")
                event.target.value = key
            }
            opEl.appendChild(option)
        })
        opEl.dispatchEvent(new Event("change"))
    } else {
        opEl.innerHTML = ""
        let option = document.createElement("option")
        option.value = selectedOp
        option.text = OPERATORS[selectedOp] || selectedOp
        option.title = selectedOp
        option.setAttribute("selected", "selected")
        opEl.appendChild(option)
        event.target.value = key
        event.target.title = "onbekende parameter"
        event.target.setCustomValidity("onbekende parameter")
    }

    // Update infobubble
    event.target.parentElement.dispatchEvent(new Event("mouseenter"))

    // Make sure dummy setting is added
    if (
        !event.target.parentElement.nextElementSibling &&
        event.target.parentElement.parentElement
    ) {
        event.target.parentElement.parentElement.appendChild(
            createParamEl(null, null, "eq", true, param.in)
        )
    }
}

function parseJwt(token) {
    let base64Url = token.split(".")[1]
    let base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/")
    let jsonPayload = decodeURIComponent(
        atob(base64)
            .split("")
            .map(function (c) {
                return "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2)
            })
            .join("")
    )

    return JSON.parse(jsonPayload)
}

function onParamOpSet(event) {
    let key = event.target.dataset.key
    let op = event.target.value
    if (oaParams.hasOwnProperty(key)) {
        let param = oaParams[key]
        let opParam = param.operators.find((x) => x.name == event.target.value)
        event.target.title = opParam.description

        // Update value input type to match key and operator
        let oldValueEl =
            event.target.parentElement.getElementsByClassName("param-val")[0]
        let valueEl = document.createElement("input")
        valueEl.value = oldValueEl.value
        valueEl.placeholder = oldValueEl.placeholder
        valueEl.className = oldValueEl.className

        let type =
            opParam.schema.format ||
            opParam.schema.type ||
            param.schema.format ||
            param.schema.type
        if (opParam.schema.enum) {
            valueEl.setAttribute("list", `datalist-${key}[${op}]-enum`)
        }
        if (opParam.examples) {
            valueEl.setAttribute("list", `datalist-${key}[${op}]-examples`)
        }
        if (type == "date-time") {
            valueEl.type = "datetime-local"
        } else if (type == "date") {
            valueEl.type = "date"
        } else if (type == "integer") {
            valueEl.type = "number"
            valueEl.step = 1
        } else if (type == "boolean") {
            valueEl.setAttribute("list", "boolean")
        }
        oldValueEl.parentNode.replaceChild(valueEl, oldValueEl)
    }
}

function createParamEl(
    key = null,
    value = null,
    op = "eq",
    active = true,
    insideOf = "query"
) {
    // Create new parameter setting
    let paramEl = document.createElement("div")
    paramEl.className = "param"
    let activeEl = document.createElement("input")
    activeEl.type = "checkbox"
    activeEl.className = "param-check"
    activeEl.checked = active
    activeEl.onchange = (e) => {
        e.target.checked
            ? e.target.parentElement.classList.remove("disabled")
            : e.target.parentElement.classList.add("disabled")
    }
    paramEl.appendChild(activeEl)
    activeEl.dispatchEvent(new Event("change"))

    let keyEl = document.createElement("input")
    keyEl.className = "param-key"
    keyEl.setAttribute("list", insideOf + "-parameter-options")
    keyEl.placeholder = "select a parameter"
    keyEl.autocomplete = "off"
    keyEl.addEventListener("change", onParamKeySet)

    // Show complete datalist on focus if value is unknown parameter
    keyEl.onmouseover = (e) => {
        e.target.dispatchEvent(new Event("focus"))
        e.target.dataset.old = e.target.value
    }
    keyEl.onmousedown = (e) => {
        if (oaParams != null && !(e.target.value in oaParams)) {
            e.target.value = ""
        }
    }
    keyEl.onmouseup = (e) => {
        e.target.value = e.target.dataset.old
    }
    keyEl.onblur = (e) => {
        if (e.target.value == "") {
            e.target.value = e.target.dataset.old
        }
    }
    paramEl.appendChild(keyEl)

    let opEl = document.createElement("select")
    opEl.className = "param-op"
    let option = document.createElement("option")
    option.value = op
    option.textContent = OPERATORS[op] || op
    option.setAttribute("selected", "selected")
    opEl.innerHTML = ""
    opEl.appendChild(option)
    opEl.addEventListener("change", onParamOpSet)
    paramEl.appendChild(opEl)

    let valueEl = document.createElement("input")
    valueEl.className = "param-val"
    valueEl.placeholder = "enter a value"
    valueEl.value = value
    paramEl.appendChild(valueEl)

    let deleteEl = document.createElement("button")
    deleteEl.className = "remove-param-btn btn glyphicon glyphicon-trash"
    deleteEl.onclick = (e) => {
        e.target.parentElement.remove()
    }
    paramEl.appendChild(deleteEl)

    let infoEl = document.createElement("div")
    infoEl.className = "param-info hidden"
    infoEl.onclick = (e) => {
        e.target.classList.toggle("expand")
    }
    paramEl.appendChild(infoEl)
    paramEl.onmouseenter = (e) => setInfoBubble(e.target)

    if (oaParams == null) {
        paramEl.classList.add("loading")
    }
    if (key != null) {
        keyEl.value = key
        let event = new Event("change")
        keyEl.dispatchEvent(event)
    }
    return paramEl
}

function setInfoBubble(element) {
    let valueEl = element.getElementsByClassName("param-val")[0]
    let infoEl = element.getElementsByClassName("param-info")[0]
    if (valueEl && valueEl.value.startsWith("Bearer ")) {
        let token = parseJwt(valueEl.value)
        let isExpired = token.exp * 1000 < new Date().getTime()
        let minutesRemaining = Math.floor(
            (new Date(token.exp * 1000) - new Date()) / 60000
        )
        expiredText = `Exp:${minutesRemaining}min`
        summary = `${token.preferred_username} ${
            isExpired ? "Expired" : expiredText
        } `
        infoEl.innerHTML = `<div class="summary">${summary}</div>`
        infoEl.innerHTML += `<pre>${syntaxHighlight(
            JSON.stringify(token, null, 4)
        )}</pre>`
        infoEl.classList.remove("hidden")
    } else {
        infoEl.classList.add("hidden")
    }
}

function setHeaders(headers = null) {
    // Fill the header settings container
    let headersEl = document.getElementById("request-headers")
    headersEl.innerHTML = ""
    if (headers) {
        headers.forEach((header) => {
            headersEl.appendChild(
                createParamEl(
                    header.key,
                    header.value,
                    "eq",
                    header.active,
                    "header"
                )
            )
        })
    } else {
        for (key in DEFAULT_HEADERS) {
            headersEl.appendChild(
                createParamEl(key, DEFAULT_HEADERS[key], "eq", true, "header")
            )
        }
        let token = JSON.parse(window.localStorage.getItem("authToken"))
        if (token) {
            addSetting(
                "Authorization",
                "Bearer " + token.access_token,
                "eq",
                "header",
                false
            )
        }
    }

    headersEl.appendChild(createParamEl(null, null, "eq", true, "header"))
}

function setParams(params = null) {
    // Fill the parameter settings container
    let paramsEl = document.getElementById("request-params")
    paramsEl.appendChild(createParamEl())
    if (params == null) {
        for (let paramkey of PAGEURL.searchParams.keys()) {
            let value = PAGEURL.searchParams.get(paramkey)
            let [key, operator] = splitKeyandOperator(paramkey)
            addSetting(key, value, operator, (type = "param"))
        }
        params = getRequestSettings()
    }

    paramsEl.innerHTML = ""
    params.forEach((param) => {
        let active =
            (PAGEURL.searchParams.has(param.combinedKey) &&
                PAGEURL.searchParams.get(param.combinedKey) == param.value) ||
            param.key == ""
        paramsEl.appendChild(
            createParamEl(param.key, param.value, param.operator, active)
        )
    })

    paramsEl.appendChild(createParamEl())
}
