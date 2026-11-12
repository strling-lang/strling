"""Install exact release subjects in isolated consumers, without publication.

The fixtures exercise the versioned canonical protocol. They do not implement
language semantics or choose a target profile on behalf of package users.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

from tooling.release_supply_chain import (
    ROOT,
    MANIFEST_PATH,
    ReleaseSupplyChainError,
    _surface_identity,
    _surface_members,
    authenticate_source,
    canonical_json,
    document_fingerprint,
    inspect_release_payload,
    load_json,
    validate_manifest,
    _write_json,
    scoped_artifact,
)

CONSUMER_FIXTURES = {
    "source.json": "spec/contracts/1.0/examples/compile-request/regex-compat-success.json",
    "request.json": "spec/contracts/1.0/examples/compile-request/target-artifact.json",
    "target.json": "spec/targets/profiles/pcre2-10.43.json",
    "wrong-target.json": "spec/targets/profiles/pcre2-10.42.json",
}


PYTHON_CONSUMER = """import hashlib, importlib.metadata, json, pathlib, sys
from STRling import NativeClient, NativeLoadError, bundled_library_path, load_native
fixtures = pathlib.Path(sys.argv[1])
assert importlib.metadata.version("STRling") == sys.argv[2]
library = bundled_library_path().resolve()
assert library.is_relative_to(pathlib.Path(sys.prefix).resolve())
client = load_native()
assert client.describe()["native_abi"]["major"] == 1
source = client.compile(json.loads((fixtures / "source.json").read_text()))
assert source["outcome"] == "succeeded"
assert source["semantic_result"]["program"]["root"]["text"] == "a"
result = client.compile(json.loads((fixtures / "request.json").read_text()), json.loads((fixtures / "target.json").read_text()))
assert result["outcome"] == "succeeded"
assert result["artifact"]["pattern"]["text"] == "abc"
bad = fixtures / "wrong-kernel"
bad.write_bytes(b"\\0STRLING-PRODUCT-VERSION:0.0.0\\0")
try:
    NativeClient(bad)
except NativeLoadError:
    pass
else:
    raise AssertionError("mismatched native kernel accepted")
print(json.dumps({"status":"passed", "source_outcome":source["outcome"], "target_pattern":result["artifact"]["pattern"]["text"], "kernel_mismatch_rejected":True, "native_sha256":hashlib.sha256(library.read_bytes()).hexdigest()}))
"""

GO_CONSUMER = """package main
import ("encoding/json"; "os"; "fmt"; "strings"; strling "github.com/strling-lang/strling/bindings/go")
func read(name string) map[string]any { b,e:=os.ReadFile(name); if e!=nil { panic(e) }; var v map[string]any; if e=json.Unmarshal(b,&v); e!=nil {panic(e)}; return v }
func main() {
 c,e:=strling.LoadNative(os.Args[1]); if e!=nil {panic(e)}; defer c.Close()
 s,e:=c.Compile(read("source.json"),nil); if e!=nil {panic(e)}
 source:=s.(map[string]any); if source["outcome"]!="succeeded" || source["semantic_result"].(map[string]any)["program"].(map[string]any)["root"].(map[string]any)["text"]!="a" {panic("source compile failed")}
 r,e:=c.Compile(read("request.json"),read("target.json")); if e!=nil {panic(e)}
 result:=r.(map[string]any); pattern:=result["artifact"].(map[string]any)["pattern"].(map[string]any)["text"]
 if result["outcome"]!="succeeded" || pattern!="abc" {panic("target emission changed")}
 if bad,e:=strling.LoadNative(os.Args[2]); e==nil {bad.Close();panic("wrong kernel accepted")} else if !strings.Contains(e.Error(),"product identity") {panic(e)}
 b,_:=json.Marshal(map[string]any{"status":"passed","source_outcome":source["outcome"],"target_pattern":pattern,"kernel_mismatch_rejected":true});fmt.Println(string(b))
}
"""

DART_CONSUMER = """import 'dart:convert';
import 'dart:io';
import 'package:strling/strling.dart';
Map<String,Object?> read(String name) => (jsonDecode(File(name).readAsStringSync()) as Map).cast<String,Object?>();
void main(List<String> args) {
 final client = NativeClient.load(args[0]);
 try {
  final source = client.compile(read('source.json')) as Map;
  if(source['outcome']!='succeeded' || (((source['semantic_result'] as Map)['program'] as Map)['root'] as Map)['text']!='a') throw StateError('source compile failed');
  final result = client.compile(read('request.json'),targetProfile:read('target.json')) as Map;
  final pattern = ((result['artifact'] as Map)['pattern'] as Map)['text'];
  if(result['outcome']!='succeeded' || pattern!='abc') throw StateError('target emission changed');
  bool rejected=false;
  try { NativeClient.load(args[1]).close(); } on NativeAdapterException catch(e) { if(!e.toString().contains('product identity')) rethrow; rejected=true; }
  if(!rejected) throw StateError('wrong kernel accepted');
  print(jsonEncode({'status':'passed','source_outcome':source['outcome'],'target_pattern':pattern,'kernel_mismatch_rejected':rejected}));
 } finally { client.close(); }
}
"""

SWIFT_CONSUMER = """import Foundation
import STRling
func read(_ name: String) throws -> [String:Any] { try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: name))) as! [String:Any] }
let client = try NativeClient(libraryPath: CommandLine.arguments[1])
defer { client.close() }
let source = try client.compile(read("source.json")) as! [String:Any]
precondition(source["outcome"] as? String == "succeeded")
let literal = ((source["semantic_result"] as! [String:Any])["program"] as! [String:Any])["root"] as! [String:Any]
precondition(literal["text"] as? String == "a")
let result = try client.compile(read("request.json"), targetProfile: read("target.json")) as! [String:Any]
let pattern = ((result["artifact"] as! [String:Any])["pattern"] as! [String:Any])["text"] as! String
precondition(result["outcome"] as? String == "succeeded" && pattern == "abc")
precondition(STRling.version == CommandLine.arguments[3])
var rejected = false
do { let bad = try NativeClient(libraryPath: CommandLine.arguments[2]); bad.close() }
catch let error as NativeAdapterError { precondition(error.detail.contains("product identity")); rejected = true }
precondition(rejected)
let data = try JSONSerialization.data(withJSONObject: ["status":"passed", "source_outcome":source["outcome"]!, "target_pattern":pattern, "kernel_mismatch_rejected":rejected])
print(String(data: data, encoding: .utf8)!)
"""

CPP_CONSUMER = """#include <fstream>
#include <iostream>
#include <sstream>
#include "strling/native.hpp"
std::string read(const char *name) { std::ifstream f(name); std::ostringstream s; s << f.rdbuf(); if(!f) throw 1; return s.str(); }
int main(int argc,char **argv) {
 if(strling::version()!=STRLING_C_PACKAGE_VERSION) return 2;
 auto request=read(argv[1]); strling::client client;
 auto result = argc==3 ? client.compile_json(request,read(argv[2])) : client.compile_json(request);
 if(result.transport_status()!=STRLING_INTEROP_STATUS_RESPONSE_WRITTEN) return 3;
 std::cout << result.text() << std::endl;
}
"""

C_CONSUMER = """#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "strling.h"
char *read(const char *name) { FILE *f=fopen(name,"rb"); if(!f) exit(2); fseek(f,0,SEEK_END); long n=ftell(f); rewind(f); if(n<0 || n>1000000) exit(2); char *s=calloc((size_t)n+1,1); if(!s || fread(s,1,(size_t)n,f)!=(size_t)n) exit(2); fclose(f); return s; }
int main(int argc,char **argv) {
 if(strcmp(strling_version(),STRLING_C_PACKAGE_VERSION)) return 2;
 char *request=read(argv[1]); char *target=argc==3?read(argv[2]):NULL;
 strling_c_result_v1 result=strling_compile_json_v1(request,target); free(request); free(target);
 if(result.transport_status!=STRLING_INTEROP_STATUS_RESPONSE_WRITTEN) return 3;
 fwrite(result.response.data,1,result.response.len,stdout); putchar('\\n');
 return strling_c_result_free_v1(&result)==STRLING_INTEROP_STATUS_RESPONSE_WRITTEN?0:4;
}
"""

RUST_CONSUMER = """use std::{fs,env};
use strling::{CompileRequest,TargetProfile,KernelCompileError};
fn main() {
 let source:CompileRequest=serde_json::from_str(&fs::read_to_string("source.json").unwrap()).unwrap();
 let request:CompileRequest=serde_json::from_str(&fs::read_to_string("request.json").unwrap()).unwrap();
 let target:TargetProfile=serde_json::from_str(&fs::read_to_string("target.json").unwrap()).unwrap();
 let wrong:TargetProfile=serde_json::from_str(&fs::read_to_string("wrong-target.json").unwrap()).unwrap();
 let source=serde_json::to_value(strling::compile(&source,None).unwrap()).unwrap();
 let result=serde_json::to_value(strling::compile(&request,Some(&target)).unwrap()).unwrap();
 assert_eq!(source["outcome"],"succeeded");
 assert_eq!(source["semantic_result"]["program"]["root"]["text"],"a");
 assert_eq!(result["outcome"],"succeeded");
 assert_eq!(result["artifact"]["pattern"]["text"],"abc");
 assert_eq!(strling::version(),env::args().nth(1).unwrap());
 assert!(matches!(strling::compile(&request,Some(&wrong)),Err(KernelCompileError::TargetProfileMismatch{..})));
 println!("{}",serde_json::json!({"status":"passed","source_outcome":source["outcome"],"target_pattern":result["artifact"]["pattern"]["text"],"linked_package_version":strling::version(),"target_profile_mismatch_rejected":true}));
}
"""

CSHARP_CONSUMER = """using System.Text.Json;
using Strling.Native;
static JsonElement Read(string name) { using var d=JsonDocument.Parse(File.ReadAllText(name)); return d.RootElement.Clone(); }
using var client=NativeClient.Load(Path.Combine(AppContext.BaseDirectory,"strling_interop.dll"));
var compiler=new Strling.Compiler(client);
var source=compiler.Compile(Read("source.json"));
var target=compiler.Compile(Read("request.json"),Read("target.json"));
if(source.GetProperty("outcome").GetString()!="succeeded" || source.GetProperty("semantic_result").GetProperty("program").GetProperty("root").GetProperty("text").GetString()!="a") throw new Exception("source compile failed");
var pattern=target.GetProperty("artifact").GetProperty("pattern").GetProperty("text").GetString();
if(target.GetProperty("outcome").GetString()!="succeeded" || pattern!="abc") throw new Exception("target compile failed");
bool rejected=false;
try { using var bad=NativeClient.Load(Path.GetFullPath("wrong-kernel")); }
catch(NativeLoadException e) { if(!e.Message.Contains("product identity")) throw; rejected=true; }
if(!rejected) throw new Exception("wrong kernel accepted");
Console.WriteLine(JsonSerializer.Serialize(new {status="passed",source_outcome="succeeded",target_pattern=pattern,kernel_mismatch_rejected=rejected}));
"""

FSHARP_CONSUMER = """open System
open System.IO
open System.Text.Json
open STRling.FSharp
let read name =
    use doc = JsonDocument.Parse(File.ReadAllText(name))
    doc.RootElement.Clone()
use client = Api.loadClient (Path.Combine(AppContext.BaseDirectory,"strling_interop.dll"))
let compiler = Api.createCompiler client
let source = match Api.compile compiler (read "source.json") None with | Succeeded value -> value | _ -> failwith "source compile failed"
let target = match Api.compile compiler (read "request.json") (Some (read "target.json")) with | Succeeded value -> value | _ -> failwith "target compile failed"
if source.GetProperty("semantic_result").GetProperty("program").GetProperty("root").GetProperty("text").GetString() <> "a" then failwith "source literal changed"
let pattern = target.GetProperty("artifact").GetProperty("pattern").GetProperty("text").GetString()
if pattern <> "abc" then failwith "target pattern changed"
let mutable rejected = false
try
    use bad = Api.loadClient (Path.GetFullPath "wrong-kernel")
    ()
with :? Strling.Native.NativeLoadException as error ->
    if not (error.Message.Contains "product identity") then reraise()
    rejected <- true
if not rejected then failwith "wrong kernel accepted"
printfn "%s" (JsonSerializer.Serialize({|status="passed";source_outcome="succeeded";target_pattern=pattern;kernel_mismatch_rejected=rejected|}))
"""

JAVA_CONSUMER = """import com.strling.Compiler;
import com.strling.simply.Simply;
import com.strling.jvm.NativeClient;
import com.strling.jvm.NativeLoadException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.core.type.TypeReference;
import java.io.File;
import java.nio.file.Paths;
import java.util.Map;
public class Consumer {
 static final ObjectMapper mapper=new ObjectMapper();
 static Map<String,Object> read(String name) throws Exception {return mapper.readValue(new File(name),new TypeReference<Map<String,Object>>(){});}
 public static void main(String[] args) throws Exception {
  try(NativeClient client=NativeClient.load(Paths.get(args[0]))) {
   Compiler compiler=new Compiler(client);
   JsonNode simply=mapper.valueToTree(client.simplyCompile(Simply.merge(Simply.startsWith("a"),Simply.endsWith("a")).buildRequest(Map.of("requested_outputs",java.util.List.of("semantic"),"compiler_options",Map.of("partial_semantics","forbid","diagnostic_policy",Map.of("minimum_severity","hint"))))));
   if(!simply.path("status").asText().equals("success") || !simply.path("compile_result").path("outcome").asText().equals("succeeded")) throw new IllegalStateException("Simply anchor protocol failed");
   JsonNode source=mapper.valueToTree(compiler.compile(read("source.json")));
   JsonNode target=mapper.valueToTree(compiler.compile(read("request.json"),read("target.json")));
   if(!source.path("outcome").asText().equals("succeeded") || !source.path("semantic_result").path("program").path("root").path("text").asText().equals("a")) throw new IllegalStateException("source compile failed");
   String pattern=target.path("artifact").path("pattern").path("text").asText();
   if(!target.path("outcome").asText().equals("succeeded") || !pattern.equals("abc") || !com.strling.Strling.VERSION.equals(args[2])) throw new IllegalStateException("target or package identity changed");
   boolean rejected=false;
   try(NativeClient bad=NativeClient.load(Paths.get(args[1]))) {} catch(NativeLoadException error) {if(!(error.getMessage()+" "+(error.getCause()==null?"":error.getCause().getMessage())).contains("product identity")) throw error;rejected=true;}
   if(!rejected) throw new IllegalStateException("wrong kernel accepted");
   System.out.println(mapper.writeValueAsString(Map.of("status","passed","source_outcome","succeeded","target_pattern",pattern,"kernel_mismatch_rejected",rejected)));
  }
 }
}
"""

KOTLIN_CONSUMER = """import com.strling.jvm.NativeClient
import com.strling.jvm.NativeLoadException
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.core.type.TypeReference
import java.io.File
import java.nio.file.Paths
import strling.Compiler
import strling.Simply
val mapper=ObjectMapper()
fun read(name:String):Map<String,Any?> = mapper.readValue(File(name),object:TypeReference<Map<String,Any?>>() {})
fun main(args:Array<String>) {
 NativeClient.load(Paths.get(args[0])).use { client ->
  val compiler=Compiler(client)
  val simply:JsonNode=mapper.valueToTree(client.simplyCompile(Simply.merge(Simply.startsWith("a"),Simply.endsWith("a")).buildRequest(mapOf("requested_outputs" to listOf("semantic"),"compiler_options" to mapOf("partial_semantics" to "forbid","diagnostic_policy" to mapOf("minimum_severity" to "hint"))))))
  check(simply.path("status").asText()=="success" && simply.path("compile_result").path("outcome").asText()=="succeeded")
  val source:JsonNode=mapper.valueToTree(compiler.compile(read("source.json")))
  val target:JsonNode=mapper.valueToTree(compiler.compile(read("request.json"),read("target.json")))
  check(source.path("outcome").asText()=="succeeded" && source.path("semantic_result").path("program").path("root").path("text").asText()=="a")
  val pattern=target.path("artifact").path("pattern").path("text").asText()
  check(target.path("outcome").asText()=="succeeded" && pattern=="abc" && strling.STRling.version()==args[2])
  var rejected=false
  try { NativeClient.load(Paths.get(args[1])).close() } catch(error:NativeLoadException) { check(listOfNotNull(error.message,error.cause?.message).any { it.contains("product identity") });rejected=true }
  check(rejected)
  println(mapper.writeValueAsString(mapOf("status" to "passed","source_outcome" to "succeeded","target_pattern" to pattern,"kernel_mismatch_rejected" to rejected)))
 }
}
"""


def fixture_files(root: Path, work: Path) -> dict[str, str]:
    from tooling.documentation_programs import prepare

    hashes = {}
    for name, source in CONSUMER_FIXTURES.items():
        data = (root / source).read_bytes()
        (work / name).write_bytes(data)
        hashes[source] = hashlib.sha256(data).hexdigest()
    prepare(root, work)
    return hashes


def run_consumer(command: list[str], work: Path, environment: dict[str, str]) -> str:
    index = len(list(work.glob("consumer-command-*.json")))
    prefix = work / f"consumer-command-{index:04d}"
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=work,
            env=environment,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        for suffix, value in (("stdout", error.stdout), ("stderr", error.stderr)):
            prefix.with_suffix("." + suffix).write_bytes(
                value if isinstance(value, bytes) else (value or "").encode()
            )
        prefix.with_suffix(".json").write_text(
            json.dumps(
                {
                    "command": command,
                    "status": "timed-out",
                    "elapsed_seconds": time.monotonic() - started,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        raise
    prefix.with_suffix(".stdout").write_text(completed.stdout, encoding="utf-8")
    prefix.with_suffix(".stderr").write_text(completed.stderr, encoding="utf-8")
    prefix.with_suffix(".json").write_text(
        json.dumps(
            {
                "command": command,
                "exit_code": completed.returncode,
                "elapsed_seconds": time.monotonic() - started,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    if completed.returncode:
        # Consumers never receive registry credentials; preserve diagnostics for
        # local repairs without converting a failed install into a pass.
        raise ReleaseSupplyChainError(
            "consumer-failed", (completed.stdout + completed.stderr)[-12000:]
        )
    return completed.stdout


def copy_subject_directory(root: Path, member: dict, destination: Path) -> None:
    """Copy the complete certified file graph, without build/cache discovery."""
    prefix = Path(member["name"])
    for row in member["files"]:
        relative = Path(row["name"])
        if relative.is_absolute() or ".." in relative.parts or "\\" in row["name"]:
            raise ReleaseSupplyChainError(
                "consumer-package", "unsafe package member path"
            )
        suffix = relative.relative_to(prefix)
        source = root / relative
        target = destination / suffix
        if not source.resolve().is_relative_to(
            root.resolve()
        ) or not target.resolve().is_relative_to(destination.resolve()):
            raise ReleaseSupplyChainError(
                "consumer-package", "consumer staging escapes its isolated roots"
            )
        if (
            source.is_symlink()
            or hashlib.sha256(source.read_bytes()).hexdigest() != row["sha256"]
        ):
            raise ReleaseSupplyChainError(
                "consumer-package", "package bytes changed during consumer staging"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def canonical_results(source: dict, target: dict) -> dict:
    if "interop_protocol_version" in source or "interop_protocol_version" in target:
        for envelope in (source, target):
            if (
                envelope.get("interop_protocol_version") != "1.0.0"
                or envelope.get("operation") != "compile"
                or envelope.get("status") != "completed"
            ):
                raise ReleaseSupplyChainError(
                    "consumer-result", "native compile envelope did not complete"
                )
        source, target = source["result"], target["result"]
    if (
        source.get("outcome") != "succeeded"
        or source["semantic_result"]["program"]["root"]["text"] != "a"
    ):
        raise ReleaseSupplyChainError(
            "consumer-result",
            "source compilation did not produce its canonical literal: "
            + json.dumps(source)[:4000],
        )
    if (
        target.get("outcome") != "succeeded"
        or target["artifact"]["pattern"]["text"] != "abc"
    ):
        raise ReleaseSupplyChainError(
            "consumer-result",
            "target compilation did not produce its canonical pattern",
        )
    return {
        "status": "passed",
        "source_outcome": source["outcome"],
        "target_pattern": target["artifact"]["pattern"]["text"],
    }


def expect_product_rejection(
    command: list[str], work: Path, environment: dict[str, str]
) -> None:
    completed = subprocess.run(
        command, cwd=work, env=environment, capture_output=True, text=True, timeout=120
    )
    if (
        completed.returncode == 0
        or "product identity mismatch"
        not in (completed.stdout + completed.stderr).lower()
    ):
        raise ReleaseSupplyChainError(
            "consumer-mismatch",
            "the package did not explicitly reject a mismatched native product",
        )


def consume_native(
    root: Path,
    artifact: dict,
    work: Path,
    version: str,
    environment: dict[str, str],
    members: list[dict],
    harness_root: Path | None = None,
) -> dict:
    from tooling.release_packaging import host_scope

    slug = artifact["id"].removeprefix("release:")
    build = work / "build"
    prefix = work / "prefix"
    generator = (
        ["-G", "Visual Studio 17 2022", "-A", "x64", "-T", "v143"]
        if os.name == "nt"
        else []
    )
    toolchain = []
    if slug == "cpp":
        archives = [
            root / row["name"]
            for row in members
            if row["name"].endswith("-" + host_scope() + ".tgz")
        ]
        if len(archives) != 1:
            raise ReleaseSupplyChainError(
                "consumer-package", "one exact host Conan cache is required"
            )
        environment["CONAN_HOME"] = str(work / "conan-cache")
        run_consumer(["conan", "cache", "restore", str(archives[0])], work, environment)
        (work / "conanfile.txt").write_text(
            "[requires]\nstrling/"
            + version
            + "\n[generators]\nCMakeDeps\nCMakeToolchain\n"
        )
        install = [
            "conan",
            "install",
            ".",
            "--profile:all="
            + str((harness_root or root) / "bindings/cpp/profiles" / host_scope()),
            "--build=never",
            "--no-remote",
            "--output-folder=" + str(build),
        ]
        run_consumer(install, work, environment)
        toolchain = ["-DCMAKE_TOOLCHAIN_FILE=" + str(build / "conan_toolchain.cmake")]
        native_candidates = list(
            (work / "conan-cache").rglob(
                "strling_interop.lib" if os.name == "nt" else "libstrling_interop.a"
            )
        )
    else:
        source = work / "source"
        for member in members:
            if "files" in member:
                copy_subject_directory(root, member, source / member["name"])
            else:
                target = source / member["name"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / member["name"], target)
        native_build = work / "native-build"
        run_consumer(
            [
                "cmake",
                "-S",
                str(source / "bindings/c"),
                "-B",
                str(native_build),
                "-DCMAKE_BUILD_TYPE=Release",
                "-DBUILD_TESTING=OFF",
                *generator,
                *([] if os.name == "nt" else ["-DCMAKE_C_COMPILER=gcc-13"]),
            ],
            work,
            environment,
        )
        run_consumer(
            [
                "cmake",
                "--build",
                str(native_build),
                "--config",
                "Release",
                "--parallel",
                "2",
            ],
            work,
            environment,
        )
        run_consumer(
            [
                "cmake",
                "--install",
                str(native_build),
                "--config",
                "Release",
                "--prefix",
                str(prefix),
            ],
            work,
            environment,
        )
        native_candidates = list(
            prefix.rglob(
                "strling_interop.lib" if os.name == "nt" else "libstrling_interop.a"
            )
        )
    if len(native_candidates) != 1:
        raise ReleaseSupplyChainError(
            "consumer-native", "installed static runtime is absent or ambiguous"
        )
    native = native_candidates[0]
    native_hash = hashlib.sha256(native.read_bytes()).hexdigest()
    extension, package, target = (
        ("cpp", "strling-cpp", "STRling::cpp")
        if slug == "cpp"
        else ("c", "strling-c", "STRling::c")
    )
    (work / ("consumer." + extension)).write_text(
        CPP_CONSUMER if slug == "cpp" else C_CONSUMER
    )
    (work / "CMakeLists.txt").write_text(
        f"cmake_minimum_required(VERSION 3.20)\nproject(Consumer LANGUAGES {'CXX' if slug == 'cpp' else 'C'})\nset(CMAKE_CXX_STANDARD 17)\nfind_package({package} {version} EXACT CONFIG REQUIRED)\nadd_executable(Consumer consumer.{extension})\ntarget_link_libraries(Consumer PRIVATE {target})\n"
    )
    configure = [
        "cmake",
        "-S",
        str(work),
        "-B",
        str(build),
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_PREFIX_PATH=" + str(prefix),
        *generator,
        *toolchain,
    ]
    run_consumer(configure, work, environment)
    run_consumer(
        ["cmake", "--build", str(build), "--config", "Release", "--parallel", "2"],
        work,
        environment,
    )
    executable = build / ("Release/Consumer.exe" if os.name == "nt" else "Consumer")
    source_result = json.loads(
        run_consumer([str(executable), "source.json"], work, environment)
    )
    target_result = json.loads(
        run_consumer(
            [str(executable), "request.json", "target.json"], work, environment
        )
    )
    result = canonical_results(source_result, target_result)
    if slug == "cpp":
        from tooling.documentation_programs import readme

        (work / "consumer.cpp").write_text(readme(work, "cpp", 4), encoding="utf-8")
        run_consumer(
            ["cmake", "--build", str(build), "--config", "Release", "--parallel", "2"],
            work,
            environment,
        )
        documented = json.loads(run_consumer([str(executable)], work, environment))
        if (
            documented.get("status") != "success"
            or documented.get("compile_result", {}).get("outcome") != "succeeded"
        ):
            raise ReleaseSupplyChainError(
                "consumer-documentation", "C++ documented Simply program failed"
            )
    original = native.read_bytes()
    marker = b"\0STRLING-PRODUCT-VERSION:" + version.encode() + b"\0"
    if original.count(marker) != 1:
        raise ReleaseSupplyChainError(
            "consumer-native", "static runtime product marker is absent or ambiguous"
        )
    native.write_bytes(
        original.replace(
            marker, b"\0STRLING-PRODUCT-VERSION:" + b"0" * len(version) + b"\0"
        )
    )
    if slug == "cpp":
        expect_product_rejection(install, work, environment)
    else:
        configure[configure.index(str(build))] = str(work / "mismatch-build")
        expect_product_rejection(configure, work, environment)
    result.update(kernel_mismatch_rejected=True, native_sha256=native_hash)
    from tooling.documentation_programs import completed

    completed(result, work, ("bindings/cpp/README.md#4",) if slug == "cpp" else ())
    return result


def consume_gds(
    root: Path,
    artifact: dict,
    work: Path,
    version: str,
    environment: dict[str, str],
    members: list[dict],
    native: Path | None,
) -> dict:
    from tooling.release_payload import native_identity

    if native is None:
        raise ReleaseSupplyChainError(
            "consumer-native", "the explicit canonical native runtime is required"
        )
    if native.stat().st_size > 128 * 1024 * 1024:
        raise ReleaseSupplyChainError(
            "consumer-native", "native runtime exceeds the registered size limit"
        )
    data = native.read_bytes()
    native_identity(data, version)
    from tooling.release_native import inspect_native

    inspect_native(data)
    library = work / native.name
    library.write_bytes(data)
    bad = work / "wrong-kernel"
    bad.write_bytes(b"\0STRLING-PRODUCT-VERSION:0.0.0\0")
    slug = artifact["id"].removeprefix("release:")
    package_member = next(
        row
        for row in members
        if row["name"]
        == ("target/release-packaging/dart" if slug == "dart" else "bindings/" + slug)
    )
    package = work / "package"
    copy_subject_directory(root, package_member, package)
    if slug == "go":
        (work / "go.mod").write_text(
            "module strling-release-consumer\n\ngo 1.22\n\nrequire github.com/strling-lang/strling/bindings/go v0.0.0\nreplace github.com/strling-lang/strling/bindings/go => ./package\n"
        )
        (work / "main.go").write_text(GO_CONSUMER)
        environment.update(CGO_ENABLED="1", GOPROXY="off", GOSUMDB="off", GOWORK="off")
        output = run_consumer(
            ["go", "run", ".", str(library), str(bad)], work, environment
        )
    elif slug == "dart":
        (work / "pubspec.yaml").write_text(
            "name: strling_release_consumer\nenvironment:\n  sdk: '>=3.0.0 <4.0.0'\ndependencies:\n  strling:\n    path: package\n"
        )
        (work / "consumer.dart").write_text(DART_CONSUMER)
        run_consumer(["dart", "pub", "get", "--offline"], work, environment)
        output = run_consumer(
            ["dart", "run", "consumer.dart", str(library), str(bad)], work, environment
        )
    else:
        (work / "Package.swift").write_text(
            '// swift-tools-version: 5.9\nimport PackageDescription\nlet package = Package(name:"Consumer",dependencies:[.package(path:"package")],targets:[.executableTarget(name:"Consumer",dependencies:[.product(name:"STRling",package:"package")])])\n'
        )
        source = work / "Sources/Consumer/main.swift"
        source.parent.mkdir(parents=True)
        source.write_text(SWIFT_CONSUMER)
        run_consumer(["swift", "build", "-c", "release"], work, environment)
        output = run_consumer(
            [
                "swift",
                "run",
                "--skip-build",
                "-c",
                "release",
                "Consumer",
                str(library),
                str(bad),
                version,
            ],
            work,
            environment,
        )
    result = json.loads(output)
    from tooling.documentation_programs import readme

    if slug == "go":
        (work / "main.go").write_text(readme(work, slug), encoding="utf-8")
        command = ["go", "run", ".", str(library)]
    elif slug == "dart":
        (work / "consumer.dart").write_text(readme(work, slug), encoding="utf-8")
        command = ["dart", "run", "consumer.dart", str(library)]
    else:
        (work / "Sources/Consumer/main.swift").write_text(
            readme(work, slug), encoding="utf-8"
        )
        run_consumer(["swift", "build", "-c", "release"], work, environment)
        command = [
            "swift",
            "run",
            "--skip-build",
            "-c",
            "release",
            "Consumer",
            str(library),
        ]
    if run_consumer(command, work, environment).strip() != "succeeded":
        raise ReleaseSupplyChainError(
            "consumer-documentation", "documented " + slug + " example failed"
        )
    result["native_sha256"] = hashlib.sha256(data).hexdigest()
    from tooling.documentation_programs import completed

    completed(result, work, (f"bindings/{slug}/README.md#1",))
    return result


def consume_python(
    root: Path,
    work: Path,
    version: str,
    environment: dict[str, str],
    members: list[dict],
) -> dict:
    if sys.version_info[:2] != (3, 12):
        raise ReleaseSupplyChainError(
            "consumer-runtime", "the Python consumer requires CPython 3.12"
        )
    tag = "win_amd64" if os.name == "nt" else "linux_x86_64"
    wheels = [
        root / row["name"]
        for row in members
        if row["name"].endswith("-cp312-none-" + tag + ".whl")
    ]
    if len(wheels) != 1:
        raise ReleaseSupplyChainError(
            "consumer-package", "one exact host wheel is required"
        )
    venv = work / "venv"
    run_consumer(
        [sys.executable, "-m", "venv", "--without-pip", str(venv)], work, environment
    )
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    run_consumer(
        [
            sys.executable,
            "-m",
            "pip",
            "--python",
            str(python),
            "--isolated",
            "install",
            "--no-index",
            "--no-deps",
            str(wheels[0]),
        ],
        work,
        environment,
    )
    script = work / "consumer.py"
    script.write_text(PYTHON_CONSUMER, encoding="utf-8")
    result = json.loads(
        run_consumer(
            [str(python), "-I", str(script), str(work), version], work, environment
        )
    )
    from tooling.documentation_programs import python_program

    script.write_text(python_program(work), encoding="utf-8")
    if (
        not run_consumer([str(python), "-I", str(script)], work, environment)
        .rstrip()
        .endswith("documentation passed")
    ):
        raise ReleaseSupplyChainError(
            "consumer-documentation", "documented Python examples failed"
        )
    from tooling.documentation_programs import completed, PYTHON_EXAMPLES

    completed(result, work, PYTHON_EXAMPLES)
    return result


def consume_rust(
    root: Path,
    work: Path,
    version: str,
    environment: dict[str, str],
    members: list[dict],
) -> dict:
    from tooling.release_payload import archive_files

    if len(members) != 1:
        raise ReleaseSupplyChainError(
            "consumer-package", "one exact Rust crate is required"
        )
    package = work / "package"
    files = archive_files(root / members[0]["name"])
    for name, data in files.items():
        relative = Path(name).relative_to("strling-" + version)
        target = package / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    lock = tomllib.loads((package / "Cargo.lock").read_text(encoding="utf-8"))
    serde_json = next(
        row["version"] for row in lock["package"] if row["name"] == "serde_json"
    )
    (work / "Cargo.toml").write_text(
        '[package]\nname="strling-release-consumer"\nversion="0.0.0"\nedition="2021"\n[dependencies]\nstrling={path="package",version="='
        + version
        + '"}\nserde_json="='
        + serde_json
        + '"\n'
    )
    shutil.copyfile(package / "Cargo.lock", work / "Cargo.lock")
    (work / "src").mkdir()
    (work / "src/main.rs").write_text(RUST_CONSUMER)
    run_consumer(["cargo", "+1.75.0", "build", "--offline"], work, environment)
    executable = (
        work
        / "target/debug"
        / (
            "strling-release-consumer.exe"
            if os.name == "nt"
            else "strling-release-consumer"
        )
    )
    result = json.loads(run_consumer([str(executable), version], work, environment))
    from tooling.documentation_programs import rust_program

    (work / "src/main.rs").write_text(rust_program(work), encoding="utf-8")
    run_consumer(["cargo", "+1.75.0", "build", "--offline"], work, environment)
    if (
        run_consumer([str(executable)], work, environment).strip()
        != "documentation passed"
    ):
        raise ReleaseSupplyChainError(
            "consumer-documentation", "documented Rust examples failed"
        )
    from tooling.documentation_programs import completed

    completed(result, work, ("bindings/rust/README.md#1", "bindings/rust/README.md#2"))
    return result


def consume_dotnet(
    root: Path,
    artifact: dict,
    work: Path,
    version: str,
    environment: dict[str, str],
    members: list[dict],
    manifest: dict,
) -> dict:
    from tooling.dotnet_adapter_package import (
        _write_consumer_files,
        _fsharp_core_package,
    )

    dotnet = shutil.which("dotnet")
    if dotnet is None:
        raise ReleaseSupplyChainError(
            "consumer-runtime", "the governed .NET SDK is required"
        )
    feed = work / "feed"
    feed.mkdir()
    companion = None
    packages = list(members)
    if artifact["id"] == "release:fsharp":
        csharp = next(
            row for row in manifest["artifacts"] if row["id"] == "release:csharp"
        )
        companion = _surface_members(root, csharp, version)
        inspect_release_payload(root, csharp, version, companion)
        packages.extend(companion)
    for row in packages:
        shutil.copyfile(root / row["name"], feed / Path(row["name"]).name)
    shutil.copyfile(_fsharp_core_package(dotnet), feed / "FSharp.Core.9.0.300.nupkg")
    config, csharp_project, fsharp_project = _write_consumer_files(work, feed)
    project = csharp_project if artifact["id"] == "release:csharp" else fsharp_project
    source = CSHARP_CONSUMER if artifact["id"] == "release:csharp" else FSHARP_CONSUMER
    (
        project.parent
        / ("Program.cs" if artifact["id"] == "release:csharp" else "Program.fs")
    ).write_text(source)
    for name in ("source.json", "request.json", "target.json"):
        shutil.copyfile(work / name, project.parent / name)
    (project.parent / "wrong-kernel").write_bytes(b"\0STRLING-PRODUCT-VERSION:0.0.0\0")
    environment["NUGET_PACKAGES"] = str(work / "packages")
    environment["DOTNET_CLI_HOME"] = str(work / "dotnet-home")
    run_consumer(
        [
            dotnet,
            "restore",
            str(project),
            "--configfile",
            str(config),
            "-p:NuGetAudit=false",
        ],
        work,
        environment,
    )
    run_consumer(
        [dotnet, "build", str(project), "-c", "Release", "--no-restore"],
        work,
        environment,
    )
    output = run_consumer(
        [
            dotnet,
            "run",
            "--project",
            str(project),
            "-c",
            "Release",
            "--no-build",
            "--no-restore",
        ],
        project.parent,
        environment,
    )
    result = json.loads(output)
    from tooling.documentation_programs import readme

    slug = artifact["id"].removeprefix("release:")
    documented = readme(work, slug)
    if slug == "csharp":
        documented += "\n" + readme(work, slug, 2)
    (project.parent / ("Program.cs" if slug == "csharp" else "Program.fs")).write_text(
        documented, encoding="utf-8"
    )
    run_consumer(
        [dotnet, "build", str(project), "-c", "Release", "--no-restore"],
        work,
        environment,
    )
    if (
        run_consumer(
            [
                dotnet,
                "run",
                "--project",
                str(project),
                "-c",
                "Release",
                "--no-build",
                "--no-restore",
            ],
            project.parent,
            environment,
        ).strip()
        != "succeeded"
    ):
        raise ReleaseSupplyChainError(
            "consumer-documentation", "documented .NET example failed"
        )
    from tooling.documentation_programs import completed

    completed(
        result,
        work,
        tuple(
            f"bindings/{slug}/README.md#{ordinal}"
            for ordinal in ((1, 2) if slug == "csharp" else (1,))
        ),
    )
    if companion:
        result["companion_subject_sha256"] = _surface_identity(companion)[1]
    return result


def consume_jvm(
    root: Path,
    artifact: dict,
    work: Path,
    version: str,
    environment: dict[str, str],
    members: list[dict],
    manifest: dict,
    native: Path | None,
    harness_root: Path | None = None,
) -> dict:
    from tooling.jvm_adapter_package import EXTERNAL_PACKAGES
    from tooling.release_payload import native_identity

    if native is None or native.stat().st_size > 128 * 1024 * 1024:
        raise ReleaseSupplyChainError(
            "consumer-native", "an explicit bounded native runtime is required"
        )
    native_bytes = native.read_bytes()
    native_identity(native_bytes, version)
    from tooling.release_native import inspect_native

    inspect_native(native_bytes)
    library = work / native.name
    library.write_bytes(native_bytes)
    bad = work / "wrong-kernel"
    bad.write_bytes(b"\0STRLING-PRODUCT-VERSION:0.0.0\0")
    repository = Path(
        environment.get("STRLING_MAVEN_REPOSITORY", str(Path.home() / ".m2/repository"))
    )
    harness_root = harness_root or root
    verification = ET.parse(
        harness_root / "bindings/kotlin/gradle/verification-metadata.xml"
    ).getroot()
    for element in verification.iter():
        element.tag = element.tag.split("}")[-1]
    jars = []
    lib = work / "lib"
    lib.mkdir()
    companions = None
    package_rows = list(members)
    if artifact["id"] == "release:kotlin":
        java = next(row for row in manifest["artifacts"] if row["id"] == "release:java")
        companions = _surface_members(root, java, version)
        inspect_release_payload(root, java, version, companions)
        package_rows.extend(
            row for row in companions if row["name"].startswith("bindings/jvm/")
        )
    for row in package_rows:
        if row["name"].endswith(
            (
                "strling-" + version + ".jar",
                "strling-jvm-" + version + ".jar",
                "strling-kotlin-" + version + ".jar",
            )
        ):
            target = lib / Path(row["name"]).name
            shutil.copyfile(root / row["name"], target)
            jars.append(target)
    dependency_hashes = {}
    for coordinate, release, _ in EXTERNAL_PACKAGES:
        if artifact["id"] == "release:java" and coordinate in {
            "org.jetbrains.kotlin:kotlin-stdlib",
            "org.jetbrains:annotations",
        }:
            continue
        group, name = coordinate.split(":")
        filename = name + "-" + release + ".jar"
        path = repository / Path(*group.split(".")) / name / release / filename
        if not path.is_file():
            cached = list(
                (
                    Path(
                        environment.get(
                            "GRADLE_USER_HOME", str(Path.home() / ".gradle")
                        )
                    )
                    / "caches/modules-2/files-2.1"
                    / group
                    / name
                    / release
                ).glob("*/" + filename)
            )
            if len(cached) != 1:
                raise ReleaseSupplyChainError(
                    "consumer-dependency",
                    "published JVM runtime is unavailable or ambiguous: " + coordinate,
                )
            path = cached[0]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        component = next(
            (
                row
                for row in verification.iter("component")
                if row.attrib == {"group": group, "name": name, "version": release}
            ),
            None,
        )
        accepted = (
            []
            if component is None
            else [
                sha.get("value")
                for row in component.findall("artifact")
                if row.get("name") == filename
                for sha in row.findall("sha256")
            ]
        )
        if digest not in accepted:
            raise ReleaseSupplyChainError(
                "consumer-dependency",
                "JVM runtime differs from reviewed verification metadata: "
                + coordinate,
            )
        target = lib / filename
        shutil.copyfile(path, target)
        jars.append(target)
        dependency_hashes[coordinate + ":" + release] = digest
    classpath = os.pathsep.join(map(str, jars))
    if artifact["id"] == "release:java":
        (work / "Consumer.java").write_text(JAVA_CONSUMER)
        run_consumer(
            ["javac", "--release", "11", "-cp", classpath, "Consumer.java"],
            work,
            environment,
        )
        output = run_consumer(
            [
                "java",
                "-cp",
                str(work) + os.pathsep + classpath,
                "Consumer",
                str(library),
                str(bad),
                version,
            ],
            work,
            environment,
        )
    else:
        (work / "settings.gradle.kts").write_text('rootProject.name="Consumer"\n')
        # The closed runtime graph above already supplies the verified stdlib.
        (work / "gradle.properties").write_text(
            "kotlin.stdlib.default.dependency=false\n"
        )
        file_literals = ",".join(json.dumps(path.as_posix()) for path in jars)
        (work / "build.gradle.kts").write_text(
            'plugins { kotlin("jvm") version "2.0.20"; application }\nrepositories { mavenCentral() }\ndependencies { implementation(files('
            + file_literals
            + ')) }\napplication { mainClass.set("ConsumerKt") }\n'
        )
        source = work / "src/main/kotlin/Consumer.kt"
        source.parent.mkdir(parents=True)
        source.write_text(KOTLIN_CONSUMER)
        (work / "gradle").mkdir()
        shutil.copyfile(
            harness_root / "bindings/kotlin/gradle/verification-metadata.xml",
            work / "gradle/verification-metadata.xml",
        )
        wrapper = (
            harness_root
            / "bindings/kotlin"
            / ("gradlew.bat" if os.name == "nt" else "gradlew")
        )
        run_consumer(
            [str(wrapper), "--offline", "--no-daemon", "installDist"], work, environment
        )
        output = run_consumer(
            [
                "java",
                "-cp",
                str(work / "build/classes/kotlin/main") + os.pathsep + classpath,
                "ConsumerKt",
                str(library),
                str(bad),
                version,
            ],
            work,
            environment,
        )
    result = json.loads(output)
    from tooling.documentation_programs import readme

    if artifact["id"] == "release:java":
        (work / "Example.java").write_text(readme(work, "java", 2), encoding="utf-8")
        run_consumer(
            ["javac", "--release", "11", "-cp", classpath, "Example.java"],
            work,
            environment,
        )
        command = [
            "java",
            "-cp",
            str(work) + os.pathsep + classpath,
            "Example",
            str(library),
        ]
    else:
        source.write_text(readme(work, "kotlin", 2), encoding="utf-8")
        run_consumer(
            [str(wrapper), "--offline", "--no-daemon", "installDist"], work, environment
        )
        command = [
            "java",
            "-cp",
            str(work / "build/classes/kotlin/main") + os.pathsep + classpath,
            "ConsumerKt",
            str(library),
        ]
    if run_consumer(command, work, environment).strip() != "succeeded":
        raise ReleaseSupplyChainError(
            "consumer-documentation", "documented JVM example failed"
        )
    from tooling.documentation_programs import completed

    completed(
        result,
        work,
        ("bindings/" + artifact["id"].removeprefix("release:") + "/README.md#2",),
    )
    result.update(
        native_sha256=hashlib.sha256(native_bytes).hexdigest(),
        runtime_dependency_sha256=dependency_hashes,
    )
    if companions:
        result["companion_subject_sha256"] = _surface_identity(companions)[1]
    return result


def execute_consumer_contract(
    artifact_id: str,
    *,
    root: Path,
    fixture_root: Path,
    work: Path,
    version: str,
    environment: dict[str, str],
    members: list[dict],
    artifact: dict,
    manifest: dict,
    native: Path | None,
) -> tuple[dict, dict]:
    """Run the shared semantic-free consumer contract against supplied subjects.

    The caller authenticates subjects and establishes process/filesystem isolation.
    Public verification supplies a retrieval-only root, never a producer checkout.
    Fixtures and executable test expectations always come from the trusted harness.
    """
    fixtures = fixture_files(fixture_root, work)
    if artifact_id == "release:python":
        result = consume_python(root, work, version, environment, members)
    elif artifact_id in {"release:go", "release:dart", "release:swift"}:
        result = consume_gds(
            root, artifact, work, version, environment, members, native
        )
    elif artifact_id in {"release:c", "release:cpp"}:
        result = consume_native(
            root,
            artifact,
            work,
            version,
            environment,
            members,
            harness_root=fixture_root,
        )
    elif artifact_id == "release:rust":
        result = consume_rust(root, work, version, environment, members)
    elif artifact_id in {"release:csharp", "release:fsharp"}:
        result = consume_dotnet(
            root, artifact, work, version, environment, members, manifest
        )
    elif artifact_id in {"release:java", "release:kotlin"}:
        result = consume_jvm(
            root,
            artifact,
            work,
            version,
            environment,
            members,
            manifest,
            native,
            harness_root=fixture_root,
        )
    else:
        raise ReleaseSupplyChainError(
            "consumer-unavailable",
            "isolated consumer is not implemented for " + artifact_id,
        )
    compatibility = (
        result.get("linked_package_version") == version
        and result.get("target_profile_mismatch_rejected") is True
        if artifact_id == "release:rust"
        else result.get("kernel_mismatch_rejected") is True
    )
    if (
        result.get("status") != "passed"
        or result.get("source_outcome") != "succeeded"
        or result.get("target_pattern") != "abc"
        or not compatibility
    ):
        raise ReleaseSupplyChainError(
            "consumer-result",
            "consumer did not prove canonical success and mismatch refusal",
        )
    from tooling.documentation_programs import verify_proof

    verify_proof(fixture_root, artifact_id.removeprefix("release:"), result)
    return result, fixtures


def public_consumer_environment(
    work: Path, sdk_environment: dict[str, str]
) -> dict[str, str]:
    """Allow only SDK/process prerequisites, with fresh consumer configuration."""
    allowed = {
        "PATH",
        "SystemRoot",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "INCLUDE",
        "LIB",
        "LIBPATH",
        "JAVA_HOME",
        "DOTNET_ROOT",
        "RUSTUP_HOME",
        "CARGO_HOME",
        "STRLING_MAVEN_REPOSITORY",
        "STRLING_GRADLE_CACHE",
        "STRLING_PUB_CACHE",
        "GOROOT",
        "PROGRAMDATA",
        "ProgramData",
        "ALLUSERSPROFILE",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMW6432",
        "COMMONPROGRAMFILES",
        "COMMONPROGRAMFILES(X86)",
        "COMMONPROGRAMW6432",
        "SYSTEMDRIVE",
    }
    environment = {
        key: value
        for key, value in sdk_environment.items()
        if key.upper() in {name.upper() for name in allowed}
    }
    home = work / "home"
    home.mkdir()
    temporary = work / "tmp"
    temporary.mkdir()
    environment.update(
        HOME=str(home),
        USERPROFILE=str(home),
        APPDATA=str(home / "appdata"),
        LOCALAPPDATA=str(home / "localappdata"),
        TMP=str(temporary),
        TEMP=str(temporary),
        TMPDIR=str(temporary),
        XDG_CONFIG_HOME=str(home / "config"),
        XDG_CACHE_HOME=str(home / "cache"),
        PYTHONNOUSERSITE="1",
        PIP_CONFIG_FILE=os.devnull,
        PIP_NO_INDEX="1",
        PIP_DISABLE_PIP_VERSION_CHECK="1",
        NPM_CONFIG_USERCONFIG=os.devnull,
        NPM_CONFIG_GLOBALCONFIG=os.devnull,
        NUGET_PACKAGES=str(home / "nuget"),
        DOTNET_CLI_HOME=str(home / "dotnet"),
        DOTNET_CLI_TELEMETRY_OPTOUT="1",
        DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1",
        DOTNET_GENERATE_ASPNET_CERTIFICATE="false",
        DOTNET_ADD_GLOBAL_TOOLS_TO_PATH="false",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        CARGO_INCREMENTAL="0",
        CARGO_BUILD_JOBS="2",
        GOWORK="off",
        TZ="UTC",
        LC_ALL="C",
        PYTHONHASHSEED="0",
    )
    environment.setdefault("STRLING_MAVEN_REPOSITORY", str(home / "maven"))
    gradle = Path(environment.pop("STRLING_GRADLE_CACHE", str(home / "gradle")))
    if any(
        (gradle / name).exists()
        for name in ("init.gradle", "init.gradle.kts", "init.d", "gradle.properties")
    ):
        raise ReleaseSupplyChainError(
            "consumer-isolation",
            "Gradle dependency cache contains executable user configuration",
        )
    environment["GRADLE_USER_HOME"] = str(gradle)
    environment["PUB_CACHE"] = environment.pop("STRLING_PUB_CACHE", str(home / "pub"))
    return environment


def verify_retrieved_consumer(
    artifact_id: str,
    *,
    retrieval_root: Path,
    fixture_root: Path,
    work: Path,
    manifest: dict,
    version: str,
    sdk_environment: dict[str, str],
    retrieval_files: dict[str, str],
    authority: str,
    native: Path | None = None,
) -> dict:
    """Exercise authenticated retrieved subjects using the canonical consumers.

    Live public execution is restricted to disposable hosted verification runners.
    Staged qualification remains engineering evidence even after successful runs.
    The orchestrator authenticates every retrieval file before invoking this API.
    """
    from tooling.release_packaging import host_scope
    from tooling.release_supply_chain import _probe_toolchain

    if authority not in {"public", "staged"}:
        raise ReleaseSupplyChainError(
            "consumer-authority", "only public or certified staged payloads may execute"
        )
    if authority == "public" and (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
    ):
        raise ReleaseSupplyChainError(
            "consumer-isolation",
            "public packages require disposable hosted verification runners",
        )
    retrieval_root, fixture_root, work = (
        retrieval_root.resolve(),
        fixture_root.resolve(),
        work.resolve(),
    )
    if (
        retrieval_root == fixture_root
        or work.is_relative_to(retrieval_root)
        or work.is_relative_to(fixture_root)
    ):
        raise ReleaseSupplyChainError(
            "consumer-isolation",
            "retrieved subjects, trusted fixtures and consumer workspace must be separate",
        )
    if work.exists():
        raise ReleaseSupplyChainError(
            "consumer-isolation", "consumer workspace must be fresh"
        )
    artifact = next(
        (row for row in manifest["artifacts"] if row["id"] == artifact_id), None
    )
    scope = host_scope()
    if (
        artifact is None
        or artifact["distribution_contract"]["tier"] != "Supported"
        or scope not in artifact["distribution_contract"]["platforms"]
    ):
        raise ReleaseSupplyChainError(
            "consumer-scope", "consumer is outside the registered Supported scope"
        )
    artifact = scoped_artifact(artifact, scope)
    public_contract = load_json(
        Path(__file__).resolve().parents[1] / "governance/public-distribution.json"
    )
    policy_sha256 = document_fingerprint(load_json(fixture_root / "toolchain.json"))
    toolchains = [
        _probe_toolchain(
            fixture_root,
            artifact_id=artifact_id,
            toolchain_id=identity,
            policy_sha256=policy_sha256,
            scope=scope,
        )
        for identity in public_contract["consumer_toolchains"][artifact_id]
    ]
    if any(row["status"] != "passed" for row in toolchains):
        raise ReleaseSupplyChainError(
            "consumer-runtime",
            "governed consumer runtime prerequisites failed: " + json.dumps(toolchains),
        )
    for name, digest in retrieval_files.items():
        relative = Path(name)
        path = retrieval_root / relative
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or path.is_symlink()
            or not path.resolve().is_relative_to(retrieval_root)
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise ReleaseSupplyChainError(
                "consumer-substitution", "retrieved subject changed before installation"
            )
    members = _surface_members(retrieval_root, artifact, version)
    for member in members:
        for row in member.get("files", [member]):
            if retrieval_files.get(row["name"]) != row["sha256"]:
                raise ReleaseSupplyChainError(
                    "consumer-substitution",
                    "consumer selected a file without authenticated retrieval",
                )
    if native is not None:
        native = native.resolve()
        if (
            not native.is_relative_to(retrieval_root)
            or retrieval_files.get(native.relative_to(retrieval_root).as_posix())
            != hashlib.sha256(native.read_bytes()).hexdigest()
        ):
            raise ReleaseSupplyChainError(
                "consumer-native",
                "caller-provided native runtime lacks authenticated retrieval",
            )
    work.mkdir(parents=True)
    environment = public_consumer_environment(work, sdk_environment)
    result, fixtures = execute_consumer_contract(
        artifact_id,
        root=retrieval_root,
        fixture_root=fixture_root,
        work=work,
        version=version,
        environment=environment,
        members=members,
        artifact=artifact,
        manifest=manifest,
        native=native,
    )
    receipt = {
        "document_kind": "retrieved-consumer-receipt",
        "schema_version": "1.0.0",
        "artifact_id": artifact_id,
        "scope": scope,
        "product_version": version,
        "authority": authority,
        "status": "VERIFIED" if authority == "public" else "READY",
        "retrieval_files_sha256": document_fingerprint(retrieval_files),
        "fixture_sha256": fixtures,
        "result": result,
        "environment_keys": sorted(environment),
        "toolchains": toolchains,
        "runner_environment": os.environ.get(
            "RUNNER_ENVIRONMENT", "local-staged-qualification"
        ),
        "publication_authorized": False,
    }
    receipt["receipt_fingerprint"] = hashlib.sha256(canonical_json(receipt)).hexdigest()
    return receipt


def verify_consumer(
    artifact_id: str,
    *,
    root: Path = ROOT,
    engineering: bool = False,
    native: Path | None = None,
) -> dict:
    from tooling.release_packaging import build_environment, host_scope

    root = root.resolve()
    manifest = validate_manifest(
        load_json(root / MANIFEST_PATH.relative_to(ROOT)), root=root
    )
    artifact = next(
        (row for row in manifest["artifacts"] if row["id"] == artifact_id), None
    )
    if artifact is None or artifact["distribution_contract"]["tier"] != "Supported":
        raise ReleaseSupplyChainError(
            "consumer-scope", "a registered Supported consumer is required"
        )
    scope = host_scope()
    if scope not in artifact["distribution_contract"]["platforms"]:
        raise ReleaseSupplyChainError(
            "consumer-scope", "the host is outside this package's Supported scope"
        )
    artifact = scoped_artifact(artifact, scope)
    version = load_json(root / "governance/release-policy.json")["product"]["version"]
    source = None if engineering else authenticate_source(root)
    members = _surface_members(root, artifact, version)
    inspect_release_payload(root, artifact, version, members)
    environment = build_environment(root, "0", manifest)
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        environment.pop(name, None)
    environment.update(
        PYTHONNOUSERSITE="1", PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1"
    )
    with tempfile.TemporaryDirectory(prefix="strling-consumer-") as temporary:
        work = Path(temporary).resolve()
        if work.is_relative_to(root):
            raise ReleaseSupplyChainError(
                "consumer-isolation", "consumer must run outside its source checkout"
            )
        result, fixtures = execute_consumer_contract(
            artifact_id,
            root=root,
            fixture_root=root,
            work=work,
            version=version,
            environment=environment,
            members=members,
            artifact=artifact,
            manifest=manifest,
            native=native,
        )
    receipt = {
        "schema_version": "2.0.0",
        "document_kind": "release-consumer-receipt",
        "artifact_id": artifact_id,
        "product_version": version,
        "scope": scope,
        "source": source,
        "engineering": engineering,
        "subject_sha256": _surface_identity(members)[1],
        "manifest_fingerprint": document_fingerprint(manifest),
        "fixture_sha256": fixtures,
        "result": result,
        "publication_authorized": False,
    }
    receipt["receipt_fingerprint"] = hashlib.sha256(canonical_json(receipt)).hexdigest()
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--engineering", action="store_true")
    parser.add_argument("--native-library", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ReleaseSupplyChainError(
                "output-exists", "consumer receipt already exists"
            )
        receipt = verify_consumer(
            args.artifact_id,
            root=args.source_root,
            engineering=args.engineering,
            native=args.native_library,
        )
        _write_json(args.output, receipt)
        print(
            json.dumps(
                {
                    "status": "passed",
                    "artifact_id": args.artifact_id,
                    "scope": receipt["scope"],
                    "engineering": args.engineering,
                }
            )
        )
        return 0
    except (
        ReleaseSupplyChainError,
        OSError,
        ValueError,
        subprocess.SubprocessError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
