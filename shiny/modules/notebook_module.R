library(shiny)
library(shinyAce)
library(jsonlite)
library(glue)
library(shinyjs)


notebook_ui <- function(id) {
  ns <- NS(id)
  
  div(
    id = ns("notebook_wrapper"),
    style = "display: none;",  # Hidden by default
    useShinyjs(),
    
    div(
      class = "notebook-container",
      tags$script(HTML("
        Shiny.addCustomMessageHandler('scrollToBottom', function(message) {
          var container = document.querySelector(message.selector);
          if (container) {
            container.scrollTop = container.scrollHeight;
          }
        });
      ")),
      
      # Environment controls
      div(
        class = "environment-controls",
        div(
          class = "env-status",
          textOutput(ns("env_status"))
        ),
        div(
          actionButton(
            ns("save_env"),
            "Save Environment",
            icon = icon("save"),
            class = "btn-icon"
          )
        )
      ),
      
      # Execution history
      div(
        class = "execution-history",
        uiOutput(ns("history"))
      ),
      
      # Code editor
      div(
        class = "code-editor-container",
        aceEditor(
          ns("code_editor"),
          mode = "r",
          theme = "chrome",
          height = "150px",
          fontSize = 14,
          tabSize = 2,
          useSoftTabs = TRUE,
          showPrintMargin = FALSE,
          showLineNumbers = TRUE,
          highlightActiveLine = TRUE
        ),
        div(
          style = "text-align: right; margin-top: 10px;",
          actionButton(
            ns("execute_code"),
            "Execute",
            icon = icon("play"),
            class = "btn-primary"
          )
        )
      )
    )
  )
}


notebook_server <- function(id, selected_project, api_url, tenant_id) {
  moduleServer(id, function(input, output, session) {
    ns <- session$ns
    
    # Reactive values for state management
    rv <- reactiveValues(
      history = list(),
      env_saved = TRUE,
      execution_count = 0,
      is_executing = FALSE
    )
    
    # Initialize safe environment
    safe_env <- reactiveValues(
      env = create_safe_env()
    )
    
    # Load environment if it exists
    observe({
      req(selected_project())
      
      tryCatch({
        response <- httr::GET(
          glue("{api_url}/environments/{selected_project()$session_id}"),
          query = list(tenant_id = tenant_id())
        )
        
        if (httr::status_code(response) == 200) {
          env_data <- httr::content(response)
          if (!is.null(env_data$env_file)) {
            # Load environment from base64 encoded RDS
            env_raw <- base64enc::base64decode(env_data$env_file)
            safe_env$env <- unserialize(env_raw)
            rv$env_saved <- TRUE
          }
        }
      }, error = function(e) {
        warning("Failed to load environment: ", e$message)
      })
    })
    
    # Save environment function
    save_environment <- function(auto = FALSE) {
      req(selected_project())
      
      # Serialize environment to base64
      env_raw <- serialize(safe_env$env, NULL)
      env_base64 <- base64enc::base64encode(env_raw)
      
      # Prepare payload
      payload <- list(
        session_id = selected_project()$session_id,
        context_id = selected_project()$context_id,
        env_file = env_base64
      )
      
      # Send to server
      tryCatch({
        response <- httr::PUT(
          glue("{api_url}/environments/{selected_project()$session_id}"),
          query = list(tenant_id = tenant_id()),
          body = payload,
          encode = "json"
        )
        
        if (httr::status_code(response) == 200) {
          rv$env_saved <- TRUE
          if (!auto) {
            showNotification("Environment saved successfully", type = "message")
          }
        }
      }, error = function(e) {
        warning("Failed to save environment: ", e$message)
        if (!auto) {
          showNotification("Failed to save environment", type = "error")
        }
      })
    }
    
    # Execute code
    observeEvent(input$execute_code, {
      code <- input$code_editor
      if (nchar(code) == 0) return()
      
      # Set executing state
      rv$is_executing <- TRUE
      
      # Disable UI elements
      shinyjs::disable("execute_code")
      shinyjs::disable("code_editor")
      shinyjs::disable("save_env")
      
      updateActionButton(session, "execute_code",
        label = "Executing...",
        icon = icon("spinner", class = "fa-spin")
      )
      
      # Execute code with plot capture
      result <- run_user_code_capture_plots(code, safe_env$env, device = "png")
      
      # update env
      if (!is.null(result$updated_env)) {
        list2env(result$updated_env, envir = safe_env$env)
      }
      
      # Add to history
      rv$history[[length(rv$history) + 1]] <- list(
        type = "user",
        input = code,
        output = if (inherits(result, "error")) {
          result$message
        } else {
          result$console_output
        },
        plots = if (!inherits(result, "error")) result$plots else NULL,
        status = if (inherits(result, "error")) "error" else "success",
        timestamp = Sys.time(),
        count = rv$execution_count
      )
      
      # Reset UI state
      rv$is_executing <- FALSE
      shinyjs::enable("execute_code")
      shinyjs::enable("code_editor")
      shinyjs::enable("save_env")
      updateActionButton(session, "execute_code",
        label = "Execute",
        icon = icon("play")
      )
      
      # Clear editor
      updateAceEditor(session, "code_editor", value = "")
      
      # Mark environment as unsaved
      rv$env_saved <- FALSE
      
      # Auto-save if enabled
      # save_environment(auto = TRUE)
    })
    
    # Manual environment save
    observeEvent(input$save_env, {
      save_environment(auto = FALSE)
    })
    
    # Environment status display
    output$env_status <- renderText({
      if (rv$env_saved) {
        "Environment: Saved"
      } else {
        "Environment: Unsaved changes"
      }
    })
    
    # Render execution history
    output$history <- renderUI({
      req(length(rv$history) > 0)
      
      lapply(rv$history, function(item) {
        div(
          class = paste("code-pair", item$type),
          # Input
          div(
            class = "code-input",
            tags$pre(
              tags$code(
                class = "language-r",
                paste0("In[", item$count, "]: ", item$input)
              )
            )
          ),
          # Output
          div(
            class = "code-output",
            # Console output
            if (!is.null(item$output) && nchar(item$output) > 0) {
              tags$pre(
                tags$code(item$output)
              )
            },
            # Plots
            if (!is.null(item$plots) && length(item$plots) > 0) {
              div(
                class = "plot-container",
                lapply(seq_along(item$plots), function(i) {
                  plotId <- paste0(ns(paste0("plot_", item$count, "_", i)))
                  div(
                    class = "plot-wrapper",
                    # Create a unique ID for each plot
                    img(
                      id = plotId,
                      src = sprintf("data:image/png;base64,%s",
                        base64enc::base64encode(item$plots[[i]])
                      ),
                      class = "plot-image"
                    )
                  )
                })
              )
            },
            # Meta information
            div(
              class = "execution-meta",
              span(
                class = paste("execution-badge", paste0("badge-", item$type)),
                if(item$type == "agent") icon("robot") else icon("user"),
                if(item$type == "agent") "Assistant" else "User"
              ),
              span(
                class = paste("execution-status", paste0("status-", item$status)),
                item$status
              ),
              div(
                class = "code-timestamp",
                format(item$timestamp, "%Y-%m-%d %H:%M:%S")
              )
            )
          )
        )
      })
    })
    
    # Auto-scroll to bottom after new execution
    observeEvent(rv$history, {
      # Use JavaScript to scroll to bottom
      session$sendCustomMessage(
        type = "scrollToBottom",
        message = list(selector = ".execution-history")
      )
    })
    
    # Watch for project selection
    observe({
      if (!is.null(selected_project())) {
        runjs(sprintf("document.getElementById('%s').style.display = 'block';",
          ns("notebook_wrapper")
        ))
      } else {
        runjs(sprintf("document.getElementById('%s').style.display = 'none';",
          ns("notebook_wrapper")
        ))
        
        # Reset state when no project selected
        rv$history <- list()
        rv$env_saved <- TRUE
        rv$execution_count <- 0
        rv$is_executing <- FALSE
      }
    })
  })
}
