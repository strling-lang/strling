#!/usr/bin/env Rscript
# STRling R Binding Setup Script
# This script installs the required R dependencies for the R binding.

# Force locale to C to avoid warnings
Sys.setenv(LC_ALL = "C")

cat("Setting up STRling R binding dependencies...\n")

# Install packages into a writable user library instead of the system library.
user_lib <- Sys.getenv("R_LIBS_USER", unset = file.path(path.expand(Sys.getenv("HOME")), "R", paste0(R.version$platform, "-library"), paste0(R.version$major, ".", sub("\\.", "", R.version$minor))))
dir.create(user_lib, recursive = TRUE, showWarnings = FALSE)
Sys.setenv(R_LIBS_USER = user_lib)
.libPaths(c(user_lib, .libPaths()))

# Set CRAN mirror
options(repos = c(CRAN = Sys.getenv("CRAN", unset = "https://cloud.r-project.org")))

# Install required packages if not present
# Note: devtools is NOT required - we source R files directly in CI
packages <- c("testthat", "jsonlite")

for (pkg in packages) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    cat(sprintf("Installing %s...\n", pkg))
    result <- tryCatch(
      {
        install.packages(pkg, lib = user_lib)
        TRUE
      },
      error = function(e) {
        cat(sprintf("Error installing %s: %s\n", pkg, e$message))
        FALSE
      }
    )
    if (!result || !requireNamespace(pkg, quietly = TRUE)) {
      stop(sprintf("Failed to install required package: %s", pkg))
    }
  } else {
    cat(sprintf("%s is already installed.\n", pkg))
  }
}

cat("R binding setup complete.\n")
