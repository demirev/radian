page_ui <- dashboardPage(
  #options = list(sidebarExpandOnHover = TRUE),
  skin = "black",
  header = dashboardHeader(
    title = "Radian",
    titleWidth = 300,
    tags$li(
      class = "dropdown",
      project_selector_ui("project_selector")
    ),
    tags$li(
      class = "dropdown navbar-custom-menu",
      tags$a(
        href = "#",
        class = "dropdown-toggle",
        `data-toggle` = "dropdown",
        icon("cog")
      ),
      tags$ul(
        class = "dropdown-menu",
        tags$li(
          delete_project_ui("delete_project")
        )
      )
    )
  ),
  sidebar = dashboardSidebar(
    disable = TRUE,
    width = 0,
    collapsed = TRUE,
    minified = FALSE
  ),
  body = dashboardBody(
    tags$script(HTML("
      $(document).on('click', '.dropdown-menu', function (e) {
        e.stopPropagation();
      });
    ")),
    tags$style(
      type = "text/css",
      ".shiny-output-error { visibility: hidden; }",
      ".shiny-output-error:before { visibility: hidden; }",
      ".sidebar-collapse .main-sidebar { display: none !important; }"
    ),
    #shinyDashboardThemes(
    #  theme = 'grey_light' # c('blue_gradient','flat_red','grey_light','grey_dark','onenote','poor_mans_flatly','purple_gradient')
    #),
    tags$head(
      tags$link(rel = "stylesheet", type = "text/css", href = "radian.css"),
      tags$link(rel = "shortcut icon", href = "radian_logo_positiv_symbol.svg")
    ),
    autoWaiter(
      color = "#3498db",
      html = spin_three_bounce()
    ),
    waiterPreloader(
      color = "#3498db",
      html = spin_three_bounce()
    ),
    useShinyalert(),
    shinyjs::useShinyjs(),
    disconnectMessage(
      text = "Session has been disconnected. Please refresh the page to reconnect.",
      refresh = "Refresh",
      width = "full",
      top = "center",
      size = 22,
      background = "#f5f7fa",
      colour = "#2c3e50",
      overlayColour = "#2c3e50",
      overlayOpacity = 0.9,
      refreshColour = "#3498db"
    ),
    shinybrowser::detect(),
    fluidRow(
      column(
        4,
        conversation_ui("conversation")
      ),
      column(8)
    )
  ),
  controlbar = NULL,
  footer = dashboardFooter(
    left = "georgi[underscore]demirev[at]proton[dot]me",
    right = glue("https://github.com/demirev/radian")
  ),
  title = "Radian"
)

ui <- if (is_local) {
  page_ui
} else {
  secure_app(
    id = "auth",
    head_auth = list(
      tags$title("radian"),
      tags$head()
    ),
    fab_position = "none",
    ui = page_ui
  )
}
  
ui
