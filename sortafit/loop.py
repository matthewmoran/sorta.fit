"""Sorta.Fit main polling loop — port of core/loop.sh"""
import importlib
import os
import sys
import time
from pathlib import Path

from sortafit.adapters import ADAPTER_REGISTRY
from sortafit.config import Config
from sortafit.events import log_event
from sortafit.gh_auth import refresh_gh_token
from sortafit.runners import RUNNER_REGISTRY
from sortafit.runners.base import ClaudeRateLimited
from sortafit.utils import (
    get_rate_limit_reset_epoch,
    is_rate_limited,
    lock_acquire,
    lock_release,
    log_error,
    log_info,
    log_step,
    log_warn,
    preflight_check,
)


def create_adapter(config: Config):
    """Create the appropriate board adapter based on config."""
    if config.board_adapter not in ADAPTER_REGISTRY:
        raise ValueError(f"Unknown adapter: {config.board_adapter}")
    module_path, class_name = ADAPTER_REGISTRY[config.board_adapter]
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(config)


def create_runner(name: str, config: Config, adapter):
    """Create a runner instance by name."""
    if name not in RUNNER_REGISTRY:
        raise ValueError(f"Unknown runner: {name}")
    cls = RUNNER_REGISTRY[name]
    return cls(config, adapter)


def print_banner(config: Config) -> None:
    """Print the startup banner."""
    print("================================================")
    print("  Sorta.Fit")
    print("================================================")
    print(f"  Adapter:  {config.board_adapter}")
    print(f"  Project:  {config.board_project_key}")
    print(f"  Target:   {config.target_repo}")
    print(f"  Runners:  {','.join(config.runners_enabled)}")
    print(f"  Interval: {config.poll_interval // 60} minutes")
    print(f"  Base branch: {config.git_base_branch}")
    print("================================================")
    print()


def validate_runners(config: Config) -> None:
    """Validate runner configuration and exit. Port of --validate mode."""
    log_step("Running validation checks...")
    failed = False

    adapter_config = Path(config.sorta_root) / "adapters" / f"{config.board_adapter}.config.sh"
    if not adapter_config.exists():
        log_error(f"Adapter config not found: {adapter_config}")
        failed = True

    valid_runners = list(RUNNER_REGISTRY.keys())
    for runner_name in config.runners_enabled:
        runner_name = runner_name.strip()
        if runner_name not in valid_runners:
            log_error(f"Unknown runner: {runner_name}")
            failed = True
            continue

        from_attr = f"runner_{runner_name}_from"
        from_val = getattr(config, from_attr, "")
        if not from_val:
            log_warn(f"Runner '{runner_name}': RUNNER_{runner_name.upper()}_FROM is not set — runner will not know which lane to read from")

    if failed:
        log_error("Validation failed.")
        sys.exit(1)

    log_info("Validation passed.")
    sys.exit(0)


def _sleep_until_reset(config: Config) -> None:
    """Sleep until the rate limit resets, then resume."""
    reset_epoch = get_rate_limit_reset_epoch(config.sorta_root)
    if not reset_epoch:
        # No parsed reset time — fall back to poll interval
        log_info(f"No reset time available. Waiting {config.poll_interval // 60} minutes.")
        return

    now = int(time.time())
    wait = reset_epoch - now
    if wait <= 0:
        log_info("Rate limit has already reset.")
        return

    minutes = wait // 60
    reset_str = time.strftime("%H:%M", time.localtime(reset_epoch))
    log_info(f"Sleeping {minutes}m until rate limit resets at {reset_str}...")
    time.sleep(wait)
    log_info("Rate limit window passed. Resuming.")

    # Clear the rate file
    rate_file = Path(config.sorta_root) / ".rate-limited"
    rate_file.unlink(missing_ok=True)


def run_loop(config: Config, validate: bool = False) -> None:
    """Main polling loop. Port of core/loop.sh."""
    print_banner(config)

    if validate:
        validate_runners(config)
        return

    if not preflight_check():
        sys.exit(1)

    adapter = create_adapter(config)
    lock_path = Path(config.sorta_root) / ".automation.lock"

    cycle_id = ""
    runner_name = "loop"

    def run_cycle():
        nonlocal cycle_id, runner_name
        if is_rate_limited(config.sorta_root):
            return

        if not lock_acquire(lock_path):
            return

        try:
            cycle_id = f"{os.getpid()}-{int(time.time())}"
            runner_name = "loop"

            if not refresh_gh_token(config):
                if config.gh_app_id and config.gh_app_installation_id:
                    log_error("GitHub App token refresh failed — skipping cycle (bot auth required)")
                    log_event("cycle_completed", config, runner_name=runner_name,
                              cycle_id=cycle_id, outcome="auth_failed")
                    return
                log_warn("GitHub App token refresh failed — falling back to default auth")

            log_event("cycle_started", config, runner_name=runner_name, cycle_id=cycle_id)
            log_info(f"Cycle starting at {time.strftime('%Y-%m-%d %H:%M:%S')}")

            runners_list = config.runners_enabled
            total = len(runners_list)
            rate_limited = False
            for i, name in enumerate(runners_list, 1):
                name = name.strip()
                log_step(f"[{i}/{total}] Running: {name}")
                runner_name = name
                try:
                    runner = create_runner(name, config, adapter)
                    runner.run()
                except ClaudeRateLimited:
                    log_warn(f"Rate limited during '{name}' — stopping remaining runners.")
                    rate_limited = True
                    break
                except Exception as e:
                    log_warn(f"Runner '{name}' encountered an error: {e}")

            runner_name = "loop"
            if rate_limited:
                log_event("cycle_completed", config, runner_name=runner_name,
                          cycle_id=cycle_id, outcome="rate_limited")
                _sleep_until_reset(config)
            else:
                log_event("cycle_completed", config, runner_name=runner_name, cycle_id=cycle_id)
                log_info(f"Cycle complete at {time.strftime('%Y-%m-%d %H:%M:%S')}. Next run in {config.poll_interval // 60} minutes.")
        finally:
            lock_release(lock_path)

    # Run immediately
    run_cycle()

    # Then loop
    try:
        while True:
            time.sleep(config.poll_interval)
            run_cycle()
    except KeyboardInterrupt:
        log_info("Loop stopped.")
