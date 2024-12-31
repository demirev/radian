create_safe_env <- function(
    packages = c(
      "dplyr", "ggplot2", "lubridate", "purrr",
      "readr", "stringr", "tidyr", 
      "MASS", "caret", "e1071", "rpart",
      "randomForest", "xgboost", "glmnet", "nnet",
      "tidymodels", "recipes", "parsnip", "yardstick",
      "tune", "workflows", "tibble", "tibbletime",
      "tsibble", "tsibbledata",# "tsibbletalk", "tsibbletools",
      "prophet", "forecast", "fable", "fabletools",
      "magrittr", "rlang",
      "kableExtra", "knitr", "rmarkdown"
    )
) {
  # Start from base R environment
  safe_env <- new.env(parent = baseenv())
  
  # For each package, copy *exported* functions into `safe_env`
  for (pkg in packages) {
    # Make sure the package is loaded
    if (!requireNamespace(pkg, quietly = TRUE)) {
      stop(paste("Package", pkg, "is not installed."))
    }
    exports <- getNamespaceExports(pkg)
    for (nm in exports) {
      safe_env[[nm]] <- get(nm, envir = asNamespace(pkg))
    }
  }
  
  # Block or override functions deemed unsafe:
  safe_env$system <- function(...) {
    stop("system() is blocked in this environment.")
  }
  safe_env$shell <- function(...) {
    stop("shell() is blocked in this environment.")
  }
  safe_env$library <- function(...) {
    stop("library() is blocked in this environment.")
  }
  safe_env$require <- function(...) {
    stop("require() is blocked in this environment.")
  }
  safe_env$install
  
  safe_env
}

run_user_code <- function(code, safe_env = baseenv(), timeout_secs = 5) {
  # We wrap callr::r in a tryCatch to handle errors/timeouts gracefully
  res <- tryCatch(
    callr::r(
      func = function(code, env, limit) {
        # Capture console output as a character vector
        out_lines <- capture.output(
          R.utils::withTimeout(
            expr = eval(parse(text = code), envir = env),
            timeout   = limit,
            onTimeout = "error"
          )
        )
        # Combine into one string
        paste(out_lines, collapse = "\n")
      },
      args = list(code = code, env = safe_env, limit = timeout_secs)
    ),
    error = function(e) e  # Return error object on failure
  )
  res
}