conversation_ui <- function(id) {
	ns <- NS(id)
	
	tagList(
		div(
			id = ns("no_project_message"),
			class = "no-project-message",
			icon("comments"),
			tags$p("Select a project to start chatting"),
			style = "text-align: center; padding: 2rem; color: #666;"
		),
		
		div(
			id = ns("chat_wrapper"),
			style = "display: none;",
			
			div(
				id = ns("message_container"),
				class = "message-container",
				uiOutput(ns("messages"))
			),
			div(
				class = "message-input-container",
				textAreaInput(
					ns("message_input"),
					label = NULL,
					placeholder = "Type your message...",
					resize = "vertical",
					width = "100%"
				),
				actionButton(
					ns("send_message"),
					"Send",
					icon = icon("paper-plane"),
					class = "btn-primary"
				)
			)
		)
	)
}

conversation_server <- function(id, selected_project, api_url, tenant_id) {
	moduleServer(id, function(input, output, session) {
		ns <- session$ns
		
		# Watch for project selection
		observe({
			if (!is.null(selected_project())) {
				runjs(sprintf("
					document.getElementById('%s').style.display = 'none';
					document.getElementById('%s').style.display = 'block';
				", ns("no_project_message"), ns("chat_wrapper")))
			} else {
				runjs(sprintf("
					document.getElementById('%s').style.display = 'block';
					document.getElementById('%s').style.display = 'none';
				", ns("no_project_message"), ns("chat_wrapper")))
				
				# Reset state when no project selected
				messages(NULL)
				pending_messages(list())
				last_timestamp(NULL)
				last_message_id(NULL)
			}
		})
		
		# Reactive values
		messages <- reactiveVal(NULL)
		pending_messages <- reactiveVal(list())
		last_timestamp <- reactiveVal(NULL)
		last_message_id <- reactiveVal(NULL)
		
		# Load initial messages when project changes
		observe({
		  cat("Observer 1 hit. ", "\n")
			req(selected_project())
			session_id <- selected_project()$session_id
			
			# Reset state
			messages(NULL)
			pending_messages(list())
			last_timestamp(NULL)
			last_message_id(NULL)
			
			# Load messages
			isolate(load_messages(session_id))
		})
		
		# Function to load messages
		load_messages <- function(
      session_id, 
      since_timestamp = NULL, 
      since_message_id = NULL
    ) {
		  cat("load_messages hit. ", "\n")
			response <- tryCatch({
				GET(
					glue("{api_url}/analysis/{session_id}/messages"),
					query = list(
						tenant_id = tenant_id(),
						since_timestamp = since_timestamp,
							since_message_id = since_message_id
					)
				)
			}, error = function(e) {
				showNotification(
					"Error loading messages",
					type = "error"
				)
				return(NULL)
			})
			
			if (!is.null(response) && status_code(response) == 200) {
				new_messages <- fromJSON(rawToChar(response$content))
				if (length(new_messages) > 0) {
					# Update messages
					if (is.null(messages())) {
						messages(new_messages)
					} else {
						messages(rbind(messages(), new_messages))
					}
					
					# Only update tracking if we're not doing an initial load
					if (!is.null(since_timestamp) || !is.null(since_message_id)) {
						last_timestamp(max(new_messages$timestamp))
						last_message_id(new_messages$message_id[length(new_messages$message_id)])
					} else {
						# For initial load, just set the timestamp once
						if (is.null(last_timestamp())) {
							last_timestamp(max(new_messages$timestamp))
							last_message_id(new_messages$message_id[length(new_messages$message_id)])
						}
					}
				}
			}
		}
		
		# Check message statuses
		check_pending_messages <- function() {
		  cat("check_pending_messages hit. ", "\n")
			req(selected_project(), length(pending_messages()) > 0)
			session_id <- selected_project()$session_id
			
			response <- tryCatch({
				GET(
					glue("{api_url}/analysis/{session_id}/messages/status"),
					query = list(
						tenant_id = tenant_id(),
						message_ids = I(names(pending_messages()))
					)
				)
			}, error = function(e) {
				return(NULL)
			})
			
			if (!is.null(response) && status_code(response) == 200) {
				statuses <- fromJSON(rawToChar(response$content))
				
				# Check for not_pending messages
				if (length(statuses) != 0) {
				  not_pending <- names(statuses)[sapply(statuses, function(x) x$status != "pending")]
				} else {
				  not_pending <- character(0)
				}
				
				if (length(not_pending) > 0) {
					# Remove from pending
					current_pending <- pending_messages()
					current_pending[not_pending] <- NULL
					pending_messages(current_pending)
					
					# Load new messages
					load_messages(session_id, since_message_id = last_message_id())
				}
			}
		}
		
		# Polling mechanism
		observe({
		  cat("Observer 2 hit. ", "\n")
			req(selected_project(), length(pending_messages()) > 0)
			
			# Determine polling interval based on oldest pending message
			oldest_pending <- min(sapply(pending_messages(), function(x) x$timestamp))
			time_diff <- difftime(Sys.time(), oldest_pending, units = "secs")
			
			if (time_diff < 10) {
				interval <- 500
			} else if (time_diff < 30) {
				interval <- 1000
			} else {
				interval <- 3000
			}
			
			if (length(pending_messages()) > 0) {
				invalidateLater(interval)
			  check_pending_messages()
			}
		})
		
		# Background polling for new messages
		observe({
		  cat("Observer 3 hit. ", "\n")
			req(selected_project(), !is.null(last_timestamp()))
			invalidateLater(10000) # once every 10 seconds
			
			isolate({
				current_timestamp <- last_timestamp()
				load_messages(
					selected_project()$session_id,
					since_timestamp = current_timestamp
				)
			})
		})
		
		# Send message
		observeEvent(input$send_message, {
		  cat("Observer 4 hit. ", "\n")
			req(selected_project(), input$message_input)
			session_id <- selected_project()$session_id
			message_text <- input$message_input
			
			# Clear input
			updateTextAreaInput(session, "message_input", value = "")
			
			response <- tryCatch({
				POST(
					glue("{api_url}/analysis/{session_id}/messages"),
					query = list(
						tenant_id = tenant_id(),
						message = message_text
					)
				)
			}, error = function(e) {
				showNotification(
					"Error sending message",
					type = "error"
				)
				return(NULL)
			})
			
			if (!is.null(response) && status_code(response) == 200) {
				result <- fromJSON(rawToChar(response$content))
				# Add to pending messages
				current_pending <- pending_messages()
				current_pending[[result$task_id]] <- list(
					timestamp = Sys.time()
				)
				pending_messages(current_pending)
			}
		})
		
		# Render messages
		output$messages <- renderUI({
			req(messages())
			
			# Create message list
			msg_list <- tagList(
				map(seq_len(nrow(messages())), function(i) {
					msg <- messages()[i,]
					is_user <- msg$role == "user"
					
					div(
						class = paste0(
							"message ",
							if (is_user) "message-user" else "message-assistant"
						),
						div(
							class = "message-content",
							HTML(markdown::markdownToHTML(
								text = msg$content,
								fragment.only = TRUE
							))
						),
						div(
							class = "message-timestamp",
							format(as_datetime(msg$timestamp), "%H:%M:%S")
						)
					)
				})
			)
			
			# Add auto-scroll after rendering
			runjs("
				setTimeout(function() {
					var container = document.getElementById('conversation-message_container');
					if (container) {
						container.scrollTop = container.scrollHeight;
					}
				}, 100);
			")
			
			msg_list
		})
		
		# Return messages for other modules
		return(messages)
	})
}
