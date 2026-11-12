# STRling PHP adapter

STRling 4.0.0 is not publicly published. Public installation commands describe
the proposed separately authorized release. Candidate tests use staged artifacts.
See the [support matrix](../../docs/support-matrix.md) for exact supported scopes.

This package is a thin PHP 8.2+ projection of the canonical STRling compiler. It uses the PHP FFI extension to call a caller-selected `strling.c-abi` version 1 library. It owns request construction, host data projection, and native lifecycle only; no PHP parser, semantic model, validator, target planner, or emitter remains.

The adapter is a provisional Preview candidate during the Fourth Edition migration. This is not a publication or permanent support-tier promise.

## Requirements

-   PHP `>= 8.2, < 9.0` with `ext-ffi` and `ext-json`
-   a compatible native STRling library chosen by the application

## Use

Pass the authenticated absolute native-library path as the first program argument.
Save the program at the Composer project root after installing the package and its
declared dependencies; `vendor/autoload.php` belongs to that consumer project.

```php
<?php

require __DIR__ . '/vendor/autoload.php';

use STRling\Requests;
use STRling\Stdlib;
use STRling\STRling;

$client = STRling::loadNative($argv[1] ?? throw new RuntimeException('pass the authenticated absolute native path'));
$result = $client->compile(Requests::sourceCompileRequest('semantic strling 1.0; case sensitive; pattern text "hello";'));

if ($result['outcome'] !== 'succeeded') throw new RuntimeException(json_encode($result));

$step = Stdlib::email('root');
$builder = Requests::simplyBuilderRequest([$step], 'root');
$simplyResult = $client->simplyCompile($builder);

if ($simplyResult['status'] !== 'success' || $simplyResult['compile_result']['outcome'] !== 'succeeded')
    throw new RuntimeException(json_encode($simplyResult));
$client->close();
```

Generated helpers record lexical-shape recipes; they do not promise semantic validity. The adapter rejects relative or missing paths, disabled FFI, ABI mismatch, missing symbols, malformed or oversized transport, duplicate JSON properties, release failure, and use after close. There is no ambient loading or fallback compiler.

See the [canonical interop contract](../../spec/interop/1.0/README.md) and the [migration record](../../docs/migration/dynamic-language-adapter-migration.md).

## Proposed public installation

After separately authorized publication, the exact proposed coordinate is:

```bash
git clone --branch php-v4.0.0 --single-branch https://github.com/strling-lang/strling.git
```

Install from the authenticated `strling/bindings/php` subtree with Composer, then run the program from its consumer project root. PHP FFI must permit native calls; the bounded example runner uses `php -d ffi.enable=1 example.php <absolute-native-path>`. Do not infer a Packagist upload from this governed Git route.
