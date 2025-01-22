import asyncio
import types
import typing
from argparse import (
    ArgumentDefaultsHelpFormatter,
    ArgumentParser,
    BooleanOptionalAction,
    Namespace,
)
from pathlib import Path


class FnToCLI:
    """
    A utility class which automatically infers and generates ArgParse command
    line options from a function based on defaults/type annotations

    This is _very_ basic; supports:
    * Args of int, str types (same logic as default argparse)
    * Args of bool type (Uses argparse BooleanOptionalAction)
        * eg `do_blah=False` becomes `--do-blah, --no-do-blah`
    * Args of typing.Optional (or anything with a default)
    * Args of typing.Literal (uses argparse choices)
        * eg `color: Literal['red, 'black']` becomes `--color red|black` (with docs)
    * Type deduction of default values
    * Supports async functions automatically
    * Includes docstring if it's in `:param my_arg: Description of my arg` format

    Anything else will likely error :)

    Example:
    if __name__ == '__main__':
        FnToCLI(my_func).run()
    """

    def __init__(self, fn: typing.Callable):
        self.fn = fn
        arg_names = fn.__code__.co_varnames[: fn.__code__.co_argcount]
        annotations = typing.get_type_hints(fn)
        defaults: list = fn.__defaults__ or []  # type: ignore[assignment]
        num_required = len(arg_names) - len(defaults)
        default_args = arg_names[num_required:]
        defaults: dict = {  # type: ignore[no-redef]
            arg: default for [arg, default] in zip(default_args, defaults)
        }

        docs = fn.__doc__ or ''
        arg_docs = self.parse_docs(docs)
        self.parser = ArgumentParser(
            description=docs.split(':param', 1)[0],
            formatter_class=ArgumentDefaultsHelpFormatter,
        )
        self.args: Namespace | None = None
        for arg in arg_names:
            optional = arg in defaults
            cli_name = arg.replace('_', '-')

            if arg in annotations:
                arg_opts = self.type_to_argparse(annotations[arg])
            elif arg in defaults:
                arg_opts = self.type_to_argparse(type(defaults[arg]))  # type: ignore[call-overload]
            else:
                raise ValueError(f'{arg} has no type information')

            # Help needs to always be defined, or it won't show the default :/
            arg_opts['help'] = arg_docs.get(arg) or '-'

            if optional:
                opt_name = f'--{cli_name}' if len(cli_name) > 1 else f'-{cli_name}'
                self.parser.add_argument(opt_name, default=defaults[arg], **arg_opts)  # type: ignore[call-overload]
            else:
                self.parser.add_argument(cli_name, **arg_opts)

    def parse_args(self, args: typing.Sequence[str] | None = None):
        self.args = self.parser.parse_args(args)
        return self.args

    def args_dict(self):
        if not self.args:
            self.parse_args()

        return {k.replace('-', '_'): v for k, v in self.args.__dict__.items()}

    def run(self):
        args_dicts = self.args_dict()
        if asyncio.iscoroutinefunction(self.fn):
            return asyncio.run(self.fn(**args_dicts))
        else:
            return self.fn(**args_dicts)

    @staticmethod
    def parse_docs(docs):
        params = docs.strip().split(':param ')[1:]
        params = [p.strip() for p in params]
        params = [p.split(':', 1) for p in params if p]
        return {name: docs.strip() for [name, docs] in params}

    @staticmethod
    def type_to_argparse(typ: type) -> dict:
        if FnToCLI.is_optional(typ):
            return FnToCLI.type_to_argparse(
                next(t for t in typing.get_args(typ) if not isinstance(t, type(None)))
            )
        if typ is bool:
            return {'type': typ, 'action': BooleanOptionalAction}

        simple_types = (int, str, float, Path)
        if typ in simple_types:
            return {'type': typ}

        if typing.get_origin(typ) is list:
            subtype = typing.get_args(typ)[0]
            if subtype in simple_types:
                return {'nargs': '*', 'type': subtype}

        if typing.get_origin(typ) == typing.Literal:
            return {'choices': typing.get_args(typ)}
        raise ValueError(f'Unsupported type: {typ}')

    @staticmethod
    def is_optional(typ: type) -> bool:
        return (
            (typing.get_origin(typ) is typing.Union or isinstance(typ, types.UnionType))
            and type(None) in typing.get_args(typ)
            and len(typing.get_args(typ)) == 2
        )


if __name__ == '__main__':

    def fn(nums: list[int]):
        print(sum(nums))

    cli = FnToCLI(fn)
    cli.run()
