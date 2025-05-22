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
                const { header, ...urls } = version
                return (
                    result +
                    `<h4 class='dataset-version'>${header}</h4>` +
                    createLinksForVersion(urls)
                )
            },
            ""
        )
        datasetEl.innerHTML += linksForAllVersions
        datasetsEl.appendChild(datasetEl)
    })
    return datasetsEl.innerHTML
}

const KEYMAP = {
    doc_url: "Documentation",
    api_url: "REST API",
    wfs_url: "WFS",
    mvt_url: "MVT",
}

const createLinksForVersion = (urls) => {
    return Object.entries(urls)
        .map(([key, value]) =>
            key in KEYMAP
                ? `<div><b>${KEYMAP[key]}:</b> <a href="${value}">${value}</a></div>`
                : ""
        )
        .join("")
}
