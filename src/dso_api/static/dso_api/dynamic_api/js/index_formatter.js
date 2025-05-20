// Format Dataset index JSON
// Show pretty HTML version of dataset index JSON.
//
// parameter: rawJson (index JSON)
// returns: HTML string

const FORMATTER = (rawJson) => {
    const datasetsEl = document.createElement("div")
    datasetsEl.className = "datasets"
    Object.keys(rawJson.datasets).forEach((datasetId) => {
        const dataset = rawJson.datasets[datasetId]
        const datasetEl = document.createElement("div")
        datasetEl.className = "dataset"
        datasetEl.style = "margin-bottom:30px"
        datasetEl.innerHTML = `
        <h3 class='dataset-name' style="text-transform: capitalize;">${dataset.service_name}</h3>
        <p class='dataset-description' style="width:80%; word-break: normal;">${dataset.description}</p>
        <p class='dataset-api-authentication'><b>Autorisatie</b>: ${dataset.api_authentication}</p>`
        const linksForAllVersions = dataset.versions.reduce(
            (result, version) => {
                return (
                    result +
                    `<h4 class='dataset-version'>${version.header}</h4>` +
                    createLinksForVersion(version)
                )
            },
            ""
        )
        datasetEl.innerHTML += linksForAllVersions
        datasetsEl.appendChild(datasetEl)
    })
    return datasetsEl.innerHTML
}

const createLinksForVersion = (version) => {
    return `
        <div>
            <div><b>API:</b> <a href="${version.api_url}">${
        version.api_url
    }</a></div>
            <div><b>Documentation:</b> <a href="${version.documentation_url}">${
        version.documentation_url
    }</a></div>
            ${
                version.mvt_url
                    ? `<div><b>MVT:</b> <a href="${version.mvt_url}">${version.mvt_url}</a></div>`
                    : ""
            }
            ${
                version.wfs_url
                    ? `<div><b>WFS:</b> <a href="${version.wfs_url}">${version.wfs_url}</a></div>`
                    : ""
            }

        </div>
    `
}
