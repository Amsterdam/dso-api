// Format Dataset index JSON
// Show pretty HTML version of dataset index JSON.
//
// parameter: rawJson (index JSON)
// returns: HTML string

const FORMATTER = (rawJson) => {
    let datasetsEl = document.createElement("div")
    datasetsEl.className = "datasets"
    Object.keys(rawJson.datasets).forEach((datasetId) => {
        let dataset = rawJson.datasets[datasetId]
        let datasetEl = document.createElement("div")
        datasetEl.className = "dataset"
        datasetEl.style = "margin-bottom:30px"
        datasetEl.innerHTML = `
        <h3 class='dataset-name' style="text-transform: capitalize;">${dataset.service_name}</h3>
        <p class='dataset-description' style="width:80%; word-break: normal;">${dataset.description}</p>
        <p class='dataset-api-authentication'><b>Autorisatie</b>: ${dataset.api_authentication}</p>

      `
        let versions = dataset.versions
        let defaultVersion = dataset.default_version
        let urls = [
            { type: "API", url: dataset.environments[0].api_url },
            {
                type: "Documentation",
                url: dataset.environments[0].documentation_url,
            },
        ]
        if (dataset.related_apis) {
            urls = urls.concat(dataset.related_apis)
        }

        let urlsEl = document.createElement("div")
        urls.forEach((url) => {
            urlsEl.innerHTML += `<div><b>${url["type"]}:</b> <a href="${url["url"]}">${url["url"]}</a></div>`
        })
        datasetEl.appendChild(urlsEl)
        datasetsEl.appendChild(datasetEl)
    })
    return datasetsEl.innerHTML
}
