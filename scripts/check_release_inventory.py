#!/usr/bin/env python3
"""Inventory declared release APIs without importing native or optional hosts.

Python uses AST declarations; JavaScript/TypeScript uses the existing pinned
TypeScript compiler. Source-byte hashes record provenance, while comparison
uses semantic declarations so an implementation-only edit does not force a freeze.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = Path("spec/releases/0.6.0-api-inventory.json")
PYTHON_ROOTS = ("xyg", "xyg.pyplot")
REFERENCES = {
    "xyg": ["spec/api/api-examples.md", "spec/design/composition-api.md", "spec/api/export.md"],
    "xyg.pyplot": ["spec/matplotlib/compat.md", "tests/pyplot/corpus/"],
    "node": ["spec/design/host-parity.md", "packages/xy-node/test/"],
    "browser": ["spec/api/browser-wasm.md", "spec/design/browser-wasm.md", "js/src/60_entries.ts"],
}
OPERATOR_COMMANDS = (
    "hatch_build.py",
    "scripts/gen_abi_manifest.py",
    "scripts/check_release_version.py",
    "scripts/stage_node_packages.py",
    "scripts/stage_browser_package.py",
    "scripts/publish_node_packages.py",
    "scripts/check_release_inventory.py",
)

# This is an inspector, not another emitter/type declaration generator. The
# compiler resolves aliases and existing .d.ts files; no product code executes.
JS_INSPECTOR = r"""
const fs = require('node:fs');
const path = require('node:path');
const root = process.argv[1];
const {pathToFileURL} = require('node:url');
async function main() {
const apiModule = await import(pathToFileURL(path.join(root, 'node_modules/typescript/dist/api/sync/api.js')));
const astModule = await import(pathToFileURL(path.join(root, 'node_modules/typescript/dist/ast/index.js')));
const ts = {...apiModule, ...astModule};
const client = new ts.API({cwd: root});
const nodePackage = JSON.parse(fs.readFileSync(path.join(root, 'packages/xy-node/package.json')));
const entries = Object.entries(nodePackage.exports).map(([name, file]) => ({
  surface: 'node' + (name === '.' ? '' : name.slice(1)),
  file: path.resolve(root, 'packages/xy-node', typeof file === 'string' ? file : file.import),
}));
entries.push({surface: 'browser', file: path.join(root, 'js/src/60_entries.ts')});
function jsFiles(dir) {
  return fs.readdirSync(dir, {withFileTypes:true}).flatMap(entry => entry.isDirectory()
    ? jsFiles(path.join(dir, entry.name)) : entry.name.endsWith('.js') ? [path.join(dir, entry.name)] : []);
}
const snapshot = client.updateSnapshot({openProjects:[path.join(root,'js/tsconfig.json')], openFiles:[...entries.map(x => x.file),...jsFiles(path.join(root,'packages/xy-node/src'))]});
let program, checker, project;
const relative = file => path.relative(root, file).split(path.sep).join('/');
const print = node => node ? project.emitter.printNode(node).trim() : null;
const flags = 1; // TypeFormatFlags.NoTruncation
const typeOf = (symbol, location) => checker.getTypeOfSymbolAtLocation(symbol, location);
const formatType = (type, location) => checker.typeToString(type, location, flags).split(root.split(path.sep).join("/")).join("<repo>");
const calls = type => checker.getSignaturesOfType(type, ts.SignatureKind.Call).map(sig => ({
  parameters: sig.getParameters().map(p => ({name:p.name,type:formatType(checker.getTypeOfSymbol(p))})),
  returns: formatType(checker.getReturnTypeOfSignature(sig)),
}));
const params = declaration => declaration.parameters ? declaration.parameters.map(print) : null;
const visible = declaration => !declaration.name?.getText().startsWith('_')
  && !declaration.name?.getText().startsWith('#')
  && !declaration.modifiers?.some(m => m.kind === ts.SyntaxKind.PrivateKeyword || m.kind === ts.SyntaxKind.ProtectedKeyword);
function literalDefaultBindings(declaration, sourceProject = project) {
  const bindings = {};
  const visited = new Set();
  const literal = node => ts.isLiteralExpression(node)
    || [ts.SyntaxKind.TrueKeyword, ts.SyntaxKind.FalseKeyword, ts.SyntaxKind.NullKeyword].includes(node.kind)
    || ts.isPrefixUnaryExpression(node) && literal(node.operand)
    || ts.isArrayLiteralExpression(node) && node.elements.every(literal)
    || ts.isObjectLiteralExpression(node) && node.properties.every(p => ts.isPropertyAssignment(p) && literal(p.initializer));
  function visit(node) {
    if (ts.isIdentifier(node)) {
      let symbol = sourceProject.checker.getSymbolAtLocation(node);
      if (symbol?.flags & ts.SymbolFlags.Alias) symbol = sourceProject.checker.getAliasedSymbol(symbol);
      if (symbol && !visited.has(symbol.id)) {
        visited.add(symbol.id);
        for (const handle of symbol.declarations ?? []) {
          const binding = handle.resolve(sourceProject);
          const value = binding?.initializer;
          if (!value) continue;
          if (literal(value)) bindings[relative(binding.getSourceFile().fileName) + '#' + symbol.name] = sourceProject.emitter.printNode(value).trim();
          else if (ts.isIdentifier(value)) visit(value);
        }
      }
    }
    node.forEachChild(visit);
  }
  for (const parameter of declaration.parameters ?? []) {
    if (parameter.initializer) visit(parameter.initializer);
    if (!ts.isIdentifier(parameter.name)) visit(parameter.name);
  }
  return bindings;
}
function declarationContract(declaration) {
  const result = {kind: ts.SyntaxKind[declaration.kind]};
  if (declaration.parameters) result.parameters = params(declaration);
  if (declaration.type) result.returnOrFieldType = print(declaration.type);
  if (declaration.typeParameters) result.typeParameters = declaration.typeParameters.map(print);
  if (declaration.heritageClauses) result.bases = declaration.heritageClauses.map(print);
  if (declaration.modifiers) result.modifiers = declaration.modifiers.map(print).sort();
  if (ts.isTypeAliasDeclaration(declaration) || ts.isInterfaceDeclaration(declaration)) {
    result.typeDeclaration = print(declaration);
  }
  const init = declaration.initializer;
  const functionNode = init && (ts.isArrowFunction(init) || ts.isFunctionExpression(init)) ? init : declaration;
  if (functionNode !== declaration) result.parameters = params(functionNode);
  if (functionNode.parameters) result.defaultTypes = functionNode.parameters.map(p => p.initializer ? formatType(checker.getTypeAtLocation(p.initializer), p.initializer) : null);
  const bindings = literalDefaultBindings(functionNode);
  if (Object.keys(bindings).length) result.literalDefaultBindings = bindings;
  if (init && !ts.isArrowFunction(init) && !ts.isFunctionExpression(init)
      && (ts.isLiteralExpression(init) || init.kind === ts.SyntaxKind.TrueKeyword
          || init.kind === ts.SyntaxKind.FalseKeyword || init.kind === ts.SyntaxKind.NullKeyword)) {
    result.literalDefault = print(init);
  }
  return result;
}
function runtimeDefaults(declaration) {
  const file = declaration.getSourceFile().fileName;
  if (!file.endsWith('.d.ts')) return null;
  const runtimeFile = file.slice(0, -5) + '.js';
  if (!fs.existsSync(runtimeFile)) return null;
  const runtimeProject = snapshot.getDefaultProjectForFile(runtimeFile);
  const source = runtimeProject?.program.getSourceFile(runtimeFile);
  if (!source) return null;
  const name = declaration.name?.getText();
  const target = source.statements.flatMap(s => ts.isVariableStatement(s) ? [...s.declarationList.declarations] : [s])
    .find(s => s.name?.getText() === name);
  if (!target) return null;
  if (ts.isClassDeclaration(target)) return {parameters: target.members.filter(visible)
    .filter(m => m.parameters).map(m => ({name: m.name?.getText() ?? 'constructor', parameters: params(m), literalDefaultBindings: literalDefaultBindings(m, runtimeProject)}))};
  const functionNode = target.initializer && (ts.isArrowFunction(target.initializer) || ts.isFunctionExpression(target.initializer)) ? target.initializer : target;
  return {parameters: params(functionNode), literalDefaultBindings: literalDefaultBindings(functionNode, runtimeProject)};
}
const surfaces = {};
const gaps = [];
for (const entry of entries) {
  project = snapshot.getDefaultProjectForFile(entry.file);
  program = project.program; checker = project.checker;
  const source = program.getSourceFile(entry.file);
  const moduleSymbol = source && checker.getSymbolAtLocation(source);
  if (!moduleSymbol) throw new Error('No compiler module for ' + entry.file);
  surfaces[entry.surface] = checker.getExportsOfModule(moduleSymbol).map(exp => {
    const target = exp.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(exp) : exp;
    const declarations = (target.declarations ?? []).map(handle => handle.resolve(project)).filter(Boolean);
    const declaration = declarations[0];
    if (!declaration) {
      gaps.push(entry.surface + '.' + exp.name + ': no local declaration');
      return {name: exp.name, kind: 'unresolved', status: 'unclassified'};
    }
    const type = typeOf(target, declaration);
    const result = {
      name: exp.name, source: relative(declaration.getSourceFile().fileName), reference: relative(declaration.getSourceFile().fileName) + '#' + target.name,
      status: target.getJsDocTags(checker).some(tag => tag.name === 'experimental') ? 'experimental' : 'unclassified',
      declarations: declarations.map(declarationContract), signatures: calls(type),
    };
    const runtime = runtimeDefaults(declaration);
    if (runtime?.parameters) result.runtimeParameters = runtime.parameters;
    if (runtime?.literalDefaultBindings && Object.keys(runtime.literalDefaultBindings).length) result.runtimeDefaultBindings = runtime.literalDefaultBindings;
    if (ts.isClassDeclaration(declaration)) {
      result.members = declaration.members.filter(visible).map(member => {
        const symbol = member.name && checker.getSymbolAtLocation(member.name);
        return {name: member.name?.getText() ?? 'constructor', ...declarationContract(member),
          ...(symbol ? {type: formatType(typeOf(symbol, member), member), signatures: calls(typeOf(symbol, member))} : {})};
      });
    } else if (!result.signatures.length && !ts.isInterfaceDeclaration(declaration) && !ts.isTypeAliasDeclaration(declaration)) {
      result.type = formatType(type, declaration);
    }
    if (result.signatures.some(value => /\bany\b/.test(JSON.stringify(value)))) gaps.push(entry.surface + '.' + exp.name + ': declaration contains any');
    return result;
  }).sort((a, b) => a.name.localeCompare(b.name));
}
const sources = [...new Set(snapshot.getProjects().flatMap(p => p.program.getSourceFileNames()))]
  .filter(file => file.startsWith(root + path.sep) && !file.includes(path.sep + 'node_modules' + path.sep))
  .map(relative).sort();
snapshot.dispose(); client.close();
process.stdout.write(JSON.stringify({surfaces, sources, gaps: [...new Set(gaps)].sort(), typescript: require(path.join(root,'node_modules/typescript/package.json')).version}));
}
main().catch(error => { console.error(error.message); process.exit(1); });
"""


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class PythonInventory:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.sources: dict[str, ast.Module] = {}
        self.gaps: set[str] = set()

    def module(self, name: str) -> tuple[Path, ast.Module]:
        path = self.root / "python" / name.replace(".", "/")
        path = path / "__init__.py" if path.is_dir() else path.with_suffix(".py")
        relative = path.relative_to(self.root).as_posix()
        if relative not in self.sources:
            self.sources[relative] = ast.parse(path.read_text(), filename=relative)
        return path, self.sources[relative]

    @staticmethod
    def bindings(tree: ast.Module) -> dict[str, ast.AST]:
        result: dict[str, ast.AST] = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                result[node.name] = node
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        result[target.id] = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                result[node.target.id] = node
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    result[alias.asname or alias.name] = node
        return result

    def symbol(self, module: str, name: str, seen: frozenset[str] = frozenset()) -> dict[str, Any]:
        key = f"{module}.{name}"
        if key in seen:
            return {"kind": "reference", "target": key}
        path, tree = self.module(module)
        bindings = self.bindings(tree)
        node = bindings.get(name)
        reference = f"{path.relative_to(self.root).as_posix()}#{name}"
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            overloads = [
                item
                for item in tree.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name
            ]
            return {
                "kind": "callable",
                "reference": reference,
                "signatures": [self.function(item, bindings) for item in overloads],
            }
        if isinstance(node, ast.ClassDef):
            members = {}
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                    not child.name.startswith("_")
                    or (child.name.startswith("__") and child.name.endswith("__"))
                ):
                    members.setdefault(child.name, []).append(self.function(child, bindings))
                elif (
                    isinstance(child, ast.AnnAssign)
                    and isinstance(child.target, ast.Name)
                    and not child.target.id.startswith("_")
                ):
                    members[child.target.id] = {
                        "annotation": ast.unparse(child.annotation),
                        "default": ast.unparse(child.value) if child.value else None,
                    }
                elif isinstance(child, ast.Assign):
                    for target in child.targets:
                        if isinstance(target, ast.Name) and not target.id.startswith("_"):
                            members[target.id] = {"value": ast.unparse(child.value)}
            bases = [ast.unparse(base) for base in node.bases]
            if bases:
                self.gaps.add(f"{key}: inherited members are referenced by base, not expanded")
            return {
                "kind": "class",
                "reference": reference,
                "bases": bases,
                "decorators": [ast.unparse(item) for item in node.decorator_list],
                "members": members,
                "fieldOrder": [
                    child.target.id
                    for child in node.body
                    if isinstance(child, ast.AnnAssign)
                    and isinstance(child.target, ast.Name)
                    and not child.target.id.startswith("_")
                ],
            }
        if isinstance(node, ast.ImportFrom):
            alias = next(item for item in node.names if (item.asname or item.name) == name)
            package = module if path.name == "__init__.py" else module.rpartition(".")[0]
            target = (
                importlib.util.resolve_name("." * node.level + (node.module or ""), package)
                if node.level
                else node.module or ""
            )
            if target.startswith("xyg"):
                try:
                    return self.symbol(target, alias.name, seen | {key})
                except FileNotFoundError:
                    self.gaps.add(
                        f"{key}: reexported module {target}.{alias.name} has no symbol declaration"
                    )
            return {"kind": "reexport", "reference": reference, "target": f"{target}.{alias.name}"}
        if isinstance(node, ast.AnnAssign):
            return {
                "kind": "attribute",
                "reference": reference,
                "annotation": ast.unparse(node.annotation),
                "default": ast.unparse(node.value) if node.value else None,
            }
        if node is not None:
            return {"kind": "value", "reference": reference, "expression": ast.unparse(node)}
        if name == "__version__":
            return {
                "kind": "attribute",
                "reference": reference,
                "annotation": "str",
                "authority": "installed xyg distribution metadata",
            }
        self.gaps.add(f"{key}: runtime or generated export has no static declaration")
        return {"kind": "unresolved", "reference": reference}

    @staticmethod
    def function(
        node: ast.FunctionDef | ast.AsyncFunctionDef, bindings: dict[str, ast.AST] | None = None
    ) -> dict[str, Any]:
        bound_defaults = {}
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            for child in ast.walk(default) if default is not None else []:
                value = (bindings or {}).get(child.id) if isinstance(child, ast.Name) else None
                if isinstance(value, ast.AnnAssign):
                    value = value.value
                if value is not None:
                    try:
                        ast.literal_eval(value)
                        bound_defaults[child.id] = ast.unparse(value)
                    except (ValueError, TypeError):
                        pass
        return {
            "literalDefaultBindings": bound_defaults,
            "parameters": ast.unparse(node.args),
            "returns": ast.unparse(node.returns) if node.returns else None,
            "async": isinstance(node, ast.AsyncFunctionDef),
            "decorators": [ast.unparse(item) for item in node.decorator_list],
            "raisedTypes": sorted(
                {
                    ast.unparse(item.exc.func if isinstance(item.exc, ast.Call) else item.exc)
                    for item in ast.walk(node)
                    if isinstance(item, ast.Raise) and item.exc is not None
                }
            ),
        }

    def surface(self, name: str) -> list[dict[str, Any]]:
        path, tree = self.module(name)
        bindings = self.bindings(tree)
        exports = ast.literal_eval(bindings["__all__"])
        lazy = ast.literal_eval(bindings["_EXPORTS"]) if "_EXPORTS" in bindings else {}
        result = []
        for symbol in sorted(exports):
            target = importlib.util.resolve_name(lazy[symbol], name) if symbol in lazy else name
            item = {
                "name": symbol,
                "visibility": "public",
                "status": "unclassified",
                **self.symbol(target, symbol),
            }
            result.append(item)
        return result


def inspect_javascript(root: Path) -> dict[str, Any]:
    if not (root / "node_modules/typescript/dist/api/sync/api.js").is_file():
        raise ValueError("API inventory needs the pinned TypeScript compiler: run npm ci")
    result = subprocess.run(
        ["node", "-e", JS_INSPECTOR, str(root)],
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    if result.returncode:
        raise ValueError(f"TypeScript API inspection failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def environment_inventory(root: Path, python: PythonInventory) -> list[dict[str, Any]]:
    variables: dict[str, dict[str, Any]] = {}
    paths = [
        *sorted((root / "python/xyg").rglob("*.py")),
        root / "hatch_build.py",
    ]
    for path in paths:
        relative = path.relative_to(root).as_posix()
        text = path.read_text()
        tree = ast.parse(text)
        constants = {
            target.id: node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        lookups = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and node.args
                and ast.unparse(node.func) in {"os.environ.get", "os.getenv"}
            ):
                arg = node.args[0]
                key = (
                    arg.value
                    if isinstance(arg, ast.Constant)
                    else constants.get(arg.id)
                    if isinstance(arg, ast.Name)
                    else None
                )
                if isinstance(key, str) and re.fullmatch(r"XYG?_[A-Z0-9_]+", key):
                    lookups.append((key, ast.unparse(node.args[1]) if len(node.args) > 1 else None))
        # Browser discovery loops over these documented names rather than
        # passing their constants directly into environ.get().
        lookups.extend(
            (value, None)
            for key, value in constants.items()
            if key.endswith("_ENV") and re.fullmatch(r"XYG?_[A-Z0-9_]+", value)
        )
        for name, default in lookups:
            item = variables.setdefault(
                name,
                {
                    "name": name,
                    "visibility": "internal" if "ABI_TRACE" in name else "public-operator",
                    "status": "internal" if "ABI_TRACE" in name else "unclassified",
                    "lookups": [],
                },
            )
            item["lookups"].append({"source": relative, "default": default})
            python.sources.setdefault(relative, tree)
    for path in sorted((root / "packages/xy-node/src").rglob("*.js")):
        text = path.read_text()
        for name in sorted(set(re.findall(r"(?:process\.env|\benv)\.(XYG?_[A-Z0-9_]+)", text))):
            item = variables.setdefault(
                name,
                {
                    "name": name,
                    "visibility": "internal" if "ABI_TRACE" in name else "public-operator",
                    "status": "internal" if "ABI_TRACE" in name else "unclassified",
                    "lookups": [],
                },
            )
            item["lookups"].append(
                {"source": path.relative_to(root).as_posix(), "default": "see source expression"}
            )
    for crate in ("xyg-engine", "xyg-core"):
        for path in sorted((root / "crates" / crate / "src").rglob("*.rs")):
            if "bin" in path.parts:
                continue
            text = re.split(r"#\[cfg\(test\)\]\s*mod\s+\w+", path.read_text(), maxsplit=1)[0]
            for match in re.finditer(
                r'(?:std::)?env::var(?:_os)?\("((?:XYG?_[A-Z0-9_]+)|CODSPEED_ENV)"\)', text
            ):
                name = match.group(1)
                item = variables.setdefault(
                    name,
                    {
                        "name": name,
                        "visibility": "internal" if name == "CODSPEED_ENV" else "public-operator",
                        "status": "internal" if name == "CODSPEED_ENV" else "unclassified",
                        "lookups": [],
                    },
                )
                line = text[
                    text.rfind("\n", 0, match.start()) + 1 : text.find("\n", match.end())
                    if "\n" in text[match.end() :]
                    else len(text)
                ]
                item["lookups"].append(
                    {
                        "source": path.relative_to(root).as_posix(),
                        "expression": " ".join(line.split()),
                        "default": "see Rust expression",
                    }
                )
    return [variables[name] for name in sorted(variables)]


def collect(root: Path = ROOT) -> dict[str, Any]:
    python = PythonInventory(root)
    surfaces = {
        name: {"references": REFERENCES[name], "symbols": python.surface(name)}
        for name in PYTHON_ROOTS
    }
    sources = set(python.sources)
    js = inspect_javascript(root)
    for name, symbols in js["surfaces"].items():
        surfaces[name] = {
            "references": REFERENCES["browser" if name == "browser" else "node"],
            "symbols": symbols,
        }
    sources.update(js["sources"])
    environments = environment_inventory(root, python)
    sources.update(python.sources)
    sources.update(item["source"] for entry in environments for item in entry["lookups"])
    manifest_path = root / "spec/abi/xyg-abi.json"
    manifest = json.loads(manifest_path.read_text())
    abi = {
        "visibility": "internal",
        "status": "internal",
        "compatibility": "exact-match-co-versioned",
        "authority": "spec/abi/xyg-abi.json",
        "header": "spec/abi/xyg.h",
        "generator": "scripts/gen_abi_manifest.py",
        "abiVersion": manifest["abi_version"],
        "signatureSha256": manifest["signature_sha256"],
        "manifestContractSha256": digest(manifest),
        "symbols": [item["name"] for item in manifest["symbols"]],
    }
    project = tomllib.loads((root / "pyproject.toml").read_text())
    packages = {
        name: {
            key: value
            for key, value in json.loads((root / name).read_text()).items()
            if key in {"name", "exports", "main", "type", "types", "typings"}
        }
        for name in ("packages/xy-node/package.json", "packages/xy-client/package.json")
    }
    commands = []
    for name in OPERATOR_COMMANDS:
        tree = ast.parse((root / name).read_text())
        options = [
            {
                "arguments": [ast.unparse(arg) for arg in node.args],
                "options": {
                    kw.arg: ast.unparse(kw.value)
                    for kw in node.keywords
                    if kw.arg not in {"help", "description", "epilog"}
                },
            }
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
        ]
        commands.append(
            {
                "source": name,
                "visibility": "repository-operator",
                "status": "internal",
                "arguments": options,
            }
        )
    sources.update(name for refs in REFERENCES.values() for name in refs if (root / name).is_file())
    sources.update(
        (
            "packages/xy-node/README.md",
            "spec/process/production-readiness.md",
            "package-lock.json",
            "js/tsconfig.json",
            "python/xyg/py.typed",
        )
    )
    sources.update(
        (
            *OPERATOR_COMMANDS,
            "spec/abi/xyg-abi.json",
            "spec/abi/xyg.h",
            "spec/wasm/abi.json",
            "pyproject.toml",
            *packages,
        )
    )
    contracts = {
        "surfaces": surfaces,
        "cAbi": abi,
        "wasmAbi": {
            "status": "internal",
            "compatibility": "exact-match-co-versioned",
            "authority": "spec/wasm/abi.json",
            "manifestContractSha256": digest(json.loads((root / "spec/wasm/abi.json").read_text())),
        },
        "packageEntrypoints": packages,
        "installedCli": project.get("project", {}).get("scripts", {}),
        "buildHooks": project["tool"]["hatch"]["build"]["targets"],
        "operatorCommands": commands,
        "environmentVariables": environments,
    }
    definitions = {}
    node_readme = (root / "packages/xy-node/README.md").read_text()
    current_posture = (root / "spec/process/production-readiness.md").read_text()
    host_parity = (root / "spec/design/host-parity.md").read_text()
    loader_stable = (
        "with a stable `code` (`NATIVE_ERROR_CODES`)" in host_parity
        and "stable diagnostic" in host_parity
    )
    node_stable = bool(
        re.search(r"exports a stable\s+`createEngine\(\)` / chart-builder API", node_readme)
    )
    python_experimental = bool(
        re.search(
            r"composition API, chart-type set, visual styling\s+surface remain experimental",
            current_posture,
        )
    )
    chart_builders = {item["name"] for item in js["surfaces"].get("node/charts", [])}
    for surface_name, surface in surfaces.items():
        for index, symbol in enumerate(surface["symbols"]):
            classification = symbol.get("status", "unclassified")
            evidence = None
            if surface_name == "xyg" and python_experimental:
                classification = "experimental"
                evidence = "spec/process/production-readiness.md#current-contract"
            elif (
                node_stable
                and surface_name.startswith("node")
                and symbol["name"]
                in chart_builders
                | {
                    "createEngine",
                    "figure",
                }
            ):
                classification = "stable"
                evidence = "packages/xy-node/README.md#exports"
            elif (
                loader_stable
                and surface_name.startswith("node")
                and symbol["name"]
                in {
                    "NATIVE_ERROR_CODES",
                    "LOAD_ERROR_CODES",
                }
            ):
                classification = "stable"
                evidence = "spec/design/host-parity.md#0-three-runtime-surfaces-product-wide"
            reference = symbol.get("reference", f"{surface_name}#{symbol['name']}")
            definition = {
                key: value
                for key, value in symbol.items()
                if key not in {"name", "visibility", "status", "reference"}
            }
            if reference in definitions and definitions[reference] != definition:
                raise ValueError(f"inconsistent compiler declarations for {reference}")
            definitions[reference] = definition
            surface["symbols"][index] = {
                "name": symbol["name"],
                "visibility": "public",
                "status": classification,
                "definition": reference,
                **({"classificationEvidence": evidence} if evidence else {}),
            }
    contracts["definitions"] = dict(sorted(definitions.items()))
    # Build target include/exclude inventories are packaging policy; keep them
    # once in pyproject, not as an accidental public callable contract.
    contracts["buildHooks"] = {
        name: data.get("hooks", {})
        for name, data in contracts["buildHooks"].items()
        if data.get("hooks")
    }
    gaps = sorted(
        {
            *python.gaps,
            *js["gaps"],
            "Candidate stable/experimental classification remains unapproved for records marked unclassified.",
            "Error wording, value-dependent defaults, callback effects, runtime prototype augmentation and lifecycle behavior require the linked conformance/spec evidence; declarations alone do not qualify them.",
            "Indirect returned objects, non-root Python submodules, and inherited external APIs are not exhaustively expanded.",
            "Computed environment-variable names beyond documented constant discovery require manual review.",
        }
    )
    return {
        "schema": "xyg.release-api-inventory/v1",
        "releaseLine": "0.6.0",
        "acceptance": "preparation-only-not-a-freeze",
        "sourceProvenance": {
            "meaning": "generation-time working-tree bytes; source hashes may differ after body-only edits",
            "baseCommit": subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            or None,
        },
        "contracts": contracts,
        "contractSha256": digest(contracts),
        "sourceSha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(sources)
        },
        "inspector": {"python": "stdlib ast", "typescript": js["typescript"]},
        "gaps": gaps,
    }


def compare(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    if expected.get("schema") != actual.get("schema"):
        return ["API inventory schema differs"]
    if digest(expected.get("contracts")) != expected.get("contractSha256"):
        return ["API inventory snapshot contract hash is invalid"]
    if expected.get("contractSha256") != actual.get("contractSha256"):
        changed = sorted(
            key
            for key in actual["contracts"]
            if expected.get("contracts", {}).get(key) != actual["contracts"][key]
        )
        return [
            f"API contract drift: {', '.join(changed)}; review and run python3 scripts/check_release_inventory.py --write"
        ]
    return []


def render(value: dict[str, Any]) -> str:
    """Keep shared-definition records on individual lines without megabytes of padding."""

    def encode(item: Any, depth: int) -> str:
        if isinstance(item, dict) and depth < 3:
            return (
                "{\n"
                + ",\n".join(
                    " " * (depth + 1) + json.dumps(key) + ":" + encode(part, depth + 1)
                    for key, part in sorted(item.items())
                )
                + "\n"
                + " " * depth
                + "}"
            )
        return json.dumps(item, sort_keys=True, separators=(",", ":"))

    return encode(value, 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="replace the preparation snapshot after reviewing contract changes",
    )
    parser.add_argument(
        "--require-classified",
        action="store_true",
        help="also reject public symbols without a documented stability classification",
    )
    args = parser.parse_args(argv)
    try:
        actual = collect()
        unclassified = [
            f"{surface}.{symbol['name']}"
            for surface, data in actual["contracts"]["surfaces"].items()
            for symbol in data["symbols"]
            if symbol["status"] == "unclassified"
        ]
        unclassified.extend(
            f"environment.{entry['name']}"
            for entry in actual["contracts"]["environmentVariables"]
            if entry["status"] == "unclassified"
        )
        if args.require_classified and unclassified:
            raise ValueError(
                f"{len(unclassified)} public entries remain unclassified, including {', '.join(unclassified[:5])}"
            )
        path = ROOT / SNAPSHOT
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render(actual) + "\n")
            print(f"Wrote {SNAPSHOT}; preparation only, {len(actual['gaps'])} explicit review gaps")
            return 0
        expected = json.loads(path.read_text())
        errors = compare(expected, actual)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        stale = [
            name
            for name, value in actual["sourceSha256"].items()
            if expected.get("sourceSha256", {}).get(name) != value
        ]
        print(
            "API declarations match the preparation inventory; acceptance/classification gaps remain explicit"
        )
        if stale:
            print(
                f"{len(stale)} generation-time source hashes differ; semantic compatibility does not establish an exact-byte freeze"
            )
        return 0
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(f"API inventory failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
