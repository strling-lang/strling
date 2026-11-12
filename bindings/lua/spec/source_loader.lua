-- Keep component tests bound to the actual checkout's production module.
local helper_source = debug.getinfo(1, "S").source
local root = assert(helper_source:match("^@(.*)/spec/source_loader.lua$"))
local module_path = root .. "/src/adapter.lua"

package.loaded["strling"] = nil
package.preload["strling"] = function()
  local module = assert(loadfile(module_path))()
  assert(debug.getinfo(module.source_compile_request, "S").source == "@" .. module_path,
    "STRling component tests must execute the current checkout")
  return module
end
