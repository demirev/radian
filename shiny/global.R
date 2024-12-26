library(shiny)
library(shinyjs)
library(httr)
library(shinydashboard)
library(shinymanager) # for authentication
library(shinydashboard)
library(shinydashboardPlus) # https://rinterface.github.io/shinydashboardPlus
library(dashboardthemes) # https://github.com/nik01010/dashboardthemes
library(shinyalert) # https://github.com/daattali/shinyalert/
library(shinydisconnect) # https://github.com/daattali/shinydisconnect/
library(shinybrowser) # remotes::install_github("daattali/shinybrowser")
library(waiter) # https://shiny.john-coene.com/waiter/
library(htmltools)
library(readr)
library(dplyr)
library(purrr)
library(tidyr)
library(stringr)
library(lubridate)
library(DT)
library(RCurl)
library(jsonlite)
library(glue)

source("services/auth.R")
source("services/utilities.R")

source("modules/conversation_module.R")
source("modules/notebook_module.R")
source("modules/environment_module.R")
source("modules/data_module.R")
source("modules/project_selector_module.R")

is_local <- (Sys.getenv("SHINY_PORT") == "")
envPass <- Sys.getenv("CRUDPASSWORD") # not used yet

api_url <- if (is_local) {
  "http://localhost:8000"
} else {
  "http://radian:8000" # image name since we are running in docker-compose
}