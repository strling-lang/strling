#!/usr/bin/env Rscript
# STRling R Binding Setup Script
# This script installs the required R dependencies for the R binding.

cat("Setting up STRling R binding dependencies...\n")

# Set CRAN mirror
options(repos = c(CRAN = "https://cloud.r-project.org"))

# Install required packages if not present
packages <- c("testthat", "devtools", "jsonlite")

for (pkg in packages) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    cat(sprintf("Installing %s...\n", pkg))
    result <- tryCatch(
      {
        install.packages(pkg)
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
