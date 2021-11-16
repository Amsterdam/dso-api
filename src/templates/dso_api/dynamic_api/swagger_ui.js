  const swagger_settings  = {{settings|safe}}

const ui = SwaggerUIBundle({
  url: "{{schema_url|safe}}",
  dom_id: "#swagger-ui",
  presets: [
    SwaggerUIBundle.presets.apis,
  ],
  plugin: [
    SwaggerUIBundle.plugins.DownloadUrl
  ],
  layout: "BaseLayout",
  requestInterceptor: (request) => {
    request.headers["X-CSRFToken"] = "{{csrf_token}}"
    return request;
  },
  ...swagger_settings
})

// Show access token in swagger login screen
window.dsoShowToken = (token) => {
  let access_token = token.access_token
  let el =  document.getElementsByClassName("auth-container")[0].getElementsByClassName("wrapper")[0]
  el.innerHTML =`<div style="position:relative">
                    <label>access token</label>
                    <textarea rows=5 style="background-color:rgb(51,51,51); color:white; min-height:unset">${access_token}</textarea>
                    <div class="copy-to-clipboard" style="bottom: 15px; right: 20px;" onclick="navigator.clipboard.writeText('${access_token}')">
                      <button></button>
                    </div>
                  </div>`
}

/// Initiate Swagger UI with extra options.
ui.initOAuth({
    clientId: swagger_settings["clientId"],
    scopes: swagger_settings["scopes"]
})
