server <- function(input, output, session) {
	res_auth <- secure_server(
		check_credentials = check_credentials(envPass = envPass)
	)
	
	# Create a reactive value for tenant_id
	tenant_id <- reactive({ input$global_tenant_id })
	
	observe({
		if (
			is.null(input$shinymanager_where) || 
			(!is.null(input$shinymanager_where) && 
			 input$shinymanager_where %in% "application")
		) {
			
			selected_project <- project_selector_server("project_selector", api_url, tenant_id)
			
			conversation_server("conversation", selected_project, api_url, tenant_id)
			data_server("data", selected_project, api_url, tenant_id)
			environment_server("environment", selected_project, api_url, tenant_id)
			notebook_server("notebook", selected_project, api_url, tenant_id)
			
		}
	})
}
