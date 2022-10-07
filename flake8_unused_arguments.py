import ast
import optparse
from ast import NodeVisitor, Store
from typing import Iterable, List, Tuple, Union

import flake8.options.manager


FunctionTypes = Union[ast.AsyncFunctionDef, ast.FunctionDef, ast.Lambda]
LintResult = Tuple[int, int, str, str]

MAGIC_METHODS = {
        "__del__",
        "__repr__",
        "__str__",
        "__bytes__",
        "__format__",
        "__lt__",
        "__le__",
        "__eq__",
        "__ne__",
        "__gt__",
        "__ge__",
        "__hash__",
        "__bool__",
        "__getattr__",
        "__getattribute__",
        "__setattr__",
        "__delattr__",
        "__dir__",
        "__instancecheck__",
        "__subclasscheck__",
        "__class_getitem__",
        "__len__",
        "__length_hint__",
        "__getitem__",
        "__setitem__",
        "__delitem__",
        "__missing__",
        "__iter__",
        "__reversed__",
        "__contains__",
        "__add__",
        "__sub__",
        "__mul__",
        "__matmul__",
        "__truediv__",
        "__floordiv__",
        "__mod__",
        "__divmod__",
        "__pow__",
        "__lshift__",
        "__rshift__",
        "__and__",
        "__xor__",
        "__or__",
        "__radd__",
        "__rsub__",
        "__rmul__",
        "__rtruediv__",
        "__rfloordev__",
        "__rmod__",
        "__rdivmod__",
        "__rpow__",
        "__rlshift__",
        "__rrshift__",
        "__rand__",
        "__rxor__",
        "__ror__",
        "__iadd__",
        "__isub__",
        "__imul__",
        "__imatmul__",
        "__itruediv__",
        "__ifloordiv__",
        "__imod__",
        "__ipow__",
        "__ilshift__",
        "__irshift__",
        "__iand__",
        "__ixor__",
        "__ior__",
        "__neg__",
        "__pos__",
        "__abs__",
        "__invert__",
        "__complex__",
        "__int__",
        "__float__",
        "__index__",
        "__trunc__",
        "__floor__",
        "__ceil__",
        "__enter__",
        "__exit__",
        "__await__",
        "__aiter__",
        "__anext__",
        "__aenter__",
        "__aexit__",
        }


class Plugin:
    name = "flake8-unused-arguments"
    version = "0.0.8"

    ignore_abstract = False
    ignore_overload = False
    ignore_magic = False
    ignore_stubs = False
    ignore_variadic_names = False

    def __init__(self, tree: ast.Module):
        self.tree = tree

    @classmethod
    def add_options(cls, option_manager: flake8.options.manager.OptionManager) -> None:
        option_manager.add_option(
            "--unused-arguments-ignore-abstract-functions",
            action="store_true",
            parse_from_config=True,
            default=cls.ignore_abstract,
            dest="unused_arguments_ignore_abstract_functions",
            help="If provided, then unused arguments for functions decorated with abstractmethod will be ignored.",
        )

        option_manager.add_option(
            "--unused-arguments-ignore-overload-functions",
            action="store_true",
            parse_from_config=True,
            default=cls.ignore_overload,
            dest="unused_arguments_ignore_overload_functions",
            help="If provided, then unused arguments for functions decorated with overload will be ignored.",
        )

        option_manager.add_option(
            "--unused-arguments-ignore-magic-methods",
            action="store_true",
            parse_from_config=True,
            default=cls.ignore_magic,
            dest="unused_arguments_ignore_magic_methods",
            help="If provided, then unused arguments for magic methods will be ignored.",
        )

        option_manager.add_option(
            "--unused-arguments-ignore-stub-functions",
            action="store_true",
            parse_from_config=True,
            default=cls.ignore_stubs,
            dest="unused_arguments_ignore_stub_functions",
            help="If provided, then unused arguments for functions that are only a pass statement will be ignored.",
        )

        option_manager.add_option(
            "--unused-arguments-ignore-variadic-names",
            action="store_true",
            parse_from_config=True,
            default=cls.ignore_variadic_names,
            dest="unused_arguments_ignore_variadic_names",
            help="If provided, then unused *args and **kwargs won't produce warnings.",
        )

    @classmethod
    def parse_options(cls, options: optparse.Values) -> None:
        cls.ignore_abstract = options.unused_arguments_ignore_abstract_functions
        cls.ignore_overload = options.unused_arguments_ignore_overload_functions
        cls.ignore_magic = options.unused_arguments_ignore_magic_methods
        cls.ignore_stubs = options.unused_arguments_ignore_stub_functions
        cls.ignore_variadic_names = options.unused_arguments_ignore_variadic_names

    def run(self) -> Iterable[LintResult]:
        finder = FunctionFinder()
        finder.visit(self.tree)

        for function in finder.functions:
            decorator_names = set(get_decorator_names(function))
            # ignore abtractmethods, it's not a surprise when they're empty
            if self.ignore_abstract and "abstractmethod" in decorator_names:
                continue
            if self.ignore_overload and "overload" in decorator_names:
                continue
            if self.ignore_magic and function.name in MAGIC_METHODS:
                continue

            # ignore stub functions
            if self.ignore_stubs and is_stub_function(function):
                continue

            for i, argument in get_unused_arguments(function):
                name = argument.arg
                if self.ignore_variadic_names:
                    if function.args.vararg and function.args.vararg.arg == name:
                        continue
                    if function.args.kwarg and function.args.kwarg.arg == name:
                        continue

                # ignore self or whatever the first argument is for a classmethod
                if i == 0 and (name == "self" or "classmethod" in decorator_names):
                    continue

                line_number = argument.lineno
                offset = argument.col_offset

                if name.startswith("_"):
                    error_code = "U101"
                else:
                    error_code = "U100"

                text = "{error_code} Unused argument '{name}'".format(
                    error_code=error_code, name=name
                )
                check = "unused argument"
                yield (line_number, offset, text, check)


def get_unused_arguments(function: FunctionTypes) -> List[Tuple[int, ast.arg]]:
    """Generator that yields all of the unused arguments in the given function."""
    arguments = list(enumerate(get_arguments(function)))

    class NameFinder(NodeVisitor):
        def visit_Name(self, name: ast.Name) -> None:
            nonlocal arguments
            if isinstance(name.ctx, Store):
                return

            arguments = [(arg_index, arg) for arg_index, arg in arguments if arg.arg != name.id]

    NameFinder().visit(function)

    return arguments


def get_arguments(function: FunctionTypes) -> List[ast.arg]:
    """Get all of the argument names of the given function."""
    args = function.args

    ordered_arguments: List[ast.arg] = []

    # plain old args
    ordered_arguments.extend(args.args)

    # *arg name
    if args.vararg is not None:
        ordered_arguments.append(args.vararg)

    # *, key, word, only, args
    ordered_arguments.extend(args.kwonlyargs)

    # **kwarg name
    if args.kwarg is not None:
        ordered_arguments.append(args.kwarg)

    return ordered_arguments


def get_decorator_names(function: FunctionTypes) -> Iterable[str]:
    if isinstance(function, ast.Lambda):
        return

    for decorator in function.decorator_list:
        if isinstance(decorator, ast.Name):
            yield decorator.id
        elif isinstance(decorator, ast.Attribute):
            yield decorator.attr
        elif isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Name):
                yield decorator.func.id
            else:
                yield decorator.func.attr  # type: ignore
        else:
            assert False, decorator


def is_stub_function(function: FunctionTypes) -> bool:
    if isinstance(function, ast.Lambda):
        return isinstance(function.body, ast.Ellipsis)

    statement = function.body[0]
    if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Str):
        if len(function.body) > 1:
            # first statement is a docstring, let's skip it
            statement = function.body[1]
        else:
            # it's a function with only a docstring, that's a stub
            return True

    if isinstance(statement, ast.Pass):
        return True
    if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Ellipsis):
        return True

    if isinstance(statement, ast.Raise):
        if (
            isinstance(statement.exc, ast.Call)
            and statement.exc.func.id == "NotImplementedError"  # type: ignore
        ):
            return True

        elif (
            isinstance(statement.exc, ast.Name)
            and statement.exc.id == "NotImplementedError"
        ):
            return True

    return False


class FunctionFinder(NodeVisitor):
    functions: List[FunctionTypes]

    def __init__(self) -> None:
        super().__init__()
        self.functions = []

    def visit_AsyncFunctionDef(self, function: ast.AsyncFunctionDef) -> None:
        self.functions.append(function)

    def visit_FunctionDef(self, function: ast.FunctionDef) -> None:
        self.functions.append(function)

    def visit_Lambda(self, function: ast.Lambda) -> None:
        self.functions.append(function)
