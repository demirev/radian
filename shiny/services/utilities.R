
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

#' Execute user code in a safe environment with a timeout,
#' capturing console output as a string.
#'
#' @param code A character string of R code to execute.
#' @param safe_env An environment to evaluate the code in
#'   (e.g., one that blocks unsafe functions).
#' @param timeout_secs Numeric. Number of seconds to allow before timing out.
#'
#' @return A character string containing all captured console output,
#'   or an error object if timed out or another error occurred.
#'
#' @examples
#' safe_env <- new.env(parent = baseenv())
#' safe_env$system <- function(...) stop("system() blocked")
#' code_str <- "cat('Hello'); x <- 1+1; print(x)"
#' result <- run_user_code(code_str, safe_env, 5)
#' if (inherits(result, "error")) {
#'   cat("Error occurred:\n", result$message, "\n")
#' } else {
#'   cat("Captured Output:\n", result)
#' }
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
    error = function(e) {
      out_e <- capture.output(e)
      out_e <- paste(out_e, collapse = "\n")
      out_e
    }
  )
  res
}

#' Execute user code in a safe environment with a timeout,
#' capturing console output AND any plots generated.
#'
#' @param code A character string of R code to execute.
#' @param safe_env An environment to evaluate the code in
#'   (e.g., one that blocks unsafe functions).
#' @param timeout_secs Numeric. Number of seconds to allow before timing out.
#' @param device One of "pdf" or "png". Which graphics device to use?
#'
#' @return A list with:
#'   \itemize{
#'     \item \code{console_output}: character string of everything printed
#'       to the console.
#'     \item \code{plots}: a list of raw byte vectors, each representing
#'       a plot file.
#'   }
#'   If an error or timeout occurs, returns an error object instead.
#'
#' @examples
#' safe_env <- new.env(parent = baseenv())
#' safe_env$system <- function(...) stop("system() blocked")
#'
#' user_code <- "
#'   cat('Hello from user code\\n')
#'   plot(1:10)
#'   hist(rnorm(100))
#' "
#'
#' result <- run_user_code_capture_plots(user_code, safe_env, timeout_secs = 5, device = "pdf")
#' if (inherits(result, "error")) {
#'   cat('An error occurred:', result$message, '\\n')
#' } else {
#'   cat('Console output:\\n', result$console_output, '\\n')
#'   cat('Number of plot files:', length(result$plots), '\\n')
#' }
run_user_code_capture_plots <- function(
  code,
  safe_env     = baseenv(),
  timeout_secs = 5,
  device       = c("pdf", "png")
) {
  device <- match.arg(device)
  
  # Wrap callr::r in a top-level tryCatch to handle errors/timeouts
  res <- tryCatch(
    callr::r(
      func = function(code, env, limit, dev_type) {
        # Create a temporary directory to store the plot files
        plot_dir <- tempfile("user_plots_")
        dir.create(plot_dir)
        
        # Decide how to capture the plots
        plot_file_pattern <- switch(
          dev_type,
          "pdf" = file.path(plot_dir, "plot_%03d.pdf"),
          "png" = file.path(plot_dir, "plot_%03d.png")
        )
        
        # Open the chosen device
        if (dev_type == "pdf") {
          # each page becomes a separate file: plot_001.pdf, plot_002.pdf, ...
          pdf(plot_file_pattern)
        } else if (dev_type == "png") {
          # each plot will overwrite the same file name unless we manually
          # open/close devices in user code, or do other advanced handling.
          # But at least "plot_%03d.png" might handle each new dev.new() call as separate pages.
          png(plot_file_pattern)
        }
        
        # Capture console output
        out_lines <- capture.output(
          R.utils::withTimeout(
            expr = eval(parse(text = code), envir = env),
            timeout   = limit,
            onTimeout = "error"
          )
        )
        
        # Close the graphics device
        dev.off()
        
        # Gather plot files
        file_pattern <- if (dev_type == "pdf") "\\.pdf$" else "\\.png$"
        plot_files <- list.files(
          plot_dir, pattern = file_pattern, full.names = TRUE
        )
        
        # Read each file as raw bytes
        # (Alternatively, you could base64-encode or convert them differently)
        plot_bytes <- lapply(plot_files, function(f) {
          readBin(f, what = "raw", n = file.info(f)$size)
        })
        
        # Return a list with console output + raw plot data
        list(
          console_output = paste(out_lines, collapse = "\n"),
          plots = plot_bytes
        )
      },
      args = list(code = code, env = safe_env, limit = timeout_secs, dev_type = device)
    ),
    error = function(e) {
      # Return the error object if anything goes wrong
      out_e <- capture.output(e)
      out_e <- paste(out_e, collapse = "\n")
      list(console_output = out_e, plots = NULL)
    }
  )
  
  res
}
