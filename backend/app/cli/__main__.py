"""Entrypoint for `python -m app.cli`."""

import argparse
import sys

from sqlmodel import Session, select

from app.core.security import get_password_hash
from app.persistence.db import engine
from app.persistence.tables import User


def cmd_create_admin(args: argparse.Namespace) -> int:
    with Session(engine) as session:
        if session.exec(select(User).where(User.username == args.username)).first():
            print(f"User already exists: {args.username}", file=sys.stderr)
            return 1
        session.add(
            User(
                username=args.username,
                password_hash=get_password_hash(args.password),
                is_admin=bool(args.admin),
                settings={},
                api_keys={},
            )
        )
        session.commit()
    print(f"Created user {args.username} (is_admin={args.admin})")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p_admin = sub.add_parser(
        "create-admin",
        help="Create a user (first admin for an empty install).",
    )
    p_admin.add_argument("--username", required=True)
    p_admin.add_argument("--password", required=True)
    p_admin.add_argument(
        "--admin",
        action="store_true",
        default=True,
        help="Grant is_admin (default: true)",
    )
    p_admin.add_argument(
        "--no-admin",
        action="store_false",
        dest="admin",
        help="Do not grant is_admin",
    )
    p_admin.set_defaults(func=cmd_create_admin)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
