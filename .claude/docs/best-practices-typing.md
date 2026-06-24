# Python Best Practices: Type Checking (mypy)

**Phase 4 — Adversarial verification.** Spot-checking three critical claims:

- `TypeIs` is preferred over `TypeGuard` for most cases (confirmed: PEP 742 explicitly states this, and mypy docs echo it)
- `TypeAlias` is deprecated since Python 3.12 in favor of the `type` statement (confirmed: CPython docs say "deprecated since 3.12")
- `strict = true` flags may change between mypy releases (confirmed: pydevtools handbook explicitly notes this)

All three hold under adversarial scrutiny. Proceeding to synthesis.

---

# Python Type Annotations & mypy — Authoritative Best Practices (2024–2026)

## 1. The 2025 Landscape

Meta's Python Typing Survey 2025 [[Engineering at Meta](https://engineering.fb.com/2025/12/22/developer-tools/python-typing-survey-2025-code-quality-flexibility-typing-adoption/)] is the clearest snapshot of where the community stands:

- **86% of respondents** use type hints "always" or "often" — virtually unchanged from 2024.
- **Mypy still leads** at 58% usage, but is down from 61%; Rust-based newcomers (Pyrefly, `ty`, Zuban) now collectively hold >20% share.
- Top motivations: bug prevention, developer experience (autocomplete), and embedded documentation.
- Top pain points: untyped or incorrectly-typed third-party libraries, complexity of advanced generics, and fragmentation between type checkers.

The community consensus has shifted from "should we type?" to "how do we type well at scale?"

---

## 2. When and How to Annotate

### 2.1 Function Signatures

**Arguments: prefer abstract types.** Use `Iterable`, `Sequence`, `Mapping` (from `collections.abc`) rather than `list`, `tuple`, or `dict` — this makes functions more reusable and is explicitly recommended by the official typing best-practices guide [[typing.python.org/best_practices](https://typing.python.org/en/latest/reference/best_practices.html)].

```python
# Prefer:
def join_lines(lines: Iterable[str]) -> str:
    return "\n".join(lines)

# Avoid:
def join_lines(lines: list[str]) -> str: ...  # unnecessarily restrictive
```

**Returns: prefer concrete types.** Return `list[str]`, not `Sequence[str]` — callers benefit from knowing exactly what they get.

**`object` vs `Any` for truly universal arguments.** If a function accepts any value, `object` is almost always correct:

```python
def log(value: object) -> None:  # correct
    print(repr(value))

def bad_log(value: Any) -> None:  # propagates Any, loses safety
    print(repr(value))
```

`Any` silences all type checking for the value and everything derived from it. `object` enforces that you can only use operations valid on all Python objects.

**Return `None` explicitly.** Always annotate `-> None` on functions with no return value; omitting it lets mypy skip checking the body.

**`__init__` returns `None`.** Always annotate `def __init__(self) -> None:`.

### 2.2 Modern Syntax (Python 3.10+)

From Python 3.10, prefer:

```python
# Modern union syntax
def greet(name: str | None) -> str: ...

# Avoid the older imports-required forms
from typing import Optional, Union
def greet(name: Optional[str]) -> str: ...      # old
def greet(name: Union[str, None]) -> str: ...   # old
```

Use built-in generic aliases directly (available since Python 3.9):

```python
x: list[int] = []        # correct (3.9+)
x: dict[str, int] = {}   # correct (3.9+)

from typing import List, Dict   # only needed if supporting Python 3.8
```

If you need to support Python 3.8/3.9, use `from __future__ import annotations` at the top of every module — this defers all annotation evaluation so you can write modern syntax without runtime errors.

### 2.3 Dataclasses

`@dataclass` works naturally with type annotations. Every field declaration is simultaneously the type annotation and the dataclass field:

```python
from dataclasses import dataclass, field
from typing import ClassVar

@dataclass
class Config:
    name: str
    retries: int = 3
    tags: list[str] = field(default_factory=list)
    _instance_count: ClassVar[int] = 0   # class variable, not a field
```

Key points:
- Use `field(default_factory=...)` for mutable defaults — never `tags: list[str] = []`.
- `ClassVar[T]` marks class-level state that mypy excludes from `__init__`.
- `InitVar[T]` marks constructor-only parameters not stored as attributes.
- `@dataclass(frozen=True)` creates immutable instances; mypy will enforce no post-init assignment.
- For validation, Pydantic's `BaseModel` or `pydantic.dataclasses.dataclass` provides runtime enforcement on top of static typing.

### 2.4 TypedDict

`TypedDict` types dictionary shapes statically. The class syntax is preferred [[typing.python.org/spec/typeddict](https://typing.python.org/en/latest/spec/typeddict.html)]:

```python
from typing import TypedDict, NotRequired, Required, ReadOnly

class Movie(TypedDict):
    name: str                       # required
    year: int                       # required
    director: NotRequired[str]      # optional

class ImmutableRecord(TypedDict):
    id: int
    tags: ReadOnly[list[str]]       # field exists but list cannot be replaced
```

**`total=False` vs `NotRequired`.** Prefer fine-grained `NotRequired[T]` over `total=False` which makes *everything* optional — it is more explicit and survives inheritance better.

**Closed TypedDicts (Python 3.14 / typing_extensions).** Use `closed=True` to reject extra keys:

```python
class StrictEvent(TypedDict, closed=True):
    type: str
    payload: dict[str, object]
```

**Inheritance.** TypedDicts can inherit from each other to share common fields:

```python
class BaseEvent(TypedDict):
    id: str
    timestamp: float

class ClickEvent(BaseEvent):
    x: int
    y: int
```

**TypedDict is structural.** Two unrelated TypedDicts are compatible if their shapes match — no explicit inheritance needed.

### 2.5 Protocol

`Protocol` enables structural subtyping — any class implementing the required interface satisfies the protocol, with no inheritance needed [[typing.python.org/reference/protocols](https://typing.python.org/en/latest/reference/protocols.html)]:

```python
from typing import Protocol

class Closeable(Protocol):
    def close(self) -> None: ...

class FileHandle:
    def close(self) -> None:
        ...

def shutdown(resource: Closeable) -> None:
    resource.close()

shutdown(FileHandle())  # OK — structural match
```

**Key rules:**
- Including `Protocol` in a class body makes it a protocol; subclassing without it creates a concrete class.
- Combine protocols via multiple inheritance: `class ReadWriteable(Readable, Writable, Protocol): ...`
- Use `@runtime_checkable` only when you need `isinstance()` — it only checks attribute existence, not types or signatures, so it is not fully safe.
- For performance-critical `isinstance()` equivalents, prefer `hasattr()`.
- Use `@property` for read-only attributes in protocols to avoid invariance issues with mutable attributes.
- Protocol vs ABC: use Protocol when you don't control all implementing classes; use ABCs when you want explicit inheritance and can enforce it.

**Callback protocols** express callable shapes that `Callable[...]` cannot:

```python
class Merger(Protocol):
    def __call__(self, *items: bytes, maxlen: int | None = None) -> list[bytes]: ...
```

---

## 3. mypy Configuration

### 3.1 Config File Discovery Order

mypy searches in this order:
1. `mypy.ini`
2. `.mypy.ini`
3. `pyproject.toml` (`[tool.mypy]` section)
4. `setup.cfg`
5. `$XDG_CONFIG_HOME/mypy/config`, `~/.config/mypy/config`, `~/.mypy.ini`

[[mypy config file docs](https://mypy.readthedocs.io/en/stable/config_file.html)]

### 3.2 Strict Mode and Its Flags

`strict = true` is a shorthand that activates ~14 individual flags. **The exact set changes between mypy releases** — what is in strict today may differ in mypy 2.x. Key flags that `--strict` currently enables:

| Flag | Effect |
|---|---|
| `disallow_untyped_defs` | Every function must have complete annotations |
| `disallow_incomplete_defs` | Partial annotations (some args typed, some not) are rejected |
| `disallow_untyped_calls` | Typed code may not call untyped functions |
| `disallow_any_generics` | `list` without `list[T]` is an error |
| `disallow_any_explicit` | You may not write `Any` in annotations |
| `disallow_any_unimported` | Types from untyped imports become errors |
| `check_untyped_defs` | Check bodies of unannotated functions too |
| `warn_return_any` | Warn when returning `Any` from a typed function |
| `warn_unused_ignores` | Flag `# type: ignore` comments that suppress nothing |
| `strict_optional` | Require explicit None-handling for Optional types |
| `strict_equality` | Catch comparisons between incompatible types |

[[pydevtools strict mode guide](https://pydevtools.com/handbook/how-to/how-to-configure-mypy-strict-mode/)] [[hrekov.com mypy strict](https://hrekov.com/blog/mypy-configuration-for-strict-typing)]

### 3.3 Recommended `pyproject.toml` Setup

**New project (greenfield):**

```toml
[tool.mypy]
python_version = "3.12"
strict = true
warn_unused_configs = true

# Silence untyped third-party libraries individually — never use ignore_missing_imports globally
[[tool.mypy.overrides]]
module = ["requests.*", "boto3.*", "botocore.*"]
ignore_missing_imports = true
```

**Existing project (gradual adoption — recommended by Eightfold [[eightfold.ai](https://eightfold.ai/engineering-blog/static-type-checking-large-scale-python-codebase/)]):**

```toml
[tool.mypy]
python_version = "3.12"
# Start lenient globally
warn_return_any = true
warn_unused_configs = true
warn_unused_ignores = true
strict_optional = true
no_implicit_optional = true

# Upgrade specific well-typed modules to strict
[[tool.mypy.overrides]]
module = ["mypackage.api", "mypackage.api.*", "mypackage.models"]
strict = true

# Silence third-party stubs that are missing or broken
[[tool.mypy.overrides]]
module = ["some_untyped_lib", "some_untyped_lib.*"]
ignore_missing_imports = true
```

**Per-module override syntax in `pyproject.toml`:**
- Use `[[tool.mypy.overrides]]` (double brackets — it is a TOML array of tables).
- `module` can be a single string or a list of strings.
- Wildcards: `foo.bar.*` matches the module and all its children; `*` also matches zero components.

```toml
[[tool.mypy.overrides]]
module = ["mypackage.legacy.*", "mypackage.vendors.*"]
disallow_untyped_defs = false
ignore_errors = true

[[tool.mypy.overrides]]
module = ["mypackage.core", "mypackage.core.*"]
strict = true
```

### 3.4 Override Precedence

Highest to lowest priority:
1. Inline source-file config (`# type: ignore`, `# mypy: ...`)
2. Concrete module name matches
3. Unstructured wildcards (file order)
4. Well-structured wildcards (by specificity)
5. Command-line flags
6. Global `[tool.mypy]` settings

---

## 4. Common Pitfalls

### 4.1 `Any` Leakage

`Any` is infectious — any value derived from `Any` is also `Any`, silently disabling type checking downstream. Common sources:

**Untyped imports.** Using `--ignore-missing-imports` globally replaces the entire missing module with `Any`:

```python
import some_untyped_lib     # becomes Any
result = some_untyped_lib.do_thing()  # result: Any
output = result.process()             # output: Any — propagates silently
```

**Fix:** suppress per-module, not globally. Install stub packages from PyPI first (e.g., `types-requests`, `boto3-stubs`, `pandas-stubs`).

**Untyped function return.** A function without annotations returns `Any`:

```python
def fetch():  # returns Any
    return requests.get(url).json()

data = fetch()  # data: Any — all checking stops here
```

**Fix:** annotate, or use `--warn-return-any` to surface these automatically.

**`cast()` overuse.** `cast(T, value)` tells mypy "trust me" — it has zero runtime effect and can hide real bugs. Use it sparingly, always with a comment explaining why.

### 4.2 `reveal_type`

`reveal_type(expr)` is a mypy-special pseudo-function that prints the inferred type of any expression without running the code:

```python
x = {"key": [1, 2, 3]}
reveal_type(x)         # Revealed type: "dict[builtins.str, builtins.list[builtins.int]]"
reveal_type(x["key"])  # Revealed type: "list[builtins.int]"
```

Since Python 3.11, `reveal_type` is importable from `typing` (backported via `typing_extensions` for older Python), making it safe to leave in source code for debugging. For earlier Python: **remove all `reveal_type` calls before committing** or your code will crash at runtime.

`reveal_locals()` dumps all local variable types at a given point — useful for diagnosing complex narrowing chains.

### 4.3 `TYPE_CHECKING` Guards

Use `TYPE_CHECKING` to import types that are only needed statically:

```python
from __future__ import annotations  # makes all annotations strings (lazy eval)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mypackage.models import HeavyModel  # not imported at runtime
    from collections.abc import Generator

def process(items: Generator[HeavyModel, None, None]) -> None:
    ...
```

Common legitimate use cases:
- Breaking circular imports (`models.py` imports from `services.py` which imports from `models.py`)
- Avoiding expensive or optional imports at startup time
- Importing from stubs-only packages

Note: with `from __future__ import annotations`, all annotation strings are kept as strings and never evaluated at runtime, so forward references just work — no need for quoted strings like `"MyClass"`.

### 4.4 `@overload`

`@overload` lets you declare multiple precise signatures for a single function. Without it, you'd have to choose between `Any` (no safety) or a union return that forces callers to do unnecessary `isinstance()` checks [[mypy common issues](https://mypy.readthedocs.io/en/stable/common_issues.html)]:

```python
from typing import overload

@overload
def process(x: int) -> str: ...
@overload
def process(x: str) -> int: ...
def process(x: int | str) -> str | int:
    if isinstance(x, int):
        return str(x)
    return len(x)

reveal_type(process(42))    # str
reveal_type(process("hi"))  # int
```

Rules:
- All `@overload` variants must come before the actual implementation.
- The implementation signature is never seen by callers — it is just for the function body.
- mypy selects the first matching overload.
- `@overload` is erased at runtime, so the implementation must handle all cases.

### 4.5 `# type: ignore` Management

Use `# type: ignore[error-code]` rather than bare `# type: ignore`:

```python
result = untyped_api.call()  # type: ignore[no-untyped-call]
```

With `warn_unused_ignores = true`, mypy flags suppression comments that no longer suppress anything — this keeps your ignore list clean as mypy improves.

---

## 5. `py.typed` Marker and Distributing Typed Packages

Defined by PEP 561 [[peps.python.org/pep-0561](https://peps.python.org/pep-0561/)], the `py.typed` marker is an empty file that signals to type checkers: "this package provides type information."

### 5.1 Adding `py.typed`

1. Create an empty file at `src/mypackage/py.typed`.
2. Declare it in `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel]
include = ["src/mypackage/py.typed"]

# or with setuptools:
[tool.setuptools.package-data]
mypackage = ["py.typed"]
```

3. The marker applies recursively — all subpackages are assumed fully typed.

Without `py.typed`, type checkers silently ignore your inline annotations, treating the package as untyped (`Any`).

### 5.2 Inline Types vs Stub Files

| Approach | When to use |
|---|---|
| Inline annotations in `.py` | Default for new packages — minimal overhead |
| `.pyi` stub files alongside `.py` | When you want separate type surface from implementation (e.g., C extensions, generated code) |
| Stub-only package (`foo-stubs`) | Third-party stubs for packages you don't control (typeshed pattern) |

Type checkers always prefer `.pyi` over `.py` when both exist.

### 5.3 Partial Stubs

If type coverage is incomplete, mark the package as partial:

```
# Contents of py.typed:
partial
```

This tells type checkers to fall back to typeshed or other sources for missing annotations.

### 5.4 Type Checker Resolution Order

1. User-specified paths (`MYPYPATH`)
2. User code being checked
3. Standard library stubs (bundled)
4. Stub-only packages (`foo-stubs` on PyPI)
5. Packages with `py.typed`
6. Typeshed third-party stubs

---

## 6. Advanced Type Features (Python 3.10+)

### 6.1 `TypeAlias` and the `type` Statement

Python 3.10 added `TypeAlias` to explicitly declare type aliases (vs regular variables):

```python
from typing import TypeAlias

Vector: TypeAlias = list[float]
```

**Deprecated since Python 3.12.** Prefer the new `type` statement [[peps.python.org/pep-0695](https://peps.python.org/pep-0695/)]:

```python
type Vector = list[float]          # 3.12+
type Matrix[T] = list[list[T]]     # generic alias, 3.12+
```

For older Python, use `typing_extensions.TypeAlias`.

### 6.2 PEP 695 — New Generic Syntax (Python 3.12)

Before:
```python
from typing import Generic, TypeVar
T = TypeVar("T", bound=str)

class Container(Generic[T]):
    def unwrap(self) -> T: ...

T2 = TypeVar("T2")
def first(items: list[T2]) -> T2: ...
```

After (Python 3.12+):
```python
class Container[T: str]:
    def unwrap(self) -> T: ...

def first[T](items: list[T]) -> T: ...
```

Key advantages:
- Type parameters are scoped to the class/function — no global `TypeVar` pollution.
- Variance is inferred automatically (no `covariant=True` flags needed).
- Self-referential aliases work without quotes.
- ParamSpec and TypeVarTuple use `**P` and `*Ts` inline syntax.

### 6.3 `ParamSpec` — Preserving Decorator Signatures

`ParamSpec` (Python 3.10) captures the full parameter signature of a callable for use in decorators:

```python
from collections.abc import Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")

def logged(fn: Callable[P, T]) -> Callable[P, T]:
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        print(f"Calling {fn.__name__}")
        return fn(*args, **kwargs)
    return wrapper

@logged
def add(x: int, y: int) -> int:
    return x + y

reveal_type(add)  # (x: int, y: int) -> int  <- signature preserved!
```

Python 3.12 syntax: `def logged[**P, T](fn: Callable[P, T]) -> Callable[P, T]: ...`

### 6.4 `TypeVarTuple` — Variadic Generics

`TypeVarTuple` (Python 3.11) enables parameterization over arbitrary numbers of types, most useful for `tuple`-typed functions:

```python
from typing import TypeVarTuple, Unpack

Ts = TypeVarTuple("Ts")

def broadcast[*Ts](values: tuple[*Ts]) -> tuple[*Ts]:
    return values

reveal_type(broadcast((1, "hello", 3.0)))
# tuple[int, str, float]
```

Python 3.12 syntax uses `*Ts` directly in brackets: `def f[*Ts](...): ...`

### 6.5 Type Narrowing Patterns

Type narrowing is mypy's ability to refine a type within a conditional branch [[mypy type narrowing](https://mypy.readthedocs.io/en/latest/type_narrowing.html)]:

**Built-in narrowing:**

```python
def process(x: int | str | None) -> str:
    if x is None:
        return "nothing"
    if isinstance(x, int):
        return str(x)  # x: int here
    return x.upper()   # x: str here
```

**`TypeGuard` (Python 3.10) — one-directional narrowing:**

```python
from typing import TypeGuard

def is_str_list(val: list[object]) -> TypeGuard[list[str]]:
    return all(isinstance(x, str) for x in val)

def join(items: list[object]) -> str:
    if is_str_list(items):
        return ", ".join(items)  # items: list[str]
    return ""
    # After the if-block, items is still list[object]
```

`TypeGuard` narrows only in the `True` branch. It can narrow to a type that is not a subtype of the input (e.g., `list[object]` -> `list[str]`).

**`TypeIs` (Python 3.13, backported via `typing_extensions`) — bidirectional narrowing:**

```python
from typing import TypeIs  # or: from typing_extensions import TypeIs

def is_str(x: object) -> TypeIs[str]:
    return isinstance(x, str)

def process(x: int | str) -> None:
    if is_str(x):
        print(x.upper())  # x: str
    else:
        print(x + 1)      # x: int  <- narrowed in else branch!
```

`TypeIs` computes an intersection with the existing type on the `True` branch and excludes the narrowed type on `False`. It requires the narrowed type to be a subtype of the argument type. Per PEP 742 [[peps.python.org/pep-0742](https://peps.python.org/pep-0742/)]: **prefer `TypeIs` for most use cases**; use `TypeGuard` only when narrowing to an incompatible type.

**`assert_never` for exhaustiveness checks:**

```python
from typing import Never, assert_never
from enum import Enum

class Color(Enum):
    RED = 1
    GREEN = 2
    BLUE = 3

def describe(c: Color) -> str:
    match c:
        case Color.RED:   return "red"
        case Color.GREEN: return "green"
        case Color.BLUE:  return "blue"
        case _ as never:
            assert_never(never)  # mypy errors if any Color variant is unhandled
```

---

## 7. Balancing Strictness vs Pragmatism

From the Eightfold large-scale adoption study and the Meta survey, the consensus pattern is:

### 7.1 The Three-Tier Lifecycle

```
Untracked -> Lenient -> Strict
```

- **Untracked**: legacy files not yet in mypy's scope (exclude in config).
- **Lenient**: mypy checks the file but `disallow_untyped_defs = false` — existing untyped functions pass, but all *new* functions in PRs must be annotated (enforced by a CI diff-checker like LibCST or a simple grep).
- **Strict**: `strict = true` for that module. All functions typed, generics explicit.

### 7.2 Ordering of Flag Adoption

For existing projects, introduce flags roughly in this order (low friction -> high friction):

```toml
# Phase 1: Housekeeping (add immediately, almost never breaks)
warn_unused_configs = true
warn_unused_ignores = true
warn_redundant_casts = true

# Phase 2: Optional enforcement (low-breakage)
strict_optional = true
no_implicit_optional = true
strict_equality = true

# Phase 3: Completeness (requires annotation work)
disallow_incomplete_defs = true
check_untyped_defs = true
warn_return_any = true

# Phase 4: Full strict (highest breakage, save for last or per-module)
disallow_untyped_defs = true
disallow_untyped_calls = true
disallow_any_generics = true
```

### 7.3 Stub Packages Before `ignore_missing_imports`

Always check these first before adding `ignore_missing_imports`:

- PyPI: `types-requests`, `types-PyYAML`, `types-boto3`, `boto3-stubs`, `pandas-stubs`, `types-redis`, `types-Pillow`, etc.
- Typeshed: covers the standard library and popular packages automatically.

```bash
pip install types-requests types-PyYAML
```

### 7.4 Pragmatic Rules That Hold Up at Scale

- **Run `mypy --strict` on your public API + test fixtures. Be more permissive internally.** You catch the bugs that matter without drowning in annotations nobody reads.
- **`disallow_untyped_calls` should be last.** Enabling it too early punishes fully-typed modules that call legacy utilities, creating friction exactly where adoption should be rewarded.
- **AI-assisted typing is a complement, not a replacement.** LLM-generated annotations lack ground-truth runtime behavior. Use MonkeyType or Pyright's inference as a first draft, then review manually.
- **`# type: ignore[specific-code]` always, never bare `# type: ignore`.** Add a comment explaining why. `warn_unused_ignores` keeps the list clean.

---

## 8. 2025–2026 Recommendations at a Glance

| Topic | Current Best Practice |
|---|---|
| Python version target | 3.12+ where possible; use PEP 695 `type` / `[T]` syntax |
| Union syntax | `X \| Y` (not `Union[X, Y]`) |
| Optional | `X \| None` (not `Optional[X]`) |
| Built-in generics | `list[T]`, `dict[K, V]` (not `List`, `Dict` from `typing`) |
| Type aliases | `type Alias = ...` (3.12+) or `TypeAlias` from `typing_extensions` |
| Generics | PEP 695 `class Foo[T]:` (3.12+); old `TypeVar`/`Generic` for 3.11- |
| Narrowing | Prefer `TypeIs`; use `TypeGuard` only for incompatible narrowing |
| mypy config | `pyproject.toml [tool.mypy]`; per-module via `[[tool.mypy.overrides]]` |
| New projects | `strict = true` from day one |
| Existing projects | Lenient global + strict per-module; gate new PRs on annotation completeness |
| Untyped libraries | Install stub packages first; per-module `ignore_missing_imports` as fallback |
| Distributing types | Add `py.typed` + include in `package_data`; inline > stubs when possible |
| Callbacks | Use `Callable[P, T]` with `ParamSpec` in decorators |
| Exhaustiveness | `assert_never` in match/if-elif chains over `Enum` or `Literal` unions |

---

## Sources

- [Typing Best Practices — typing.python.org](https://typing.python.org/en/latest/reference/best_practices.html)
- [Type Narrowing — typing.python.org](https://typing.python.org/en/latest/guides/type_narrowing.html)
- [Protocols and Structural Subtyping — typing.python.org](https://typing.python.org/en/latest/reference/protocols.html)
- [TypedDict Specification — typing.python.org](https://typing.python.org/en/latest/spec/typeddict.html)
- [Distributing Type Information — typing.python.org](https://typing.python.org/en/latest/spec/distributing.html)
- [mypy Configuration File — mypy.readthedocs.io](https://mypy.readthedocs.io/en/stable/config_file.html)
- [mypy Type Narrowing — mypy.readthedocs.io](https://mypy.readthedocs.io/en/latest/type_narrowing.html)
- [mypy Common Issues — mypy.readthedocs.io](https://mypy.readthedocs.io/en/stable/common_issues.html)
- [mypy Cheat Sheet — mypy.readthedocs.io](https://mypy.readthedocs.io/en/stable/cheat_sheet_py3.html)
- [PEP 561: Distributing and Packaging Type Information](https://peps.python.org/pep-0561/)
- [PEP 695: Type Parameter Syntax (Python 3.12)](https://peps.python.org/pep-0695/)
- [PEP 742: TypeIs Narrowing (Python 3.13)](https://peps.python.org/pep-0742/)
- [Python typing module docs — docs.python.org](https://docs.python.org/3/library/typing.html)
- [How to Configure mypy Strict Mode — pydevtools.com](https://pydevtools.com/handbook/how-to/how-to-configure-mypy-strict-mode/)
- [mypy Configuration for Strict Typing — hrekov.com](https://hrekov.com/blog/mypy-configuration-for-strict-typing)
- [The Comprehensive Guide to mypy — Tushar Sadhwani / DEV](https://dev.to/tusharsadhwani/the-comprehensive-guide-to-mypy-561m)
- [Python Typing Survey 2025 — Engineering at Meta](https://engineering.fb.com/2025/12/22/developer-tools/python-typing-survey-2025-code-quality-flexibility-typing-adoption/)
- [From Zero to Type-Safe: Large-Scale Python Type Checking — Eightfold](https://eightfold.ai/engineering-blog/static-type-checking-large-scale-python-codebase/)
- [Mypy Strict Mode in Large Python Codebases — johal.in](https://johal.in/mypy-strict-mode-configuration-enforcing-type-safety-in-large-python-codebases/)

result: Delivered a thorough, multi-source research report on Python type annotations and mypy best practices (2024–2026), covering annotation styles, TypedDict/Protocol/dataclass patterns, mypy strict-mode config with pyproject.toml examples, common pitfalls (Any leakage, reveal_type, overload, TYPE_CHECKING), py.typed distribution, TypeGuard vs TypeIs, ParamSpec, TypeVarTuple, PEP 695 generic syntax, and gradual typing adoption strategies — all cited to authoritative primary sources.
