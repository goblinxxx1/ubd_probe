import argparse
import logging
import sys

from crawler.config import load_config
from crawler.discovery.search_state import SearchState
from crawler.schedule import PassiveSchedule
from crawler.scheduler import run_loop
from crawler.wiring import build_runner


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="crawler")
    parser.add_argument("command", choices=["run", "loop"], help="what to do")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("crawler")

    if args.command == "run":
        config = load_config()
        runner = build_runner(config)
        summary = runner.run()
        log.info("done: %s", summary)
        return 0

    if args.command == "loop":
        config = load_config()
        runner = build_runner(config)
        passive = PassiveSchedule(config.passive_state_path, config.passive_interval_seconds)

        def _load_state():
            return SearchState.load(config.search_state_path) if config.active_discovery else None

        def _learn():
            runner.learn_and_reload_grid(config)   # mine → rebuild live grid, in-process

        log.info("scheduler: adaptive loop — active while DDG free, passive in backoff windows")
        run_loop(runner, _load_state, passive,
                 active_delay=config.active_loop_delay_seconds,
                 backoff_max_sleep=config.backoff_max_sleep_seconds,
                 hard_factor=config.passive_hard_overdue_factor,
                 learn=_learn, learn_interval_seconds=config.learn_interval_seconds)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
