package = "strling"
version = "3.0.0-alpha-1"
source = {
   url = "git+https://github.com/strling-lang/strling.git",
   tag = "v3.0.0-alpha"
}
description = {
   summary = "A next-generation regex DSL compiler",
   detailed = [[
      STRling is a next-generation regex DSL compiler.
   ]],
   homepage = "https://github.com/strling-lang/strling",
   license = "MIT"
}
dependencies = {
   "lua >= 5.1",
   "lua-cjson"
}
build = {
   type = "builtin",
   modules = {
      strling = "src/strling.lua",
      ["strling.simply"] = "src/simply.lua"
   }
}
