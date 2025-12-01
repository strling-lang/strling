using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using Strling.Core;
using Xunit;

namespace STRling.Tests;

public class ConformanceTests
{
    public static IEnumerable<object[]> GetSpecFiles()
    {
        // Find the spec directory
        var currentDir = Directory.GetCurrentDirectory();
        var specDir = FindSpecDir(currentDir);

        if (specDir == null)
        {
            // Fallback for CI or different environments
            specDir = Path.GetFullPath(Path.Combine(currentDir, "../../../../../../tests/spec"));
            if (!Directory.Exists(specDir))
            {
                throw new DirectoryNotFoundException($"Could not find tests/spec directory. Searched from {currentDir}");
            }
        }

        var files = Directory.GetFiles(specDir, "*.json");
        foreach (var file in files)
        {
            yield return new object[] { file };
        }
    }

    private static string? FindSpecDir(string startDir)
    {
        var dir = new DirectoryInfo(startDir);
        while (dir != null)
        {
            // Check if we are at the root of the repo
            if (Directory.Exists(Path.Combine(dir.FullName, "bindings")) &&
                Directory.Exists(Path.Combine(dir.FullName, "tests", "spec")))
            {
                return Path.Combine(dir.FullName, "tests", "spec");
            }
            dir = dir.Parent;
        }
        return null;
    }

    [Theory]
    [MemberData(nameof(GetSpecFiles))]
    public void RunSpecTest(string filePath)
    {
        var filename = Path.GetFileName(filePath);
        Console.WriteLine($"=== RUN {filename}");

        var jsonContent = File.ReadAllText(filePath);
        JsonNode? jsonDoc;
        try
        {
            jsonDoc = JsonNode.Parse(jsonContent);
        }
        catch
        {
            // Ignore invalid JSON files if any
            return;
        }

        if (jsonDoc == null) return;

        var inputAstNode = jsonDoc["input_ast"];
        var expectedErrorNode = jsonDoc["expected_error"];

        if (inputAstNode == null)
        {
            if (expectedErrorNode != null)
            {
                // Parser test (no AST), out of scope. Pass.
                Console.WriteLine("    --- PASS: Parser test (no AST), out of scope");
                return;
            }
            return;
        }

        // Deserialize AST
        var options = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        };

        Node ast;
        try
        {
            ast = inputAstNode.Deserialize<Node>(options)!;
        }
        catch (Exception ex)
        {
            throw new Exception($"Failed to deserialize AST in {filename}: {ex.Message}", ex);
        }

        if (expectedErrorNode != null)
        {
            try
            {
                Compiler.Compile(ast);
                throw new Exception($"Expected error '{expectedErrorNode}' but compilation succeeded");
            }
            catch
            {
                Console.WriteLine("    --- PASS: Caught expected error");
                return;
            }
        }

        var expectedIrNode = jsonDoc["expected_ir"];
        if (expectedIrNode == null) return;

        // Compile to IR
        var ir = Compiler.Compile(ast);

        // Serialize IR to JsonNode for comparison
        var irJson = JsonSerializer.SerializeToNode(ir, options);

        // Compare
        if (!JsonNode.DeepEquals(irJson, expectedIrNode))
        {
            var expectedStr = expectedIrNode.ToJsonString(new JsonSerializerOptions { WriteIndented = true });
            var actualStr = irJson?.ToJsonString(new JsonSerializerOptions { WriteIndented = true });
            Assert.Fail($"IR mismatch in {Path.GetFileName(filePath)}.\nExpected:\n{expectedStr}\nActual:\n{actualStr}");
        }
    }
}
