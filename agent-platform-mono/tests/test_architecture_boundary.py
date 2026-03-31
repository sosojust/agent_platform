import ast
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).parent.parent


def check_imports_in_dir(directory: pathlib.Path, forbidden_prefixes: tuple[str, ...]) -> list[str]:
    violations = []
    if not directory.exists():
        return violations

    for filepath in directory.rglob("*.py"):
        try:
            content = filepath.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(filepath))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(forbidden_prefixes):
                            violations.append(f"{filepath.relative_to(PROJECT_ROOT)} imports {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith(forbidden_prefixes):
                        violations.append(f"{filepath.relative_to(PROJECT_ROOT)} imports from {node.module}")
        except SyntaxError:
            pass
        except Exception as e:
            violations.append(f"Error parsing {filepath.relative_to(PROJECT_ROOT)}: {e}")

    return violations


def test_core_does_not_import_domain_agents() -> None:
    """确保 core/ 目录下的核心基建代码不会反向依赖 domain_agents/ 下的业务代码"""
    core_dir = PROJECT_ROOT / "core"
    violations = check_imports_in_dir(core_dir, ("domain_agents",))
    assert not violations, f"Architecture boundary violation in core/: \n" + "\n".join(violations)


def test_shared_does_not_import_domain_agents() -> None:
    """确保 shared/ 目录下的共享代码不会反向依赖 domain_agents/ 下的业务代码"""
    shared_dir = PROJECT_ROOT / "shared"
    violations = check_imports_in_dir(shared_dir, ("domain_agents",))
    assert not violations, f"Architecture boundary violation in shared/: \n" + "\n".join(violations)


def test_shared_does_not_import_core() -> None:
    """确保 shared/ 是最底层的模块，不应该依赖 core/"""
    shared_dir = PROJECT_ROOT / "shared"
    violations = check_imports_in_dir(shared_dir, ("core", "domain_agents"))
    assert not violations, f"Architecture boundary violation in shared/: \n" + "\n".join(violations)
