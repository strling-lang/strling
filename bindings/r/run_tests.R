
Sys.setenv(LC_ALL='C')
cat("START\n")
tryCatch({
  devtools::load_all(quiet=FALSE)
  cat("LOADED\n")
  
  res <- testthat::test_dir('tests/testthat', reporter=c('summary'), stop_on_failure=FALSE)
  df <- as.data.frame(res)
  
  cat(sprintf('[ FAIL %d | WARN %d | SKIP %d | PASS %d ]\n', 
              sum(df$failed), sum(df$warning), sum(df$skipped), sum(df$passed)))
}, error = function(e) {
  cat("ERROR: ", e$message, "\n")
  quit(status = 1)
})
