import asyncio
import typing
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter, Namespace


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
        annotations = fn.__annotations__
        defaults = fn.__defaults__ or []  # type: ignore
        num_required = len(arg_names) - len(defaults)
        default_args = arg_names[num_required:]
        defaults = {
            arg: default
            for [arg, default] in zip(default_args, defaults)
        }

        docs = fn.__doc__ or ''
        arg_docs = self.parse_docs(docs)
        self.parser = ArgumentParser(
            description=docs.split(':param', 1)[0],
            formatter_class=ArgumentDefaultsHelpFormatter,
        )
        self.args: typing.Optional[Namespace] = None
        for arg in arg_names:
            optional = arg in defaults
            cli_name = arg.replace('_', '-')

            if arg in annotations:
                arg_opts = self.type_to_argparse(annotations[arg])
            elif arg in defaults:
                arg_opts = self.type_to_argparse(type(defaults[arg]))
            else:
                raise ValueError(f'{arg} has no type information')

            # Help needs to always be defined, or it won't show the default :/
            arg_opts['help'] = arg_docs.get(arg) or '-'

            if optional:
                opt_name = f'--{cli_name}' if len(cli_name) > 1 else f'-{cli_name}'
                self.parser.add_argument(opt_name, default=defaults[arg], **arg_opts)
            else:
                self.parser.add_argument(cli_name, **arg_opts)

    def parse_args(self):
        self.args = self.parser.parse_args()
        return self.args

    def args_dict(self):
        if not self.args:
            self.parse_args()

        return {k.replace('-', '_'): v for k, v in self.args.__dict__.items()}

    def run(self):
        args_dicts = self.args_dict()
        if asyncio.iscoroutinefunction(self.fn):
            asyncio.run(self.fn(**args_dicts))
        else:
            self.fn(**args_dicts)

    @staticmethod
    def parse_docs(docs):
        params = docs.strip().split(':param ')[1:]
        params = [p.strip() for p in params]
        params = [p.split(':', 1) for p in params if p]
        return {name: docs.strip() for [name, docs] in params}

    @staticmethod
    def type_to_argparse(typ):
        if typ == bool:
            from argparse import BooleanOptionalAction  # type: ignore

            return {'type': typ, 'action': BooleanOptionalAction}
        if typ in (int, str, float):
            return {'type': typ}
        if typ == list[str]:
            return {'nargs': '*'}
        if not hasattr(typ, '__origin__'):
            raise ValueError(f'Cannot determine type of {typ}')
        if typ.__origin__ == typing.Literal:
            return {'choices': typ.__args__}
        raise ValueError(f'Unsupported type: {typ}')
