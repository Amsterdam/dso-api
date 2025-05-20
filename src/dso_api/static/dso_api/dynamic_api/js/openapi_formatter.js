// Format OpenAPI Specification
// Show summary of OpenAPI Spec, in html with links to docs and endpoints.
//
// parameter: rawJson (OpenAPI specification JSON)
// returns: HTML string

const FORMATTER = (rawJson) => {
    let openApiEl = document.createElement("div")
    let requestPath = window.location.pathname
    if (requestPath.endsWith("/")) {
        requestPath = requestPath.slice(0, -1)
    }
    openApiEl.innerHTML = `
      <h3>OpenAPI ${rawJson.info.title}</h3>
      <p><dt>OpenAPI version</dt> <dd>${rawJson.openapi}</dd></p>
      <p>
        <dt>${rawJson.externalDocs.description}</dt>
        <dd><a href="${rawJson.externalDocs.url}" style="display:inline-block">${rawJson.externalDocs.url}</a></dd>
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
