// Format OpenAPI Specification
// Show summary of OpenAPI Spec, in html with links to docs and endpoints.
//
// parameter: rawJson (OpenAPI specification JSON)
// returns: HTML string

function getDefaultVersion(versions) {
    return Object.entries(versions).reduce((defaultVersion, [version, obj]) => {
        if(obj.default && version !== "default") {
            return version
        }
        return defaultVersion
    }, {})
}

function getVersionWarning(versions, currentVersion, defaultVersion) {
    // Show a warning for the unversioned path
    if (currentVersion === "default") {
        return "Waarschuwing: Dit is een ongeversioneerde API waarin brekende aanpassingen mogelijk zijn. Stap zo snel mogelijk over naar een stabiele geversioneerde versie van deze API."
    } else if (currentVersion !== defaultVersion) {
        switch (versions[currentVersion].status) {
            case "under_development":
                return "Waarschuwing: deze versie van de API is nog in ontwikkeling en niet stabiel. Niet gebruiken in productie-omgevingen. De dienstverlening kan onderbroken worden en brekende aanpassingen zijn mogelijk."
            case "superseded":
                return `Waarschuwing: deze versie van de API is verouderd en wordt niet aanbevolen voor nieuwe connecties. Support voor deze versie eindigt op ${versions[currentVersion].endSupportDate}. Stap voor die datum over op een nieuwe versie.`
        }
    }
}

const FORMATTER = (rawJson) => {
    let openApiEl = document.createElement("div")
    let requestPath = window.location.pathname
    if (requestPath.endsWith("/")) {
        requestPath = requestPath.slice(0, -1)
    }
    let versions = rawJson["x-versions"]
    let currentVMajor = requestPath.match(/v[0-9]$/)
    let defaultVersion = getDefaultVersion(versions)
    currentVMajor = currentVMajor ? currentVMajor.toString() : "default"
    let versionWarning = getVersionWarning(versions, currentVMajor, defaultVersion)
    let currentVersion = versions[currentVMajor]

    openApiEl.innerHTML = `
      <h3>OpenAPI ${rawJson.info.title}</h3>
      <b>Huidige versie</b>
      <p>
        <div style="display:inline-block;">${currentVMajor === "default" ? `Ongeversioneerd (${defaultVersion})` : `Versie ${currentVMajor}`}</div>&emsp;
        <a href="${currentVersion.url}">${currentVersion.url}</a> (${currentVersion.statusDescription})
      </p>
      ${versionWarning ? `<div class="dataset-version-alert">${versionWarning}</div>` : ""}
      <b>Alternatieve versies</b>
      ${Object.entries(rawJson["x-versions"])
        .filter(([version, obj]) => (version !== "default" && version !== currentVMajor))
          .map(([version, obj]) => {
            return `
              <p>
                <div style="display:inline-block;">Versie ${version}:</div>&emsp;
                <a href="${obj.url}">${obj.url}</a> (${obj.statusDescription})
              </p>`
          })
          .join("")}
      <p><dt>OpenAPI version</dt> <dd>${rawJson.openapi}</dd></p>
      <p>
        <dt>${rawJson.externalDocs.description}</dt>
        <dd><a href="${
            rawJson.externalDocs.url
        }" style="display:inline-block">${rawJson.externalDocs.url}</a></dd>
      </p>
      <h3>Paths:</h3>
    `

    // Add a link for each path
    let pathsEl = document.createElement("div")
    pathsEl.className = "paths"
    pathsEl.style = "padding-left: 10px;"
    Object.keys(rawJson.paths).forEach((path) => {
        Object.keys(rawJson.paths[path]).forEach((method) => {
            let endpointEl = document.createElement("div")
            endpointEl.className = "endpoint"

            endpointEl.innerHTML = `
          <p>
            <div class='request-method get' style="display:inline-block">${method}</div>
            <a href="${requestPath}${path}" style="display:inline-block" class='path'>${path}</a>
          </p>
        `
            pathsEl.appendChild(endpointEl)
        })
    })
    openApiEl.appendChild(pathsEl)

    return openApiEl.innerHTML
}
