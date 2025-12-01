# Your First Contribution: The "Zip Code" Test

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

    _This compiles `zip.strl` into `tests/spec/zip.json`, containing the AST, IR, and expected regexes._

---

## Step 3: Verify with Python

Now, let's verify that the Python binding correctly implements this logic.

1.  Run the Python tests:

    ```bash
    ./strling test python
    ```

    _The test runner will pick up `tests/spec/zip.json` and execute it against the Python implementation._

---

## Step 4: Verify with Rust (Optional)

If you have Rust installed, verify it there too. This is the power of STRling's conformance suite—one test file validates the entire ecosystem.

1.  Run the Rust tests:
    ```bash
    ./strling test rust
    ```

---

## Step 5: Submit your PR

1.  Check the status of your changes:

    ```bash
    git status
    ```

    _You should see the new `.strl` file and the generated `.json` file._

2.  Commit and push:
    ```bash
    git add tests/conformance/cases/zip.strl tests/spec/zip.json
    git commit -m "feat: add US zip code conformance test"
    git push origin feat/zip-code
    ```

**Congratulations!** You've just added a portable test case that strengthens the entire STRling ecosystem.
