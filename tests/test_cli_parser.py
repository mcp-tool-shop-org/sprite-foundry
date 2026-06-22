"""CLI parser tests (F-008 + backend F-014).

Covers:
- build_parser() constructs without raising;
- argument parsing + type coercion (e.g. --seed type=int);
- required-argument enforcement (missing --code -> SystemExit);
- parser/dispatch PARITY: every subcommand registered in build_parser has a
  handler in main()'s dispatch dict, and vice versa — a subcommand added to one
  but not the other would silently fall through;
- no-subcommand exits 2 (backend F-014), the argparse usage-error convention,
  rather than exiting 0.
"""

import argparse

import pytest

from foundry import cli


# ── construction + parsing ──────────────────────────────────


def test_build_parser_constructs():
    parser = cli.build_parser()
    assert isinstance(parser, argparse.ArgumentParser)


def test_register_run_coerces_seed_to_int():
    parser = cli.build_parser()
    args = parser.parse_args(
        ["register-run", "r1", "--subject", "s", "--stack", "A", "--seed", "7"]
    )
    assert args.command == "register-run"
    assert args.seed == 7
    assert isinstance(args.seed, int)


def test_register_run_defaults_target_to_int():
    parser = cli.build_parser()
    args = parser.parse_args(
        ["register-run", "r1", "--subject", "s", "--stack", "A", "--seed", "1"]
    )
    assert args.target == 48
    assert isinstance(args.target, int)


def test_review_reject_requires_code():
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        # --code is required; omitting it is a usage error.
        parser.parse_args(["review-reject", "5"])


def test_ship_check_direction_count_is_int():
    parser = cli.build_parser()
    args = parser.parse_args(["ship-check", "r1", "--direction-count", "8"])
    assert args.direction_count == 8
    assert isinstance(args.direction_count, int)


# ── parser/dispatch parity (F-008) ──────────────────────────


def _registered_subcommands(parser):
    """Pull the set of subcommand names registered on the parser."""
    names = set()
    for action in parser._subparsers._group_actions:
        if isinstance(action, argparse._SubParsersAction):
            names.update(action.choices.keys())
    return names


def _dispatch_keys():
    """Statically extract the keys of main()'s `commands` dispatch dict without
    executing main(). We parse the source so we don't have to run argparse."""
    import inspect
    import ast

    src = inspect.getsource(cli.main)
    tree = ast.parse(src)
    keys = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "commands":
                    if isinstance(node.value, ast.Dict):
                        for k in node.value.keys:
                            if isinstance(k, ast.Constant):
                                keys.add(k.value)
    return keys


def test_every_subcommand_has_a_handler():
    parser = cli.build_parser()
    registered = _registered_subcommands(parser)
    dispatched = _dispatch_keys()
    assert registered, "no subcommands found on parser"
    assert dispatched, "could not extract dispatch dict keys"
    # Parity both ways: no orphan subcommand and no orphan handler.
    assert registered == dispatched, (
        f"parser/dispatch mismatch — "
        f"only in parser: {registered - dispatched}; "
        f"only in dispatch: {dispatched - registered}"
    )


# ── no-subcommand exits 2 (backend F-014) ───────────────────


def test_no_subcommand_exits_2(monkeypatch, capsys):
    # main() reads argv; simulate `foundry` with no subcommand.
    monkeypatch.setattr("sys.argv", ["foundry"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
