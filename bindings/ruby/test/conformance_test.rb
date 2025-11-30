require 'minitest/autorun'
require 'json'
require_relative '../lib/strling/nodes'
require_relative '../lib/strling/ir'

class ConformanceTest < Minitest::Test
  SPEC_DIR = File.expand_path('../../../../tests/spec', __FILE__)

  Dir.glob(File.join(SPEC_DIR, '*.json')).each do |file|
    base_name = File.basename(file, '.json')
    
    # Generate test name with special handling for semantic tests
    test_name = case base_name
                when 'semantic_duplicates'
                  'test_semantic_duplicate_capture_group'
                when 'semantic_ranges'
                  'test_semantic_ranges'
                else
                  "test_conformance_#{base_name.gsub(/[^a-zA-Z0-9_]/, '_')}"
                end
    
    # Pre-check to determine test type
    begin
      pre_spec = JSON.parse(File.read(file))
    rescue JSON::ParserError
      next
    end
    
    # Define test method based on spec type
    if pre_spec['input_ast'] && pre_spec['expected_ir']
      # Standard conformance test
      define_method(test_name) do
        spec = JSON.parse(File.read(file))
        
        # Hydrate AST
        ast = Strling::Nodes::NodeFactory.from_json(spec['input_ast'])
        
        # Compile to IR
        ir = Strling::IR::Compiler.compile(ast)

        refute_nil ir, "Compilation returned nil"
        
        # Compare
        expected = spec['expected_ir']
        actual = serialize(ir)
        
        assert_equal expected, actual, "Mismatch in #{File.basename(file)}"
      end
    elsif pre_spec['expected_error']
      # Error test case - skip but ensure test name is visible in output
      define_method(test_name) do
        skip "Error test case (expected_error: #{pre_spec['expected_error']})"
      end
    end
  end

  def serialize(obj)
    case obj
    when Data
      obj.to_h.transform_keys(&:to_s).transform_values { |v| serialize(v) }.compact
    when Array
      obj.map { |v| serialize(v) }
    when Hash
      obj.transform_keys(&:to_s).transform_values { |v| serialize(v) }.compact
    else
      obj
    end
  end
end
