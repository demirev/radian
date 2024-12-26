project_selector_ui <- function(id) {
	ns <- NS(id)
	
	tagList(
		tags$a(
			href = "#",
			class = "dropdown-toggle",
			`data-toggle` = "dropdown",
			icon("folder-open"),
			span(
				textOutput(ns("current_project_name"), inline = TRUE),
				class = "project-name"
			)
		),
		tags$ul(
			class = "dropdown-menu",
			tags$li(
				class = "header",
				"Projects"
			),
			tags$li(
				tags$ul(
					class = "menu",
					tags$li(
						actionLink(
							ns("new_project"),
							icon=icon("plus"),
							label="New Project"
						)
					),
					tags$li(
						class = "divider"
					),
					uiOutput(ns("project_list"))
				)
			)
		)
	)
}


project_selector_server <- function(id, api_url, tenant_id) {
	moduleServer(id, function(input, output, session) {
		# Reactive values
		selected_project <- reactiveVal(NULL)
		projects_list <- reactiveVal(NULL)
		
		# Fetch user's projects
		observe({
			req(session$userData$user)
			user_id <- session$userData$user$username
			
			response <- tryCatch({
				GET(
					glue("{api_url}/analysis/"),
					query = list(
						context_id = user_id,
						tenant_id = tenant_id()
					)
				)
			}, error = function(e) {
				shinyalert(
					"Error Loading Projects",
					"Unable to connect to the server. Please try again later.",
					type = "error"
				)
				return(NULL)
			})
			
			if (!is.null(response)) {
				if (status_code(response) == 200) {
					projects <- fromJSON(rawToChar(response$content))
					projects_list(projects)
				} else {
					error_msg <- tryCatch({
						content <- fromJSON(rawToChar(response$content))
						content$detail
					}, error = function(e) {
						"Unknown error occurred"
					})
					
					shinyalert(
						"Error Loading Projects",
						paste("Server error:", error_msg),
						type = "error"
					)
				}
			}
		})
		
		# Render project list
		output$project_list <- renderUI({
			req(projects_list())
			ns <- session$ns
			
			projects <- projects_list()
			
			tagList(
				map(seq_len(nrow(projects)), function(i) {
					tags$li(
						actionLink(
							ns(paste0("project_", projects$session_id[i])),
							HTML(paste0(
								tags$strong(projects$title[i] %||% projects$session_id[i]),
								tags$br(),
								tags$small(projects$description[i] %||% "")
							))
						)
					)
				})
			)
		})
		
		# Handle new project creation
		observeEvent(input$new_project, {
			showModal(modalDialog(
				title = "Create New Project",
				textInput(session$ns("new_project_title"), "Title (optional)"),
				textInput(session$ns("new_project_desc"), "Description (optional)"),
				footer = tagList(
					modalButton("Cancel"),
					actionButton(session$ns("create_project"), "Create")
				)
			))
		})
		
		# Create new project
		observeEvent(input$create_project, {
			req(session$userData$user)
			user_id <- session$userData$user$username
			
			# Show loading state
			shinyalert(
				"Creating Project",
				"Please wait...",
				type = "info",
				showConfirmButton = FALSE,
				timer = 0
			)
			
			response <- tryCatch({
				POST(
					glue("{api_url}/analysis/"),
					query = list(
						context_id = user_id,
						tenant_id = tenant_id(),
						title = input$new_project_title,
						description = input$new_project_desc
					)
				)
			}, error = function(e) {
        print(e)
				shinyalert(
					"Error Creating Project",
					"Unable to connect to the server. Please try again later.",
					type = "error"
				)
				return(NULL)
			})
			
			if (!is.null(response)) {
				if (status_code(response) == 200) {
					new_project <- fromJSON(rawToChar(response$content))
					selected_project(new_project)
					closeAlert()
					removeModal()
					shinyalert(
						"Success",
						"Project created successfully!",
						type = "success",
						timer = 2000,
						showConfirmButton = TRUE
					)
					projects_list(NULL)
				} else {
					error_msg <- tryCatch({
						content <- fromJSON(rawToChar(response$content))
						if (is.list(content) && !is.null(content$detail)) {
							if (is.character(content$detail)) {
								content$detail
							} else if (is.list(content$detail)) {
								# Handle validation errors which might be nested
								paste(sapply(content$detail, function(x) x$msg), collapse = "\n")
							}
						} else {
							"Unknown error occurred"
						}
					}, error = function(e) {
						"Unknown error occurred"
					})
					
					shinyalert(
						"Error Creating Project",
						paste("Server error:", error_msg),
						type = "error"
					)
				}
			} else {
				shinyalert(
					"Error Creating Project",
					"Something went wrong. Please try again later.",
					type = "error"
				)
			}
		})
		
		# Handle project selection
		observe({
			req(projects_list())
			projects <- projects_list()
			
			map(projects$session_id, function(sid) {
				observeEvent(input[[paste0("project_", sid)]], {
					response <- tryCatch({
						GET(
							glue("{api_url}/analysis/{sid}"),
							query = list(tenant_id = tenant_id())
						)
					}, error = function(e) {
						shinyalert(
							"Error Loading Project",
							"Unable to connect to the server. Please try again later.",
							type = "error"
						)
						return(NULL)
					})
					
					if (!is.null(response)) {
						if (status_code(response) == 200) {
							project <- fromJSON(rawToChar(response$content))
							selected_project(project)
						} else {
							error_msg <- tryCatch({
								content <- fromJSON(rawToChar(response$content))
								content$detail
							}, error = function(e) {
								"Unknown error occurred"
							})
							
							shinyalert(
								"Error Loading Project",
								paste("Server error:", error_msg),
								type = "error"
							)
						}
					}
				})
			})
		})
		
		# Show current project name
		output$current_project_name <- renderText({
			if (is.null(selected_project())) {
				"Select Project"
			} else {
				selected_project()$title %||% selected_project()$session_id
			}
		})
		
		# Return selected project
		return(selected_project)
	})
}
