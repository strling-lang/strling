# Your First Contribution: The "Zip Code" Test

[← Back to Developer Hub](../index.md)

This tutorial guides you through the **Golden Path** contribution workflow. You will add a new conformance test case to STRling and verify it across multiple languages using the CLI.

---

## The Mission

We want to ensure STRling correctly handles a US Zip Code pattern: 5 digits, optionally followed by a hyphen and 4 more digits.

**Pattern:** `digit(5) + (("-" + digit(4)) | "")`

---

## Step 1: Create the Test Case

Conformance tests are defined in `.strl` files in `tests/conformance/cases/`.

1.  Create a new file `tests/conformance/cases/zip.strl`:

```strling
test "US Zip Code" {
    match "90210"
    match "12345-6789"
    reject "1234"
    reject "123456"
    reject "12345-123"
    reject "abcde"
}

pattern = digit(5) + (("-" + digit(4)) | "")
```

---

## Step 2: Generate Specifications

The TypeScript binding is the **Reference Implementation**. We use it to generate the "Golden Master" JSON spec that all other languages must match.

1.  Setup the TypeScript environment (if not already done):

    ```bash
    ./strling setup typescript
    ```

2.  Generate the specs:

    ```bash
    cd bindings/typescript
    npm run build:specs
    ```

    _Note: This command compiles the TypeScript binding and runs the spec generator, creating a corresponding `zip.json` in `tests/spec/`._

---

## Step 3: Verify with Python

Now that the spec exists, we can verify that the Python binding correctly implements it.

1.  Setup the Python environment (if not already done):

    ```bash
    ./strling setup python
    ```

2.  Run the tests:

    ```bash
    ./strling test python
    ```

    You should see the new "US Zip Code" test case passing!

---

## Step 4: Verify with Other Languages

If you have other language toolchains installed (e.g., Rust, Go), you can verify them too. The beauty of the Golden Master is that once the spec is generated, _all_ bindings can test against it immediately.

```bash
# Optional: Verify Rust
./strling setup rust
./strling test rust
```

---

## Step 5: Commit

Once verified, commit your changes.

```bash
git add tests/conformance/cases/zip.strl tests/spec/zip.json
git commit -m "feat: add US Zip Code conformance test"
```

Congratulations! You've just added a portable, cross-language test case to STRling.
