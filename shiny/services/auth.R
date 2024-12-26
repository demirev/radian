check_credentials <- function(envPass = NULL) {
  test_user = "radian"
  if (is.null(envPass)) {
    stop("Please provide a password")
  }
  function(user, password) {
    if (user == test_user & password == "gggHHH123...") { # TODO: change this to a more secure password
      list(
        result = TRUE,
        user_id = 1,
        user_name = "test_user_id"
      )
    } else {
      list(
        result = FALSE
      )
    }
  }
}