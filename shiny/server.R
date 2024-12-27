server <- function(input, output, session) {
	# Set up authentication based on mode
	if (!is_local) {
		res_auth <- secure_server(
			check_credentials = check_credentials(envPass = envPass)
		)
		# Get user from secure authentication
		user <- reactive({ 
			req(res_auth$user)
			list(username = res_auth$user$user_name)
		})
	} else {
		# For local development, use a default test user
		user <- reactive({
			list(username = "test_user_id")
		})
	}
	
	# Create a reactive value for tenant_id
	tenant_id <- reactive({ "default" })
	
	observe({
		if (
			is.null(input$shinymanager_where) || 
			(!is.null(input$shinymanager_where) && 
			 input$shinymanager_where %in% "application")
		) {
			# Set the user data in the session
			session$userData$user <- user()
			
			selected_project <- project_selector_server(
		    "project_selector", api_url, tenant_id
			)
			
			conversation_server("conversation", selected_project, api_url, tenant_id)
			#data_server("data", selected_project, api_url, tenant_id)
			#environment_server("environment", selected_project, api_url, tenant_id)
			#notebook_server("notebook", selected_project, api_url, tenant_id)
		}
	})
}
