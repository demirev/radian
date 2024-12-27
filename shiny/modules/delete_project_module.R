delete_project_ui <- function(id) {
	ns <- NS(id)
	actionLink(ns("delete_project"), 
		label = tagList(
			icon("trash"), 
			"Delete Project"
		),
		class = "text-danger"
	)
}


delete_project_server <- function(id, selected_project, api_url, tenant_id) {
	moduleServer(id, function(input, output, session) {
		# Observe delete project button click
		observeEvent(input$delete_project, {
			req(selected_project())
			
			showModal(modalDialog(
				title = "Delete Project",
				"Are you sure you want to delete this project? This action cannot be undone.",
				footer = tagList(
					modalButton("Cancel"),
					actionButton(
						session$ns("confirm_delete"),
						"Delete",
						class = "btn-danger"
					)
				)
			))
		})
		
		# Handle project deletion confirmation
		observeEvent(input$confirm_delete, {
			req(selected_project())
			session_id <- selected_project()$session_id
			
			# Show loading state
			shinyalert(
				"Deleting Project",
				"Please wait...",
				type = "info",
				showConfirmButton = FALSE,
				timer = 0
			)
			
			response <- tryCatch({
				DELETE(
					glue("{api_url}/analysis/{session_id}"),
					query = list(tenant_id = tenant_id())
				)
			}, error = function(e) {
				shinyalert(
					"Error Deleting Project",
					"Unable to connect to the server. Please try again later.",
					type = "error"
				)
				return(NULL)
			})
			
			if (!is.null(response)) {
				if (status_code(response) == 200) {
					selected_project(NULL)
				  closeAlert()
					removeModal()
					shinyalert(
						"Success",
						"Project deleted successfully!",
						type = "success",
						timer = 2000,
						showConfirmButton = TRUE
					)
				} else {
					error_msg <- tryCatch({
						content <- fromJSON(rawToChar(response$content))
						content$detail
					}, error = function(e) {
						"Unknown error occurred"
					})
					
					shinyalert(
						"Error Deleting Project",
						paste("Server error:", error_msg),
						type = "error"
					)
				}
			}
		})
	})
}
