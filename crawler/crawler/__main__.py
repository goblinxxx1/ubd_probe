import argparse
import logging
import sys

from crawler.config import load_config
from crawler.wiring import build_runner


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="crawler")
    parser.add_argument("command", choices=["run"], help="what to do")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.command == "run":
        config = load_config()
        runner = build_runner(config)
        summary = runner.run()
        logging.getLogger("crawler").info("done: %s", summary)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
